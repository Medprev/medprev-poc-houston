# ADR-0011: Deterministic Datadog deep links + report body content in Portuguese

**Status:** Accepted
**Date:** 2026-09-02
**Deciders:** Carla Cury (explicit request: real log validation link, and
"os textos devem ser em português... vai ficar melhor para comunicar com
o time")
**Decision style:** Two independent, explicit change requests from the
repository owner. The link addition is a pure addition; the language
change reverses an earlier decision that same owner made, which is her
call to make.
**Related:** [[0001-model-access-via-claude-code-cli]]

## Context

Two gaps in the reports themselves, not in the pipeline:

1. **No way to jump to the real evidence.** A report cited a query or a
   fingerprint, but validating it meant re-typing that query into Datadog
   by hand. Not acceptable for a report meant to support a real decision
   (promote or discard).
2. **Report body content was in English.** The original plan's own
   decision table ("Idioma do repositório") set English for everything in
   this repo, report content included. Carla is now reversing that
   specifically for report *prose* — front-matter keys/values, code,
   tests, ADRs, and commit messages are unaffected and stay English —
   because the actual audience for a report body and its issue draft is
   the team, in Portuguese.

For the link, three URL shapes exist, one per source, and each was
verified live in a real browser session against `app.datadoghq.com`
before being written into code — not assumed from the OpenAPI spec or
from memory, given how many silent schema-shape bugs this project has
already found that way (ADR-0007, 0008, 0009):

- **Error Tracking:** `https://app.<site>/error-tracking/issue/{issue_id}`
  — confirmed: loads the real issue detail page.
- **Kubernetes:** `https://app.<site>/event/explorer?query=<encoded>&from_ts=<ms>&to_ts=<ms>&live=false`
  — confirmed: without explicit `from_ts`/`to_ts`, the Event Explorer
  defaults to the past 15 minutes, which would show nothing for a finding
  whose evidence lives further back in a 96h window. `live=false` is
  required too, or the explorer keeps following "now" instead of the
  pinned range. The query is scoped to the finding's own namespace
  (`kube_namespace:{namespace}`), not the whole collector query — a link
  showing every namespace's warnings isn't "the link that shows the
  error."
- **Monitor:** `https://app.<site>/monitors/{monitor_id}` — confirmed:
  loads the real monitor status page, title matching the monitor's actual
  configured name.

## Decision

1. `houston/datadog_client.py` gains pure URL-builder functions
   (`error_tracking_issue_url`, `event_explorer_url`, `monitor_url`) and a
   public `DatadogClient.site` property. Each collector function computes
   the finding's `datadog_url` at collection time and carries it on
   `Finding`, alongside the real `window_from_ms`/`window_to_ms` (these
   were previously hardcoded to `0` in `Report.from_finding` — a real,
   silent bug, fixed as part of this change since the Kubernetes link
   needs the real window to pin its range).
2. `write_report()` injects `**Link do Datadog:** {url}` as the first line
   of the body, deterministically, in code — not asked of the model. The
   agent's prompt tells it the link already exists in the finding JSON and
   explicitly instructs it not to construct or guess one itself.
3. `houston/agent.py`'s `PROMPT` is rewritten in Portuguese: section
   headers (`## Causa raiz`, `## Linha do tempo`, `## Evidência`, `## Ação
   recomendada`, `## Corpo da issue`), the anti-hallucination and
   no-raw-log-paste rules, and the 5W2H issue-body instruction all carry
   over unchanged in substance, translated in wording. A new `## Linha do
   tempo` (timeline) section was added at Carla's request, sourced from
   the finding's own dates/versions, not invented.
4. The two code-generated stub bodies (`houston seed`'s "pre-existing
   debt" text, `houston investigate`'s incomplete-state message) are
   translated too, for consistency — they are report body content by the
   same definition.
5. A one-off (but reusable) migration, `scripts/backfill_datadog_url.py`,
   refreshed all 149 existing reports with the new `datadog_url` and real
   window fields, preserving each report's `state`, `body`, `cost`, and
   `issue` untouched. 149 of 151 updated; 2 skipped because their
   fingerprint had aged out of the current 96h collection window (their
   underlying signal no longer appears in a fresh `collect()` call, so
   there's no live `Finding` to refresh from — not a bug, a natural limit
   of a point-in-time backfill).

## Consequences

### Good
- Every report now carries a link that was actually confirmed, in a real
  browser, to show the right evidence at the right time range — not a
  guessed URL shape.
- The language change is scoped precisely: report prose only. Nothing
  else this project already decided (English code, tests, ADRs, commit
  messages, structured front-matter fields) changes.
- The already-investigated report (`et-114e7438`) kept its original
  English body untouched by the backfill — only structural fields
  (`datadog_url`, `window`) were refreshed. Re-investigating it later is
  what would give it a Portuguese body; the backfill was never meant to
  rewrite content.

### Bad
- Two reports permanently lost the ability to get a fresh `datadog_url`/
  window from this backfill mechanism, since their fingerprint no longer
  appears in a live 96h `collect()` call. Not a real loss — those
  fingerprints' original reports still exist and are still valid evidence
  of what was seen; only a hypothetical future re-backfill would need a
  wider collection window to reach them.

### Follow-up
None expected for the link mechanism itself. If a future report shows the
model constructing its own Datadog URL despite the prompt instruction not
to, that's the signal to also strip Anthropic model-generated `datadog.com`
URLs from the body as a code-level safeguard, not just a prompt request.
