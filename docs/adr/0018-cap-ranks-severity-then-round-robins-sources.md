# ADR-0018: The cap ranks by severity tier, then round-robins across sources

**Status:** Accepted
**Date:** 2026-09-02
**Deciders:** Carla Cury (found in a full review of the E0 verification
branch, measured on the real 151-report corpus)
**Decision style:** Design fix — the pipeline had a prioritization policy
nobody had chosen.
**Related:** [[0007-observed-count-from-search-step]], [[0009-monitor-events-nested-schema-and-severity-signal]]

## Context

`cap()` is the only prioritization in the pipeline, and it sorted the mixed
finding list by `observed_count` alone. That number counts three
incommensurable things: errors in the window (Error Tracking), warning
events in the window (Kubernetes), and alert notifications (Monitor).

Measured on the corpus: the top 16 findings by `observed_count` were all
`error_tracking`; the first `kubernetes` finding ranked 17th (1152) and the
largest `monitor` finding had 45. Every report ever investigated is
`error_tracking`. With the deliberately small `--max-findings 5`, a
P1/P2-tagged monitor alert was roughly 9-10 runs and $12-15 of spend away
from ever being looked at, while a four-year-old 401-noise issue was picked
first every time.

Meanwhile `severity` is computed three different ways at real effort — one
of them the entire subject of ADR-0009's live investigation — and then only
stored, rendered, and sent to the model. No decision read it.

## Decision

Rank by severity tier first (`high`, `medium`, `low`, then anything else).
Inside a tier, round-robin across sources, and inside one (tier, source)
group order by descending `observed_count` — the only place where the
numbers are comparable. Ties break on fingerprint, so the order is
deterministic.

## Consequences

### Good
- A P1/P2 monitor alert now outranks high-volume medium-severity noise, and
  every source present in a tier gets a slot within the cap.
- `severity` finally drives a decision, which is what ADR-0009 paid for.

### Bad
- A very high-volume `medium` finding now waits behind a low-volume `high`
  one. That is the intended trade, and it makes the severity computation
  load-bearing: a source that mislabels severity now mis-prioritizes real
  work. ADR-0009's monitor rule (the `priority:pN` tag, status as fallback)
  is the one most worth re-checking against reality.
- Error Tracking severity is still just `is_crash` -> high/medium, which is
  coarse. Worth revisiting now that it matters.
