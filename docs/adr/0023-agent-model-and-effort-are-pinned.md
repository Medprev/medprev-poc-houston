# ADR-0023: The agent subprocess pins its model and effort

**Status:** Accepted
**Date:** 2026-09-10
**Deciders:** Carla Cury (found by a run of three findings that spent $2.41
and produced no investigation; every price below was measured against the
real CLI, 2.1.267, not read off a table)
**Decision style:** Bug fix in the one measurement this PoC exists to make.
**Related:** [[0001-model-access-via-claude-code-cli]],
[[0006-no-max-turns-flag-use-budget-and-timeout]],
[[0013-cost-includes-cache-tokens-and-failed-runs]]

## Context

`houston/agent.py` and `houston/fix_agent.py` built their `claude -p`
command without `--model`. The CLI then resolves the model from the
operator's own settings (`~/.claude/settings.json`), so the price of a
pipeline run was set by whatever model the operator had last selected
interactively in their terminal — a value this repo neither controls nor
records.

On 2026-09-10 that setting was `"model": "opus[1m]"`, with
`modelSettings.claude-opus-5.effortLevel: "xhigh"`. All three findings in
the run died at the `$0.50` cap in `error_max_budget_usd`:

| finding | spend | duration | output tokens |
|---|---|---|---|
| `mon-260376188` | $0.5139 | 7.5s | 0 |
| `k8s-…-FailedGetResourceMetric-…-airflow` | $0.8022 | 20.3s | 204 |
| `et-161c8400-…` | $1.0915 | 27.5s | 193 |

Completed runs already on disk take 87–148s and produce 3,760–11,628
output tokens for $0.24–$0.42. These three died during boot: the budget
was gone before the first tool round-trip returned.

Measured live, same trivial prompt through the same subprocess shape:

| model | effort | cache creation | output | cost |
|---|---|---|---|---|
| `claude-opus-5[1m]` (inherited) | xhigh | 35,438 | 657 (277 thinking) | **$0.3915** |
| `claude-sonnet-5` (`--model sonnet`) | medium | 18,294 | 33 (0 thinking) | **$0.0777** |

**5.04x**, for answering "responda apenas: ok". Both figures reconcile
exactly against list price — Opus 5 $5/$25 per MTok, Sonnet 5 $2/$10, cache
write at 2x for the 1-hour TTL the CLI uses, cache read at 0.1x — so no 1M
context premium is in play; these prompts are far under the 200K threshold
that would trigger one. The gap is the tier and the effort level, nothing
exotic.

ADR-0013's follow-up said that if budget exhaustion turned out to be
frequent, "the lever is the budget or the prompt's scope, not the
accounting." It listed two levers and the real one was a third: the model.
Neither the prompt nor `--max-budget-usd` changed in this run.

## Decision

Both subprocesses pass `--model` and `--effort` explicitly. The defaults
live in code — `sonnet`/`medium` for the investigation agent, `sonnet`/`high`
for the fix agent, which writes code rather than describing it — and are
overridable per run with `houston investigate --model/--effort` and
`houston fix --model/--effort`. `CLAUDE_EFFORT` is scrubbed from the
subprocess env alongside `CLAUDECODE`, for the same reason.

Reports record `cost.model`, taken from the envelope's `modelUsage` key
(the resolved id, not the alias asked for) and falling back to the
requested alias when the run died before any billed request. `houston
investigate` prints the model and effort in its opening line, before
spending anything.

Sonnet is the default because it is the tier that produced every report
promoted so far, and the tier the $0.50 cap is sized for. Estimated per
finding on the token profile of a real completed run (`mon-178729377`,
52,461 cache-creation + 130,104 cache-read + 7,311 output), at list price
with the current 1-hour cache TTL: **~$0.31 on Sonnet 5**, **~$0.77 on
Opus 5** before counting the extra output that `xhigh` produces. Running
Opus is a supported choice, but it is a choice that has to move
`--max-budget-usd` with it — roughly $1.50 — and it changes the phase's
cost-per-finding gate by about 2.5x.

## Consequences

### Good
- Cost per finding is a property of this repo again, not of the operator's
  terminal. `houston metrics` measures a number the next run reproduces.
- The model is on record next to the spend it caused. Recovering it for
  this incident took reverse-engineering three reports against a price
  list; `cost.model` makes that a lookup.
- The three findings return to the queue with no manual step: `incomplete`
  is already in `NEEDS_INVESTIGATION_STATES`.

### Bad
- Every report written before this ADR has `cost.model: null`. The model
  behind those numbers is inferable from cost arithmetic but is not
  recorded, so spend is not strictly comparable across the boundary.
- Pinning means the pipeline does not pick up a better default model on
  its own. Moving tiers is now a deliberate edit, which is the point, but
  it is also a thing that can be forgotten.

### Follow-up
The `usage` block on a budget-aborted run does not add up to its own
`total_cost_usd` — `et-161c8400-…` records 20,999 cache-creation, 13,885
cache-read and 193 output tokens, which price at ~$0.22 on Opus 5 against
a reported $1.0915. `total_cost_usd` is cumulative across the run's
requests while that token block evidently is not, so token percentiles
from aborted runs understate. `cost.usd` remains the trustworthy field, as
ADR-0013 already concluded for a different reason.
