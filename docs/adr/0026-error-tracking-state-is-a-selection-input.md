# ADR-0026: An Error Tracking issue's state is a selection input

**Status:** Accepted
**Date:** 2026-09-10
**Deciders:** Carla Cury (found by the ADR-0024 validation run, which
reported that the finding it was investigating had already been marked
`IGNORED` by a person; every number below was measured live against
`/api/v2/error-tracking/issues`)
**Decision style:** The pipeline stops re-deciding questions a human answered.
**Related:** [[0007-observed-count-from-search-step]],
[[0018-cap-ranks-severity-then-round-robins-sources]],
[[0020-retry-transients-and-fan-out-only-when-investigable]],
[[0024-investigation-correlates-logs-and-classifies-noise]]

## Context

`et-161c8400` was investigated three times, for `$1.54` of real quota, and
the third run found this in the issue's own activity timeline:

> state_change, `FOR_REVIEW` → `IGNORED`, 2026-09-10T16:21:31.495Z
> comment: *"Isso é um ruido gerado pelo recaptcha não autorizado, não é
> um erro e não deve ser tratado como incidente"*

Someone had triaged it in Datadog before the pipeline spent anything on
it. The collector never read `state`, so the dismissal was invisible.

`state` is a top-level attribute of the issue-detail response, alongside
`error_type` and `first_seen`. It does not exist on the search result,
which returns only `{id, total_count}` (ADR-0007) — so it can only be read
in the step the collector already runs for every finding that could still
be investigated (ADR-0020). Reading it costs no additional call.

Measured over one 96h window of `service:medprev-rest-api`, 106 issues:

| `state` | Issues | Events behind them |
|---|---|---|
| `OPEN` | 100 | 38,267 |
| `IGNORED` | 3 | **52,820** |
| `ACKNOWLEDGED` | 2 | 416 |
| `EXCLUDED` | 1 | 36 |

Three dismissed issues carry more events than all hundred open ones
together. `cap()` ranks by volume within a (tier, source) group
(ADR-0018), so those three do not merely waste a slot — they take the
slots, and they take them from exactly the findings a human has *not* yet
looked at. The default `--max-findings` is 5.

`ACKNOWLEDGED` is not a dismissal. It records that someone picked the
issue up, which is the opposite of "do not spend anything here".

## Decision

`collect_error_tracking_findings()` drops an enriched issue whose `state`
is in `DISMISSED_ISSUE_STATES` — `IGNORED` or `EXCLUDED`. `OPEN` and
`ACKNOWLEDGED` stay in the queue.

The filter sits after the detail call, not before it, so ADR-0020's
contract is unchanged: a finding dedup already excluded never pays for the
call, and therefore never has its state read either.

Only the four states observed live are named. The set is a `frozenset`
constant rather than a condition inline in the loop, so a state Datadog
adds later is one edit in one place.

## Consequences

The cap's slots go to findings nobody has judged yet, which is the only
population where an investigation can tell the operator something new.

`false_positive_rate` in `houston metrics` gets narrower and more honest.
It reads `promoted` vs `discarded` (ADR-0015), and a dismissed issue that
the pipeline investigates lands as `discarded` — inflating the rate with
findings that were never candidates. Those no longer enter the count.

The pipeline now depends on a field a person edits in a UI, which cuts
both ways. A wrongly ignored issue becomes invisible to Houston as well as
to the Error Tracking inbox — the dismissal is trusted, not re-litigated.
That is the intended reading: the human decision is the input.

An issue dismissed *after* Houston already wrote its report keeps that
report. Dedup is a file on disk (`reports/{fingerprint}.md`), and nothing
here reaches back to delete one; the operator resolves it the way
ADR-0015 already describes, by setting the report's own state.
