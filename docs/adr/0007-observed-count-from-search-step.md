# ADR-0007: `observed_count` reads `total_count` from the search step, not the issue-detail step

**Status:** Accepted
**Date:** 2026-09-01
**Deciders:** Carla Cury (surfaced by the E4 agent itself, fixed same session)
**Decision style:** Bug fix. Found because the E4 agent's own investigation
of a real finding flagged a discrepancy between the finding's
`observed_count: 1` and the 287,657 occurrences it found by querying
Datadog directly — the tool built to catch this kind of thing caught a bug
in itself.
**Related:** [[0004-pan-gate-scans-common-card-lengths-only]]

## Context

E1's collector originally read `total_count` off the issue-**detail**
response (`GET /issues/{id}`). Per the OpenAPI schema already confirmed in
E0 (`IssueAttributes`), that response has no `total_count` field at all —
the field only exists on the **search**-step result shape
(`error_tracking_search_result.attributes.total_count`). Every finding
therefore silently fell back to the collector's own default of `1`,
regardless of real volume.

Consequence: E3's `cap()` sorts findings by `observed_count` descending to
prioritize the highest-volume signal for investigation. With every finding
reporting `1`, that sort did nothing — the cap kept whichever 15 findings
happened to sort first under a stable sort, not the highest-volume ones,
defeating the stated design intent ("corta por volume decrescente").

## Decision

`DatadogClient.search_error_tracking_issues` (renamed from
`search_error_tracking_issue_ids`) now returns `{issue_id: total_count}`
from the search step. The collector carries that count into
`Finding.observed_count` instead of reading (a nonexistent field from) the
detail step.

## Consequences

### Good
- `cap()` now actually orders by real volume. Re-seeded all 101 real
  findings: 0 remain at the stale `count: 1`.
- Caught the moment an unrelated part of the system (E4's agent) surfaced
  the discrepancy in a real report body — a small piece of evidence that
  the "evidence as claim+query pairs" design (E5) does what it's for: a
  wrong number is falsifiable by anyone re-running the query, including
  the model itself.

### Bad
- `observed_count` still isn't the same number the E4 agent found for this
  finding (48,280 after the fix vs. the model's 287,657) — expected, not a
  further bug: the collector's count is scoped to its 96h search window,
  the model's was an unbounded historical query it chose to run. Two
  different, both-correct definitions of "how many," not a discrepancy to
  resolve.

### Follow-up
None expected — regression test
(`test_observed_count_comes_from_search_step_not_issue_detail`) pins the
correct source going forward.
