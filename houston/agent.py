"""E4 — one `claude -p` subprocess per finding. Read-only tools only; Bash,
Write, and Edit are denied, so nothing the model produces reaches disk
except through the PII gate in houston.frontmatter.

Bounded by --max-budget-usd and a wall-clock timeout, not --max-turns —
see ADR-0006: the turn-count flag the original design assumed does not
exist in the installed CLI (2.1.251).

Model and effort are pinned on the command line, never inherited from the
operator's own Claude Code settings -- ADR-0023: an unpinned subprocess
priced its $0.50 budget against whatever model the operator had last
selected interactively, and one run of three findings spent $2.41
producing three `state: incomplete` reports and no investigation.

Cost accounting reads the whole usage envelope, including cache tokens and
the envelope a *failed* run still prints on stdout — see ADR-0013.

The prompt states separately that querying logs is mandatory and that
pasting their content is forbidden -- ADR-0024: read as one rule, the
paste ban made a run declare application logs "fora do escopo de leitura
seguro" and stop at "causa não determinada", while the record that
explained the error sat in the same trace.
"""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from houston.model_runner import DEFAULT_RUNNER, ModelRun, ModelRunner
from houston.models import Finding
from houston.timestamps import canonicalize, format_ms

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST_PATH = ROOT / "houston" / "allowedtools.txt"

# Sized against the ADR-0024 investigation shape, measured on this finding:
# the pre-ADR-0024 prompt completed for $0.38, the correlating prompt died
# at the old $0.50 cap in error_max_budget_usd, and completed for $0.6337.
# Trace correlation is round-trips, and round-trips are the cost -- moving
# the prompt means moving this, the same way moving tiers does (ADR-0023).
DEFAULT_MAX_BUDGET_USD = "0.75"
DEFAULT_TIMEOUT_S = 300

# The tier that produced every report promoted so far, and the tier the
# budget above is sized for. Opus costs 2.5x per token and defaults to a
# higher effort level, which does not fit this cap -- raise
# --max-budget-usd along with --model if you change this (ADR-0023).
DEFAULT_MODEL = "sonnet"
DEFAULT_EFFORT = "medium"

PROMPT = """Você está investigando um achado de observabilidade do Datadog. \
Você tem ferramentas de leitura para buscar mais contexto (logs, spans, eventos, issues \
relacionadas) — USE-AS para reconstruir o que aconteceu dentro da janela, não apenas \
para confirmar o que já veio no achado. Não chute evidência que você não consultou de \
verdade.

CONSULTAR É OBRIGATÓRIO; COLAR É PROIBIDO — são duas regras diferentes, não confunda \
uma com a outra. Você DEVE consultar os logs de aplicação do serviço afetado (\
`search_datadog_logs`, `analyze_datadog_logs`) e os spans do erro (`search_datadog_spans`, \
`aggregate_spans`); o que você não pode é COLAR o conteúdo que encontrar. Toda ferramenta \
que aparece na sua lista de ferramentas está autorizada para esta investigação: NUNCA \
escreva que uma consulta ficou "fora do escopo", "fora do escopo de leitura seguro" ou \
indisponível — se você tem a ferramenta, o escopo é rodar a consulta e relatar apenas o \
que ela devolveu, em forma de contagem, agregação ou ponteiro.

O caminho mais curto para a causa raiz é o TRACE DO PRÓPRIO ERRO, não o erro isolado. \
Pegue um `trace_id` de uma ocorrência e liste TODO o trace (logs e spans daquele \
`trace_id`): o que explica o erro quase sempre está num registro vizinho de outro nível \
(um `warn` de guard/middleware, um span de banco, um status HTTP) que nunca aparece se \
você olhar só o erro. Faça isso antes de concluir qualquer coisa sobre a causa.

ECONOMIA DE CONTEXTO — você tem orçamento por rodada, e um dump de log cru o consome \
inteiro sem entregar nada a mais. Pergunte em forma de NÚMERO, não de amostra:
- Para "quanto disso existe", use agregação (`aggregate_spans`, `analyze_datadog_logs`) ou \
uma busca com `limit: 1` e leia só a contagem total que vem no metadado — nunca pagine \
uma busca para contar à mão.
- Nunca peça todos os campos (`extra_fields: ["*"]`) numa busca ampla; nomeie os poucos \
campos que você vai usar, e só amplie num único registro quando precisar descobrir a \
forma do payload.
- Um trace inteiro e um punhado de registros representativos bastam; mais amostras da \
mesma coisa não mudam a conclusão.
- Se uma consulta voltar vazia, isso é resultado: registre e siga, não tente variações \
da mesma pergunta.

SINAL OU RUÍDO — decida isso explicitamente, é a pergunta que define se alguém deve agir: \
antes de tratar o achado como bug, verifique como o próprio serviço classifica o evento. \
Agregue os spans do erro por `@error.handling` (`handled` = resultado de negócio tratado \
pelo código; `unhandled` = falha de verdade) e por `@http.status_code`, e olhe o recurso/rota \
real. Um erro 100% `handled`, com volume estável e sem log de falha, é comportamento \
esperado modelado como exceção — é RUÍDO no Error Tracking, e dizer isso é uma conclusão \
válida e útil, não um fracasso da investigação. Nesse caso o defeito a relatar é o próprio \
ruído (resultado esperado lançado como exceção) e/ou o problema real que você encontrou \
correlacionado no trace, não uma causa inventada para o erro original.

O achado já vem com links diretos para o Datadog em `evidence_links` (cada um com \
`label`, `url` e, quando existir, `query`) e o link legado `datadog_url` — NUNCA \
construa, monte ou invente uma URL do Datadog; use sempre um desses links prontos, ou \
cite a `query` exata que você rodou.

REGRA DE TEMPO — leia com atenção, é a parte mais importante deste achado, e um erro de \
data aqui é inaceitável:
- Para as datas do PRÓPRIO achado, use exatamente as strings já formatadas que vêm no \
JSON: `window_from`, `window_to`, `first_seen`, `last_seen`. Copie-as LITERALMENTE, POR \
INTEIRO, toda vez que citar uma delas — inclusive a parte entre parênteses com o epoch e \
o ISO-8601. NUNCA corte, resuma ou reescreva a string para citar só a hora/data; se \
precisar economizar espaço, encurte o texto ao redor, não a data em si. E NUNCA calcule, \
converta ou aproxime uma data a partir de `window_from_ms`, `first_seen_ms` etc. (esses \
campos `_ms` existem só para referência de escopo, não para você formatar).
- Para qualquer timestamp que você ENCONTRAR usando as ferramentas de leitura (evento, \
log, span, versão de deploy), escreva-o literalmente dentro de um marcador \
`{{ts:<valor exatamente como a ferramenta retornou>}}` — por exemplo `{{ts:1788708797000}}` \
ou `{{ts:2026-09-06T15:33:17Z}}`. O código renderiza esse marcador na hora certa depois; \
você nunca escreve a data por extenso com a mão.
- Se não conseguir um timestamp exato para algo, diga isso explicitamente em vez de \
estimar ("não foi possível determinar o horário exato de X").

Leia os campos de contagem com cuidado, porque eles têm escopos diferentes:
- `observed_count` é a contagem DENTRO da janela de coleta (`window_from`–`window_to`). \
Não é total acumulado, e pode cair de uma rodada para a outra. Sempre que citar esse \
número, diga a janela: "N ocorrências entre <window_from> e <window_to>".
- `first_seen`/`last_seen` são do histórico completo do achado, não da janela. Nunca \
combine `observed_count` com `first_seen` numa frase como "N ocorrências desde \
<first_seen>" — são escopos diferentes e a frase fica falsa.
- Se a sua própria consulta ao Datadog devolver um total diferente de `observed_count`, \
a explicação mais provável é a diferença de janela; diga qual janela cada número usa em \
vez de tratar a divergência como inexplicada.

`target_repo` no JSON é o repositório de código do serviço afetado (ou `null` para \
componentes de infraestrutura sem repositório próprio) — é para onde a ação recomendada \
deve apontar.

Responda em português, com esta estrutura exata:

## Causa raiz
Um parágrafo, em linguagem direta: qual é o serviço, o que está acontecendo e desde quando.
Diga se o evento é sinal ou ruído (ver "SINAL OU RUÍDO" acima), com o número que sustenta a
classificação — a divisão `handled`/`unhandled` que você mediu.
Se a causa não estiver confirmada pelas evidências consultadas, diga isso explicitamente
em vez de apresentar uma hipótese como certeza — e, nesse caso, liste as consultas que você
efetivamente rodou e o que cada uma devolveu (incluindo as que voltaram vazias). "Não
determinada" sem essa lista não é uma conclusão aceitável, e alegar que uma consulta não
era permitida é sempre falso.

## Linha do tempo
Lista ordenada, cronológica, PASSO A PASSO dos eventos DENTRO da janela de coleta — não \
apenas primeira/última ocorrência. Consulte as ferramentas de leitura com a `query` de \
`evidence_links` (monitor: cada evento Triggered/Re-Triggered/Recovered; kubernetes: cada \
evento do Reason; error tracking: ocorrências e mudanças de versão) e liste cada um, \
com o marcador `{{ts:...}}` primeiro, seguido do que aconteceu e do link/consulta que \
prova aquele item. Se a ferramenta não devolveu eventos suficientes para um passo a \
passo, diga isso e liste o que os campos do achado garantem (`window_from`, `window_to`, \
`first_seen`, `last_seen`).

## Evidência
Lista com marcadores, cada um uma afirmação seguida do link de `evidence_links`/`datadog_url` \
que a sustenta, ou — se não houver link para aquele dado específico — a consulta ou \
chamada de ferramenta exata. Inclua aqui as consultas de log e de span que você rodou, com \
a contagem que cada uma devolveu. Nunca cole linha de log nem dado de usuário: isso \
restringe o que você ESCREVE, nunca o que você CONSULTA — cite a consulta, a contagem e o \
campo, não o conteúdo. Nunca construa uma URL: use as que vieram prontas.

## Ação recomendada
Uma ou duas frases com a ação objetiva.

## Corpo da issue
A ÚLTIMA seção do relatório — não escreva nada depois dela. É o texto que vira uma issue \
do GitHub e que um segundo agente de correção vai ler para consertar o código sozinho, \
então tem que ser específico o bastante para isso. Não abra a seção com um bloco de \
código (```). Até ~120 linhas. Use exatamente estas subseções, cada uma com `###`:

### Descrição do incidente
Descrição objetiva e clara: o que está acontecendo, em qual serviço, desde quando, e \
qual o impacto observável (para o usuário ou para o sistema).

### Causa raiz
A mesma conclusão da seção `## Causa raiz` acima, resumida; diga "não determinada" se for \
o caso, sem inventar uma causa para preencher a seção. Abra com a classificação sinal ou \
ruído e o número que a sustenta, para quem ler a issue saber se deve agir no erro em si.

### Linha do tempo
A mesma lista passo a passo de `## Linha do tempo`, incluindo correlações relevantes \
(deploy/versão, mudanças de estado do monitor, eventos relacionados de outros achados se \
você os encontrou).

### Evidências
Os mesmos links/consultas de `## Evidência`, como lista pronta para o leitor clicar.

### Ação recomendada
Ação concreta e específica o bastante para outro agente executar sem precisar investigar \
de novo: nomeie o repositório (`target_repo`, ou "infra — sem repositório de código, ação \
operacional" se `target_repo` for nulo), o arquivo/função/componente afetado quando \
identificável, o que exatamente deve mudar, e como validar que a correção resolveu o \
problema.

### Volume
`observed_count` com a janela em que foi medido; se você consultou o Datadog e obteve um \
total diferente (outra janela, outro filtro), inclua também, identificando a janela de \
cada número.

### Severidade e criticidade
A `severity` do achado, e uma avaliação de criticidade para o negócio (impacto em \
usuários, dados ou operação) — se a criticidade for uma inferência sua e não um dado \
direto do achado, marque isso explicitamente como inferência. Se você classificou o achado \
como ruído, diga que a `severity` do achado não se aplica ao erro em si e avalie a \
criticidade do defeito que você de fato encontrou — inclusive quando ele é mais grave que \
o achado original.

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
    # The model the CLI reports having actually billed, not the alias we
    # asked for -- diagnosing ADR-0023 required deriving the model from
    # cost arithmetic because no report recorded it.
    model: str | None = None
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    # `{{ts:...}}` markers the prompt asked for but couldn't be parsed into
    # a timestamp -- left visible in `body` verbatim, never silently
    # dropped or guessed at (see houston/timestamps.py:canonicalize).
    warnings: list[str] = field(default_factory=list)


def _load_allowlist() -> str:
    names = [
        line.strip()
        for line in ALLOWLIST_PATH.read_text().splitlines()
        if line.strip()
    ]
    return ",".join(names)


def _payload_or_none(stdout: str | None) -> dict | None:
    """The CLI prints its JSON envelope on stdout even when it exits
    non-zero, so this runs on every path, not just the success one.

    Every caller passes ModelOutcome.stdout, which model_runner.py already
    decodes from bytes if the subprocess layer ever captured it that way
    (ADR-0031) -- decoding here too would be dead code duplicating that
    rule in a second place."""
    if not stdout:
        return None
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _billed_model(payload: dict | None, requested: str) -> str:
    """`modelUsage` is keyed by the resolved model id (e.g.
    `claude-sonnet-5`), which is what we want on record; a run that died
    before its first billed request has no envelope, so the alias we asked
    for is the honest fallback."""
    model_usage = (payload or {}).get("modelUsage")
    if isinstance(model_usage, dict) and model_usage:
        return ",".join(sorted(model_usage))
    return requested


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
    requested_model: str = DEFAULT_MODEL,
) -> InvestigationResult:
    usage = (payload or {}).get("usage") or {}
    total_input, cache_read, cache_creation = _input_tokens(usage)
    duration_ms = (payload or {}).get("duration_ms")
    body = None
    warnings: list[str] = []
    if state == "new":
        raw_result = (payload or {}).get("result")
        if raw_result:
            body, warnings = canonicalize(raw_result)
    return InvestigationResult(
        body=body,
        input_tokens=total_input,
        output_tokens=int(usage.get("output_tokens") or 0),
        duration_s=(duration_ms / 1000) if duration_ms else fallback_duration_s,
        usd=float((payload or {}).get("total_cost_usd") or 0.0),
        state=state,
        error=error,
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_creation,
        warnings=warnings,
        model=_billed_model(payload, requested_model),
    )


def investigate(
    finding: Finding,
    max_budget_usd: str = DEFAULT_MAX_BUDGET_USD,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    target_repo: str | None = None,
    model: str = DEFAULT_MODEL,
    effort: str = DEFAULT_EFFORT,
    runner: ModelRunner = DEFAULT_RUNNER,
) -> InvestigationResult:
    env = {**os.environ}
    env.pop("CLAUDECODE", None)  # allow nesting claude -p inside a session
    # Same reason model and effort are pinned below: an operator's session
    # must not be able to reprice this run (ADR-0023).
    env.pop("CLAUDE_EFFORT", None)

    cmd = [
        "claude", "-p",
        "--output-format", "json",
        "--model", model,
        "--effort", effort,
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
        # Pre-rendered, code-owned canonical strings -- the model copies
        # these verbatim and never computes a date itself (see the "REGRA
        # DE TEMPO" section of PROMPT).
        "window_from": format_ms(finding.window_from_ms),
        "window_to": format_ms(finding.window_to_ms),
        "first_seen": format_ms(finding.first_seen_ms),
        "last_seen": format_ms(finding.last_seen_ms),
        "severity": finding.severity,
        "regressed": finding.regressed,
        "datadog_url": finding.datadog_url,
        "evidence_links": [
            {"label": link.label, "url": link.url, "query": link.query}
            for link in finding.evidence_links
        ],
        "target_repo": target_repo,
        "raw": finding.raw,
    })

    outcome = runner.run(ModelRun(
        argv=cmd, stdin=stdin_payload, env=env, timeout_s=timeout_s,
    ))

    if outcome.timed_out:
        partial = _payload_or_none(outcome.stdout)
        return _result(
            partial, "incomplete",
            error=_error_text(partial, "", prefix=f"timed out after {timeout_s}s"),
            fallback_duration_s=float(timeout_s),
            requested_model=model,
        )

    payload = _payload_or_none(outcome.stdout)

    if outcome.returncode != 0:
        return _result(payload, "incomplete", error=_error_text(payload, outcome.stderr),
                       requested_model=model)

    if payload is None:
        return _result(
            None, "incomplete",
            error=f"non-JSON stdout: {outcome.stdout[:500]}",
            requested_model=model,
        )

    if payload.get("is_error") or not payload.get("result"):
        return _result(payload, "incomplete", error=_error_text(payload, outcome.stderr),
                       requested_model=model)

    return _result(payload, "new", requested_model=model)
