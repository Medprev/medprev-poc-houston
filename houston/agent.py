"""E4 — one `claude -p` subprocess per finding. Read-only tools only; Bash,
Write, and Edit are denied, so nothing the model produces reaches disk
except through the PII gate in houston.frontmatter.

Bounded by --max-budget-usd and a wall-clock timeout, not --max-turns —
see ADR-0006: the turn-count flag the original design assumed does not
exist in the installed CLI (2.1.251).
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
evidência, use esse mesmo link ou a consulta (`query`) que você rodou.

Responda em português, com esta estrutura exata:

## Causa raiz
Um parágrafo, em linguagem direta: qual é o serviço, o que está acontecendo e desde quando.

## Linha do tempo
Lista curta com as datas/versões relevantes (primeira ocorrência, última ocorrência, \
regressão se houver) — extraia dos campos do achado, não invente datas.

## Evidência
Lista com marcadores, cada um uma afirmação seguida da consulta ou chamada de ferramenta \
exata que a sustenta. Nunca cole linha de log ou dado de usuário — referencie onde \
encontrar, não o conteúdo em si.

## Ação recomendada
Uma ou duas frases.

## Corpo da issue
Um corpo de issue do GitHub pronto para colar, em formato 5W2H \
(O quê/Por quê/Onde/Quando/Quem/Como/Quanto), com menos de 50 linhas.

O achado, em JSON, vem a seguir pelo stdin.
"""


@dataclass
class InvestigationResult:
    body: str | None
    input_tokens: int
    output_tokens: int
    duration_s: float
    usd: float
    state: str  # "new" (investigated) | "incomplete" (failed/timed out)
    error: str | None = None


def _load_allowlist() -> str:
    names = [
        line.strip()
        for line in ALLOWLIST_PATH.read_text().splitlines()
        if line.strip()
    ]
    return ",".join(names)


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
        "first_seen_ms": finding.first_seen_ms,
        "last_seen_ms": finding.last_seen_ms,
        "severity": finding.severity,
        "regressed": finding.regressed,
        "datadog_url": finding.datadog_url,
    })

    try:
        proc = subprocess.run(
            cmd, input=stdin_payload, capture_output=True, text=True,
            env=env, timeout=timeout_s, check=False,
        )
    except subprocess.TimeoutExpired:
        return InvestigationResult(
            body=None, input_tokens=0, output_tokens=0,
            duration_s=float(timeout_s), usd=0.0, state="incomplete",
            error=f"timed out after {timeout_s}s",
        )

    if proc.returncode != 0:
        return InvestigationResult(
            body=None, input_tokens=0, output_tokens=0, duration_s=0.0,
            usd=0.0, state="incomplete", error=proc.stderr[-2000:],
        )

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return InvestigationResult(
            body=None, input_tokens=0, output_tokens=0, duration_s=0.0,
            usd=0.0, state="incomplete",
            error=f"non-JSON stdout: {proc.stdout[:500]}",
        )

    usage = payload.get("usage", {})
    return InvestigationResult(
        body=payload.get("result"),
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        duration_s=payload.get("duration_ms", 0) / 1000,
        usd=payload.get("total_cost_usd", 0.0),
        state="new",
    )
