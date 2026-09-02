# ADR-0020: Transient failures retry, and the detail fan-out follows dedup

**Status:** Accepted
**Date:** 2026-09-02
**Deciders:** Carla Cury (found in a full review of the E0 verification
branch, by running `houston run` against the real account until it broke)
**Decision style:** Reliability fix.
**Related:** [[0007-observed-count-from-search-step]]

## Context

`docs/e0-verification.md` states the contract: the Error Tracking detail
call happens once per **new** finding, because "achados já vistos são
descartados pela dedup antes do detalhe". The code did the opposite —
`collect()` issued a `GET /issues/{id}` for every search hit and `cli.py`
filtered afterwards, so a run made about 102 sequential detail calls where
the design promised 0-10.

Every one of those calls was a chance to lose the run.
`requests.get`/`post` were wrapped in `raise_for_status()` with no retry,
no backoff and no `Session`. Reproduced live: `houston run --window-hours 2`
died with an unhandled `requests.exceptions.HTTPError: 503 Service
Unavailable` on the first detail GET, and the identical call then returned
200 four times in a row — transient upstream noise, not a real failure.
There were zero `try`/`except`/retry constructs in the client or the
collector.

## Decision

`_with_retries` wraps every request: 3 attempts, exponential backoff
(honouring `Retry-After` when present), retrying `429` and `5xx` plus
connection and timeout errors. A 4xx that is not 429 raises on the first
attempt — a revoked key or a malformed query fails the same way three
times, and retrying it only burns wall-clock.

`collect_error_tracking_findings` takes a `should_enrich` predicate, which
`houston run`/`investigate` fill with dedup's own
`needs_investigation`, and `houston seed` with "has no report yet". A
finding that is not enriched still carries what the search step returned —
fingerprint, volume, deep link — and nothing invented for the rest, so it
still counts and still dedups. The backfill script leaves the predicate
unset, because it needs every field on every report.

## Consequences

### Good
- One transient 503 costs a retry instead of the whole run. This is the
  mitigation that matters *today*: measured on a live 2h window, the run
  still makes 67 detail calls, because 147 of the 151 reports on disk are
  `state: seeded` and a seeded finding legitimately still needs
  investigation (ADR-0010). Retries are what makes 67 sequential calls
  survivable.
- The fan-out now follows the same rule as the spend it precedes, so it
  shrinks as findings reach decided states: 71 ET findings, 67 enriched
  with the predicate against 71 without it today, and 0 once the corpus is
  decided. It no longer grows with the size of the backlog.

### Bad
- `houston run`'s printed total still counts unenriched findings, so
  `service`/`reason` show as `None`/`not enriched` for anything already
  decided. That is honest about what was fetched, but it means the run
  output is no longer a full inventory of every finding's attributes.
- Retries can add up to a few seconds of backoff to a run that is already
  bounded only by wall-clock.
