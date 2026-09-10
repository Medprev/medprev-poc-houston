# ADR-0022: Code-owned timestamps, pre-built evidence links, and a fix-ready issue body

**Status:** Accepted
**Date:** 2026-09-10
**Deciders:** Carla Cury (explicit request, after reviewing real reports on disk: "quero primeiro
a hora e que mostre o passo a passo dentro da janela... isso vc tem que ser 100% criterioso não
podemos ter erros de quando aconteceu o problema", plus a rewrite of the issue-body content and the
`AIOPS` label requirement)
**Decision style:** Bug fix (wrong/vague dates in reports) plus two explicit change requests from
the repository owner.
**Related:** [[0011-datadog-links-and-portuguese-report-body]] (partially superseded — decision 3's
5W2H issue body is replaced by the outline below), [[0014-window-scoped-counts-and-per-finding-evidence]],
[[0004-pii-gate-luhn-false-positive-on-epoch-timestamps]], [[0017-pii-gate-validates-documents-not-digit-shapes]]

## Context

Real reports on disk show the investigation model converting epoch milliseconds to a date by
hand and getting it vague or wrong: `1781786117679` (`09:35:17 18/06/2026 BRT`, verified) was
narrated as "~2026-06-18/19"; another report said "~2026-09-05/06"; another said "~14:41 UTC" with
no date at all. The `## Linha do tempo` section only ever held first/last-occurrence and the
window, never the events inside the window — even though the model had read tools available to
fetch them. `## Evidência` cited a query in prose ("consultar a query X no Events Explorer")
without a clickable link, even when a deterministic link shape already existed (ADR-0011). And the
`## Corpo da issue` was a thin 5W2H that a second agent (`houston/fix_agent.py`) could not act on:
it never named the target repository, the observed volume, or a severity/criticality judgment.

## Decision

1. **Every timestamp is rendered by code, never by the model.** `houston/timestamps.py` (pure, no
   I/O) adds `format_ms(ms) -> "HH:MM:SS dd/mm/yyyy BRT (epoch <ms> · <ISO-8601 UTC>)"` — hour
   first, per the owner's explicit request. Not a fixed UTC-3: `zoneinfo("America/Sao_Paulo")`
   resolves `BRT` (-03:00) or `BRST` (-02:00, retired 2019-02-17) by the actual date, which matters
   because Error Tracking `first_seen` values reach back to 2022. `houston/agent.py`'s payload now
   carries pre-rendered `window_from`/`window_to`/`first_seen`/`last_seen` strings alongside the
   existing `*_ms` fields; the prompt tells the model to copy them verbatim and never compute a
   date from the `_ms` fields itself.
2. **Timestamps found via tool calls travel through a `{{ts:<value>}}` marker**, expanded by
   `houston/timestamps.py:canonicalize()` after the subprocess returns, before the PII gate or
   `houston promote` ever sees the text. A marker whose value doesn't parse is left visible
   verbatim and surfaced as a warning on stdout (`InvestigationResult.warnings`) — never silently
   dropped or guessed at. Bare ISO-8601 datetimes copied without a marker are also canonicalized
   (unambiguous, so converting them costs nothing and closes the most likely omission); bare
   13-digit digit runs are left untouched, since they may be ids and some already sit inside this
   project's own `from_ts=`/`to_ts=` deep-link URLs.
3. **Every source's `Finding` now carries `evidence_links`** (`houston/models.py:EvidenceLink`),
   built in the collector at collection time — same place ADR-0011 puts `datadog_url`, for the same
   reason: the model must never construct a Datadog URL itself. Error Tracking and Kubernetes carry
   one link each, mirroring `datadog_url`. Monitor findings carry two: the monitor status page, and
   a new `event_explorer_url` pinned to the collection window using
   `monitor_timeline_query(monitor_id) = "source:alert @monitor.id:{id}"` — deliberately **without**
   the collector's own `status:error OR status:warn` filter, because that filter is what makes the
   collector see triggers and miss `[Recovered]` events; the report's step-by-step timeline needs
   the whole cycle. The query shape itself was already verified live for ADR-0014's
   `monitor_evidence_query`; only the status filter was dropped.
4. **The `## Linha do tempo` section becomes a mandatory step-by-step reconstruction** of events
   inside the collection window, not just first/last occurrence — the prompt requires querying the
   window with the read tools (using `evidence_links[].query`) and listing each event
   (`[Triggered]`/`[Re-Triggered]`/`[Recovered]` for monitors, each Kubernetes event, each
   occurrence/version change for Error Tracking), each entry starting with a `{{ts:...}}` marker
   and ending with the link or exact query that proves it. `## Evidência` is likewise required to
   cite a link from `evidence_links`/`datadog_url`, never a model-constructed URL.
5. **`## Corpo da issue` gains a fixed outline** (the owner's own list, not strict 5W2H) so the
   issue is both human-readable and directly consumable by `houston fix`'s second agent: `###
   Descrição do incidente`, `### Causa raiz`, `### Linha do tempo` (with correlations — deploy/
   version, monitor state changes, related events), `### Evidências`, `### Ação recomendada`
   (naming the target repository from a new `target_repo` payload field — resolved via
   `houston/service_repos.py:resolve_repo`, moved out of `fix_agent.py` to avoid an
   `agent → fix_agent → agent` import cycle — or "infra, sem repositório de código" when null),
   `### Volume`, `### Severidade e criticidade`. The line cap relaxes from 50 to ~120; the section
   must stay last (`houston/cli.py:extract_issue_body` still splits to end-of-file) and must not
   open with a code fence.
6. **`houston promote` always adds `--label AIOPS`** to the printed `gh issue create` command, so
   every issue this project originates is filterable in `Medprev/medprev-product-backlog` — the
   label already exists on that repo ("Task aberta pelo agente de aiops da medprev"), verified live
   before writing the code.

## PII-gate reasoning

The canonical string's separators are load-bearing, not decorative. `_CARD_CANDIDATE` only matches
a bare digit run with **one kind** of `[ -]` separator; `/`, `:`, and `·` all fall outside that
class, so `18/06/2026`, `09:35:17`, and the ` · ` before the ISO tail each break candidacy on their
own. The literals `BRT (epoch ` and ` · ` around the epoch specifically stop it from being read as
part of a neighbouring digit run joined by a single space: `1234 1781786117679` (17 digits, one
separator) *is* card-shaped and Luhn-valid, and would trip the gate — the canonical string never
produces that shape because those literals sit between the epoch and anything next to it. The bare
13-digit epoch itself was already accepted by design (ADR-0004/0017). Verified with a 1,000-epoch
sweep through `format_ms()` in `tests/test_pii_gate.py` — zero hits.

## Consequences

### Good
- A report timestamp is now provably exact — rendered once, in one function, never re-derived by
  the model.
- The timeline and evidence sections carry real, clickable proof instead of prose descriptions of
  where to look.
- The issue body a promoted finding produces is the same document a second agent (`houston fix`)
  can act on without re-investigating.
- Every agent-originated issue is filterable by the `AIOPS` label.

### Bad
- The step-by-step timeline requires more tool calls per investigation, which can push a run closer
  to `--max-budget-usd`; watch `houston metrics` p95 duration/cost after the first runs on this
  format.
- Existing reports on disk keep the old format; no backfill (report bodies are paid model output,
  same precedent ADR-0011 set for not rewriting content on that backfill).

### Follow-up
A date the model computes in prose, with no `{{ts:...}}` marker and no bare ISO literal, is
undetectable by code. The prompt forbids it; if one is ever found in a real report, the mitigation
is the same escalation ADR-0011 defined for model-constructed URLs — strip model-written
`dd/mm/yyyy` dates in code rather than trusting the instruction alone.
