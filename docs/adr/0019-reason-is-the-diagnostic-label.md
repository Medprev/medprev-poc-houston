# ADR-0019: `reason` is the diagnostic label; novelty and regression are their own facts

**Status:** Accepted
**Date:** 2026-09-02
**Deciders:** Carla Cury (found in a full review of the E0 verification
branch, by running `houston promote` and reading what it printed)
**Decision style:** Bug fix in the report contract.
**Related:** [[0008-kubernetes-fingerprint-at-namespace-granularity]], [[0011-datadog-links-and-portuguese-report-body]], [[0014-window-scoped-counts-and-per-finding-evidence]]

## Context

`Finding.reason` carries the diagnostic label of a finding: the Error
Tracking `error_type`, the monitor name, or the Kubernetes `Reason`.
`Report.from_finding` overwrote it with the string `"new"` or
`"regression"`. The label therefore never reached disk: all 151 reports
hold only `reason: new` (118) or `reason: regression` (33).

The consequences were visible where it matters most. `houston promote`
printed `--title '[error_tracking] regression in medprev-rest-api'` —
`BranchLaboratoryNotFoundException` appears nowhere, so every promoted
GitHub issue was titled by how new the finding was rather than by what
broke. `generate_site.py` renders the same field under a "Reason" column,
making that column a duplicate novelty flag on the page ADR-0005 governs.

Two adjacent defects in the same area:

- `regressed` was derived from the mere existence of the `regression`
  object, which is a permanent historical record. This repo's own fixture
  carries `regressed_at: 2025-11-10` and was still labelled a regression
  ten months later, so a long-stable error was escalated to the team as a
  fresh regression.
- `houston promote` extracted the issue body by splitting on
  `## Issue body`, while the prompt emits `## Corpo da issue`. Verified by
  running it: `--body` carried the entire report — root cause, timeline,
  evidence, recommended action and the nested code fence — instead of the
  under-50-line 5W2H body. 7 of 10 investigated reports use the Portuguese
  heading; `tests/test_cli_promote.py` pinned the stale English one.
- The pod-hash strip in `k8s_fingerprint` was still applied after ADR-0008
  moved the source to namespace granularity, and its `-[0-9]+$` branch
  collapsed `medprev-web-app-2` onto `medprev-web-app`, where
  dedup-by-file-existence then suppressed the second namespace permanently.

## Decision

`reason` keeps the diagnostic label. `novelty` (`new` | `regression`) is a
separate front-matter field, rendered as its own column and used as a title
prefix only when it is a regression. `regressed` is true only when
`regression.regressed_at` falls inside the collection window.
`extract_issue_body` reads both headings and unwraps a wrapping code fence.
`k8s_fingerprint` no longer strips anything.

## Consequences

### Good
- A promoted issue is titled by the error, and its body is the 5W2H body
  the prompt asked for, as markdown rather than one literal code block.
- Namespaces ending in a digit stop disappearing.

### Bad
- The 151 reports on disk carry a `reason` that is really a novelty flag.
  Fixing the code does not fix the corpus: `scripts/backfill_datadog_url.py`
  restores the real label for any report whose finding is still inside the
  current window, and the rest keep the old value until they are
  re-investigated. Reports written before `novelty` existed have no such
  field; readers use `.get`.
