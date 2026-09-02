# ADR-0013: Cost counts cache tokens, failed runs, and is aggregated by `houston metrics`

**Status:** Accepted
**Date:** 2026-09-02
**Deciders:** Carla Cury (found in a full review of the E0 verification
branch; every number below was produced by running the real CLI, not by
reading the code)
**Decision style:** Bug fix in the one measurement this PoC exists to make.
**Related:** [[0001-model-access-via-claude-code-cli]], [[0006-no-max-turns-flag-use-budget-and-timeout]]

## Context

ADR-0001 makes cost per finding the number that decides whether this
approach scales. Three separate defects meant that number was never
actually measured.

1. `input_tokens` read only `usage.input_tokens`. A real
   `claude -p --output-format json` run reported `input_tokens: 0` beside
   `cache_read_input_tokens: 10596` and `cache_creation_input_tokens: 13285`.
   Cache tokens are billed input; excluding them understated the metric by
   three orders of magnitude, and it shows on disk: every investigated
   report records 2-14 input tokens for a run that cost ~$0.32, and
   `houston metrics` printed `input tokens p50=8 p95=14`.
2. The non-zero-exit and timeout branches hardcoded `usd=0.0` and read
   `proc.stderr` for the reason. Verified by exhausting the budget on
   purpose: the CLI exits 1 with **stderr empty** and the whole envelope on
   stdout — `total_cost_usd: 0.138283`, `is_error: true`,
   `subtype: error_max_budget_usd`, `errors: ["Reached maximum budget"]`.
   So a budget-exhausted investigation was recorded as free, its report body
   read `Investigação não foi concluída: ` with nothing after the colon, and
   because `incomplete` is in `NEEDS_INVESTIGATION_STATES` while `cap()`
   re-ranks by volume, the same finding was first in line to be retried and
   charged again.
3. `metrics.py` contained no reference to `usd` at all. Every report writes
   `cost.usd`; nothing read it. The "~$0.24-$0.40/finding measured live"
   figure in CLAUDE.md had to be added up by hand — exactly what the
   module's own docstring says it exists to prevent.

## Decision

`input_tokens` is the total billed input (uncached + cache read + cache
creation), with the two cache components kept as their own front-matter
fields so the number stays auditable. The stdout envelope is parsed on
every path — success, non-zero exit, and timeout — and `usd`,
`duration_ms`, `usage`, `subtype` and `errors` are taken from it wherever
it exists. `exit 0` with `is_error: true`, or with no `result`, is
`incomplete`, not a report. `Metrics` carries `usd_total`, `usd_mean`,
`usd_p50`, `usd_p95` and a per-state breakdown, and `houston metrics`
prints them.

## Consequences

### Good
- Spend is now a computed number: `$1.5202` total, mean `$0.3801` over the
  4 paid findings on this branch, printed by `houston metrics`.
- A failed run reports what it spent and why it stopped, so budget
  exhaustion is visible instead of looking like a free failure.
- The cost of a quarantined report is counted too (ADR-0015).

### Bad
- The token counts already on disk stay understated: the envelopes that
  produced them are gone, so they cannot be recovered. Token percentiles
  over the existing corpus are not comparable to new ones; `cost.usd` is.

### Follow-up
`--max-budget-usd` stopping mid-investigation is now legible in the data.
If it turns out to be frequent, the lever is the budget or the prompt's
scope, not the accounting.
