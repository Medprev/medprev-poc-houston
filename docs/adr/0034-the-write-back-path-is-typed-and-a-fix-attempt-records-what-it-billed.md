# ADR-0034: The write-back path is typed, and a fix attempt records what it billed

**Status:** Accepted
**Date:** 2026-09-17
**Deciders:** Carla Cury (C2 of the deepening sequence tracked in #37, on top of
[[0033-the-report-has-a-read-path]], whose Follow-up section names this PR)
**Decision style:** Design fix — replaces an untyped door into `reports/` with the two transitions
that actually go through it, and closes #34. One behavior addition ships with it: the fix agent's
spend reaches disk and `houston metrics`, which it never did.
**Related:** [[0033-the-report-has-a-read-path]], [[0030-reports-dir-becomes-an-injected-report-store]],
[[0023-agent-model-and-effort-are-pinned]], [[0013-cost-includes-cache-tokens-and-failed-runs]],
[[0001-model-access-via-claude-code-cli]]

## Context

After ADR-0033, `reports/` had one reader and two writers: `write_report` (gated, typed) and
`update_front_matter(path, **fields)` (ungated, untyped, in `pipeline.py`). The second one is where
this PoC's two open data bugs lived.

1. **#34 — a failed retry erased a PR that exists.** `fix_report` wrote
   `update_front_matter(path, fix_pr=None, fix_state="incomplete")` whenever an attempt came back
   with an error. Three of the 153 committed reports carry a real PR URL —
   `et-082448ee…` → `medprev-web-app/pull/1372`, `et-36dac142…` → `/1373`,
   `et-89045986…` → `/1371`. A retry is not hypothetical: `fix_agent._count_existing_attempts` and
   `_branch_name`'s `-v2` suffix exist precisely because a finding gets fixed more than once. The
   untyped signature is what made "erase it" expressible at all.

2. **No dollar of `houston fix` reached `houston metrics`.** `FixResult.usd` existed and was written
   nowhere; `fix_report` recorded `fix_pr`/`fix_state` and dropped the rest. Measured on the corpus:
   `et-082448ee…` carries `fix_state: pr_open` next to `usd: 0.349` — the *investigation's* price,
   while the fix ran against a `$3.00` cap. The number this PoC exists to establish (ADR-0001) was
   undercounted by everything the fix agent has ever spent. `FixResult` also had no `model` field,
   so recording the dollars alone would have reproduced exactly the gap ADR-0023 was written about.

3. **The door itself.** `update_front_matter` took `**fields` with no validation, lived in a
   use-case module rather than with the report contract, and wrote through a bare `Path` — outside
   `ReportStore` and therefore outside `_filename`'s path-safety check.

## Decision

**Two named writers replace the generic one**, in `frontmatter.py`, where the rendered shape is
already known (ADR-0033; putting them on `ReportStore` would invert the `report_store ← frontmatter`
direction ADR-0030 fixed):

- `record_promotion(path, issue_url)` — the report now has an issue in the shared backlog.
- `record_fix_attempt(path, *, pr_url, state, cost)` — one `houston fix` attempt.

`update_front_matter` is deleted, and with it `pipeline.py`'s `yaml` import: every YAML write in the
package is now in `frontmatter.py`.

**#34 is closed by the signature, not by a guard.** There is no argument that says "erase the PR
URL". `fix_pr` is written when an attempt produced one and left alone otherwise; `fix_state` stays
with it, because a recorded PR describes *the finding* while `incomplete` would describe *the
attempt*. A first attempt that fails still writes `fix_state: incomplete` — the state only stands
still when there is a PR to protect. The pointer is singular, so a retry that *does* open a second PR
replaces the URL; what is impossible is zeroing it.

**`fix_attempts` counts the runs the total is made of.** Freezing `fix_state` behind an open PR is a
deliberate deviation from #34's own prescription ("don't write `fix_pr` on the failure path, write
only `fix_state`"), and it costs something: a retry that fails behind an open PR changes no state at
all. The counter is what keeps it visible, and it is also what makes a double write of one run
detectable — nothing on disk identifies a run, so `record_fix_attempt` must be called exactly once
per agent run.

**`fix_cost` is a second cost block, and it accumulates.** Every attempt bills whether or not it ends
in a PR, so the second attempt adds to the first rather than replacing it. It is kept apart from
`cost` because the two runs are billed on different pinned tiers (sonnet/`medium` for the
investigation, sonnet/`high` for the fix), and a dollar figure is uninterpretable without the model
that produced it (ADR-0023) — so `FixResult` gains the `model` field `agent.py` already recorded,
through the same `_billed_model` it already imports.

**The key is rendered only when there is one, because presence is the signal.** `metrics.compute`
reads `if r.fix_cost` as "a fix ran on this finding". An unconditional zeroed block would report a
fix run on all 153 committed reports, 150 of which never had one — and would change the bytes
`tests/golden/report_new.md` freezes. `_cost_block`/`_cost_from` render and parse both blocks, so the
fix's cost cannot drift from the investigation's.

**One mapping from an agent run to a `Cost`.** `billed(run)` reads the seven numbers both
`InvestigationResult` and `FixResult` report under the same names, behind a `BilledRun` Protocol that
states the shape. The investigation path used to copy those seven fields onto `report.cost` by
assignment after construction. A rename on either result class now fails a test instead of silently
zeroing a cost field. This settles the *duplication* ADR-0033 pointed at, not the debt that ADR
prescribed: `Report.from_finding` still has no `cost` parameter, so the cost is still attached after
construction and `frozen=True` is still not mechanical.

**The patch is written beside the file and renamed over it.** `write_text` truncates before writing,
and this path now runs on every fix attempt over a body that was already paid for and exists nowhere
else.

**`houston metrics` reports the two spends apart.** `usd_total` keeps meaning investigation spend;
`fix_usd_total` and `with_fix_run` are new, `usd_grand_total` adds them. Folding the fix into
`usd_total` would have made the per-finding investigation cost stop answering the question it exists
to answer.

## Consequences

### Good

- #34 cannot recur: no caller can express *zeroing* `fix_pr` (a real PR replaced by `None`). A retry that opens a second PR still replaces the URL -- see "Bad" below. Pinned by
  `test_a_failed_attempt_never_erases_the_pr_a_previous_one_opened`, which also asserts the failed
  retry's spend was added.
- 277 tests pass (263 before, +14). `tests/test_report_corpus.py` is unedited and every existing
  assertion in `tests/test_report_golden.py` is untouched — the ADR-0029 rule that proves the report
  bytes did not move — and `mise run metrics` over the real 153-report corpus prints output
  byte-identical to the pre-change checkout, `diff`-verified. `ruff` clean.
- The second rendered shape gets its own golden. `tests/golden/report_fix_patched.md` freezes what a
  patched document looks like: the four fix keys filled in the order `to_markdown` renders them, and
  the investigation's front-matter, the injected link line and the body exactly where they were.
- The round-trip test from ADR-0033 caught `fix_cost` the moment it was added and refused to pass
  until the field was exercised on both sides. That is the invariant working as designed.
- `houston fix`'s cost is now measurable per finding, which is what lets the PoC state a fix's price
  the way it already states an investigation's.
- The investigation path's seven-line cost assignment block disappears into `billed()`, so both agent
  runs reach `Cost` through one mapping instead of two copies that could drift apart.

### Bad

- **`fix_pr` is a single pointer.** A retry that opens a second PR replaces the first URL, which then
  survives only on the issue the fix commented on — not on the report that caused it. Pinned by
  `test_a_retry_that_opens_a_second_pr_points_the_report_at_the_new_one`, so it is a decision rather
  than a discovery. A history (`fix_prs: []`) belongs with C3's state machine.
- **Nothing refuses a second $3.00 run on a finding that already has an open PR.** `fix_report` only
  checks `state == "promoted"`, and `_count_existing_attempts` plus the `-v2` branch suffix exist
  because a retry is expected. On a PoC whose reason to exist is establishing cost per finding, that
  is a real hole — pre-existing, and now measurable per finding through `fix_attempts`, which is what
  a refusal would read.
- **The three fix runs already on disk are unrecoverable.** Their spend was never written anywhere,
  so `fix_usd_total` starts at `0.0` against three PRs that were really paid for. Only future runs
  are counted.
- **A mixed-tier retry sums into one number.** `fix_cost` accumulates across attempts while `model`
  keeps the latest attempt's. Retrying with `--model opus` after a sonnet attempt produces a total
  whose model label is true only of the last run — the same caveat ADR-0023 raised, now for the fix
  path. The same applies to every number in the block: `duration_s` is the sum of the attempts'
  wall-clock, while the investigation's `cost.duration_s` is one run's. `fix_attempts` is the
  denominator that keeps those totals readable; a per-attempt list is not worth its cost at three fix
  runs total.
- **`fix_cost` is the first key whose presence depends on data.** Two reports written by the same
  code can now differ in shape. The alternative moved bytes in 149 files.
- **`fix_state`'s vocabulary still has no owner.** `Report`'s docstring lists
  `attempted | pr_open | merged | rejected | incomplete`; only `pr_open` and `incomplete` are ever
  written, and nothing records that a human merged or rejected the PR. Unchanged here, and now
  visible: that is C3's job in #37.
- **The gating half of the debt is re-deferred.** ADR-0033's follow-up allocated "typing and gating"
  of this door to this PR. Only the typing shipped: both writers still take a bare `Path`, so
  `ReportStore._filename`'s path-safety check does not apply to them. Every caller passes
  `store.path(fingerprint)`, which does check — the type does not enforce it, and C7 now owns it.

### Follow-up

- C3 (the report's state machine) is where `state` and `fix_state` get one owner and where the
  missing transitions — a PR merged, a PR rejected — become writable.
- `record_promotion`/`record_fix_attempt` could take `(store, fingerprint)` instead of a `Path`,
  which would close the path-safety gap above. It belongs with C7's composition work, where the
  store stops being a default argument.
