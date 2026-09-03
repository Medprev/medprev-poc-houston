"""E4 — one `claude -p` subprocess per finding. Read-only tools only; Bash,
Write, and Edit are denied, so nothing the model produces reaches disk
except through the PII gate in houston.frontmatter.

Bounded by --max-budget-usd and a wall-clock timeout, not --max-turns —
see ADR-0006: the turn-count flag the original design assumed does not
exist in the installed CLI (2.1.251).

Cost accounting reads the whole usage envelope, including cache tokens and
the envelope a *failed* run still prints on stdout — see ADR-0013.
"""
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from houston.models import Finding

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST_PATH = ROOT / "houston" / "allowedtools.txt"

DEFAULT_MAX_BUDGET_USD = "0.50"
DEFAULT_TIMEOUT_S = 300

PROMPT = """Você está investigando um achado de observabilidade do Datadog. \
Você tem ferramentas de leitura para buscar mais contexto (logs, spans, issues \
relacionadas) se for útil — não precisa usá-las se o achado já estiver claro. \
Não chute evidência que você não consultou de verdade.

O achado já vem com um link direto para o Datadog (`datadog_url` no JSON) — \
não construa nem invente outro link; se quiser referenciar onde conferir a \
evidência, use esse mesmo link ou a consulta (`query`) que acompanha o achado.

Leia os campos de contagem com cuidado, porque eles têm escopos diferentes:
- `observed_count` é a contagem DENTRO da janela de coleta, delimitada por \
`window_from_ms` e `window_to_ms`. Não é total acumulado, e pode cair de uma \
rodada para a outra. Sempre que citar esse número, diga a janela: \
"N ocorrências entre <window_from_ms> e <window_to_ms>".
- `first_seen_ms` e `last_seen_ms` são do histórico completo do achado, \
não da janela. Nunca combine `observed_count` com `first_seen_ms` numa frase \
como "N ocorrências desde <first_seen_ms>" — são escopos diferentes e a frase \
fica falsa.
- Se a sua própria consulta ao Datadog devolver um total diferente de \
`observed_count`, a explicação mais provável é a diferença de janela; diga \
qual janela cada número usa em vez de tratar a divergência como inexplicada.

Responda em português, com esta estrutura exata:

## Causa raiz
Um parágrafo, em linguagem direta: qual é o serviço, o que está acontecendo e desde quando.

## Linha do tempo
Lista curta com as datas/versões relevantes (primeira ocorrência, última ocorrência, \
regressão se houver) — extraia dos campos do achado, não invente datas. Se um campo \
de data vier nulo, escreva que o achado não carrega essa data em vez de estimá-la.

## Evidência
Lista com marcadores, cada um uma afirmação seguida da consulta ou chamada de ferramenta \
exata que a sustenta. Nunca cole linha de log ou dado de usuário — referencie onde \
encontrar, não o conteúdo em si.

## Ação recomendada
Uma ou duas frases.

## Corpo da issue
Um corpo de issue do GitHub pronto para colar, em formato 5W2H \
(O quê/Por quê/Onde/Quando/Quem/Como/Quanto), com menos de 50 linhas. Escreva o \
corpo direto, sem envolver a seção em bloco de código (```) — ele é colado como \
markdown de issue, não como código.

O achado, em JSON, vem a seguir pelo stdin.
"""


@dataclass
class InvestigationResult:
    body: str | None
    input_tokens: int  # total billed input: uncached + cache read + cache creation
    output_tokens: int
    duration_s: float
    usd: float
    state: str  # "new" (investigated) | "incomplete" (failed/timed out)
    error: str | None = None
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


def _load_allowlist() -> str:
    names = [
        line.strip()
        for line in ALLOWLIST_PATH.read_text().splitlines()
        if line.strip()
    ]
    return ",".join(names)


def _payload_or_none(stdout: str | bytes | None) -> dict | None:
    """The CLI prints its JSON envelope on stdout even when it exits
    non-zero, so this runs on every path, not just the success one."""
    if not stdout:
        return None
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _input_tokens(usage: dict) -> tuple[int, int, int]:
    """Returns (total_billed_input, cache_read, cache_creation).

    `usage.input_tokens` alone counts only the uncached prefix: a real run
    (2026-09-02) reported input_tokens=0 next to cache_read=10596 and
    cache_creation=13285, which is why every report on disk recorded 2-14
    input tokens for a ~$0.32 investigation (ADR-0013)."""
    uncached = int(usage.get("input_tokens") or 0)
    cache_read = int(usage.get("cache_read_input_tokens") or 0)
    cache_creation = int(usage.get("cache_creation_input_tokens") or 0)
    return uncached + cache_read + cache_creation, cache_read, cache_creation


def _error_text(payload: dict | None, stderr: str, prefix: str = "") -> str:
    """The CLI reports *why* it stopped on stdout (`subtype`, `errors`), and
    leaves stderr empty — a budget-exhausted run has an empty stderr and an
    `error_max_budget_usd` subtype."""
    parts = [prefix] if prefix else []
    if payload:
        subtype = payload.get("subtype")
        if subtype and subtype != "success":
            parts.append(str(subtype))
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            parts.append("; ".join(str(e) for e in errors))
        elif errors:
            parts.append(str(errors))
        if len(parts) == (1 if prefix else 0) and isinstance(payload.get("result"), str):
            parts.append(payload["result"])
    if stderr and len(parts) == (1 if prefix else 0):
        parts.append(stderr)
    if not parts:
        parts.append("no diagnostics on stdout or stderr")
    return " — ".join(p for p in parts if p)[-2000:]


def _result(
    payload: dict | None,
    state: str,
    error: str | None = None,
    fallback_duration_s: float = 0.0,
) -> InvestigationResult:
    usage = (payload or {}).get("usage") or {}
    total_input, cache_read, cache_creation = _input_tokens(usage)
    duration_ms = (payload or {}).get("duration_ms")
    return InvestigationResult(
        body=(payload or {}).get("result") if state == "new" else None,
        input_tokens=total_input,
        output_tokens=int(usage.get("output_tokens") or 0),
        duration_s=(duration_ms / 1000) if duration_ms else fallback_duration_s,
        usd=float((payload or {}).get("total_cost_usd") or 0.0),
        state=state,
        error=error,
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_creation,
    )


def investigate(
    finding: Finding,
    max_budget_usd: str = DEFAULT_MAX_BUDGET_USD,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> InvestigationResult:
    env = {**os.environ}
    env.pop("CLAUDECODE", None)  # allow nesting claude -p inside a session

    cmd = [
        "claude", "-p",
        "--output-format", "json",
        "--allowedTools", _load_allowlist(),
        "--disallowedTools", "Bash,Write,Edit",
        "--max-budget-usd", max_budget_usd,
        PROMPT,
    ]
    stdin_payload = json.dumps({
        "fingerprint": finding.fingerprint,
        "source": finding.source,
        "service": finding.service,
        "reason": finding.reason,
        "query": finding.query,
        "observed_count": finding.observed_count,
        "window_from_ms": finding.window_from_ms,
        "window_to_ms": finding.window_to_ms,
        "first_seen_ms": finding.first_seen_ms,
        "last_seen_ms": finding.last_seen_ms,
        "severity": finding.severity,
        "regressed": finding.regressed,
        "datadog_url": finding.datadog_url,
        "raw": finding.raw,
    })

    try:
        proc = subprocess.run(
            cmd, input=stdin_payload, capture_output=True, text=True,
            env=env, timeout=timeout_s, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        partial = _payload_or_none(exc.stdout)
        return _result(
            partial, "incomplete",
            error=_error_text(partial, "", prefix=f"timed out after {timeout_s}s"),
            fallback_duration_s=float(timeout_s),
        )

    payload = _payload_or_none(proc.stdout)

    if proc.returncode != 0:
        return _result(payload, "incomplete", error=_error_text(payload, proc.stderr))

    if payload is None:
        return _result(
            None, "incomplete",
            error=f"non-JSON stdout: {proc.stdout[:500]}",
        )

    if payload.get("is_error") or not payload.get("result"):
        return _result(payload, "incomplete", error=_error_text(payload, proc.stderr))

    return _result(payload, "new")
