# ADR-0032: The CLI is argparse and wiring; use cases are callable without it

**Status:** Accepted
**Date:** 2026-09-13
**Deciders:** Carla Cury (Move C of the dependency-inversion refactor tracked in #29; designed and
verified in `refactor/pipeline-out-of-the-cli`, against the `store`/`runner` collaborator shapes
from ADR-0030 and ADR-0031)
**Decision style:** Design fix — inverts a dependency direction; no behavior change verified by
the unedited E2E test bodies and assertions from ADR-0029.
**Related:** [[0029-refactor-net-anchored-at-boundaries-that-do-not-move]],
[[0030-reports-dir-becomes-an-injected-report-store]], [[0031-model-runner-is-a-port]],
[[0028-promote-files-the-issue-behind-fail-closed-guards]]

## Context

`houston/cli.py` held six `cmd_*` functions that mixed three concerns: argparse's `Namespace` as
the only interface, ~85% business logic (deciding what to collect, what state a report should
carry, what blocks a promotion) inside each one, and `print`/`sys.stderr` calls interleaved with
that logic. Two consequences, both measured before this PR:

1. **`tests/test_cli_investigate.py` could only assert that mocks were called.** Its four tests
   stacked five `@patch` decorators each (`houston.cli.collect`, `.cap`,
   `.filter_needing_investigation`, `.agent_investigate`, `.write_report`) and checked
   `mock_write.call_args.args[0].state == "new"` — a statement about which object was handed to a
   `MagicMock`, not about what reached disk.
2. **`cmd_fix` and `cmd_promote --create` had zero tests.** `cmd_fix` was 58 lines, the single
   largest untested function in the package before this PR; ADR-0028 documents `--create`'s four
   fail-closed guards in prose, but nothing exercised `promotion_blockers` or the full
   file-the-issue-and-record-it path directly.

## Decision

`houston/pipeline.py` holds the use cases as plain functions taking their collaborators as
parameters — `collect_fn`, `investigate_fn`/`fix_fn`, `resolve_repo_fn`, the `store`/`runner`
Move A/B already introduced — and returning a result object instead of printing:

```python
def seed(collect_fn, *, window_hours, store=DEFAULT_STORE) -> SeedOutcome: ...
def plan_run(collect_fn, *, window_hours, max_findings, store=DEFAULT_STORE) -> RunPlan: ...
def investigate_findings(collect_fn, investigate_fn, resolve_repo_fn, *, ...,
                          on_start=lambda *_: None) -> InvestigationRun: ...
def build_promote_command(fingerprint, *, store=DEFAULT_STORE) -> PromoteCommand: ...
def promote_report(fingerprint, *, account, required_account, create_issue_fn,
                    store=DEFAULT_STORE) -> str: ...
def fix_report(fingerprint, *, issue, fix_fn, resolve_repo_fn, runner, ...,
               notify_fn=lambda *_: None, store=DEFAULT_STORE) -> FixOutcome: ...
```

`PipelineError` is the one exception every refusal raises — no report at that fingerprint, wrong
state, a promotion blocker, `gh`/the agent failing. `cli.py`'s six `cmd_*` functions catch it once
each and print the message that used to be written inline, preserving every stderr string and exit
code.

**What deliberately stayed in `cli.py`, not moved here:** the three `gh` subprocess calls
(`active_gh_account`, `create_issue`, the fix-PR issue comment). Same reasoning ADR-0031 applied to
`fix_agent.py`'s five `git` calls: they are plumbing to an external tool, not a use case, and
extracting a `gh`/`git` port is explicitly out of scope for this refactor (tracked in #29).
`promote_report` and `fix_report` take `create_issue_fn`/`notify_fn` as injected callables instead
— the blocker/state-writing logic they wrap is the use case; the subprocess call underneath it is
not.

`on_start`, a callback fired once per finding before the (slow, paid) agent call, is what lets
`cmd_investigate` still print its `[i/N] fingerprint...` progress line without `pipeline.py`
knowing anything about stdout.

## Consequences

### Good

- `tests/test_cli_investigate.py` (4 tests, 20 patch decorators, asserted only that mocks were
  called) is deleted, not migrated — it carried no claim `tests/test_pipeline.py` and
  `tests/test_e2e_pipeline.py` don't already make more strongly. `tests/test_pipeline.py` (new, 19
  tests) drives `investigate_findings`/`seed`/`plan_run`/`promote_report`/`fix_report` directly
  with fakes and asserts on the real `InvestigationRun`/`SeedOutcome`/report bytes on disk, not on
  which internal function got called.
- `cmd_fix` and `cmd_promote --create` have real tests for the first time:
  `test_fix_report_refuses_a_report_that_is_not_promoted`,
  `..._refuses_without_an_issue_url`, `..._refuses_a_service_with_no_repo_mapping`,
  `..._records_the_pr_and_notifies_the_issue`, plus four `promotion_blockers` tests and two
  `promote_report` tests (files-and-records, refuses-without-filing-when-blocked).
- `houston/cli.py` shrank from 470 lines (252 statements) to roughly a third of its logic:
  164 statements, 82% line coverage (up from 81%, on a smaller, now argparse-and-wiring-shaped
  file). `houston/pipeline.py` starts at 94% line coverage. Package-wide coverage rose from 89% to
  91% — Move C did not just relocate code, the new direct-call tests reach branches the
  `cmd_*`-level tests never triggered.
- 237 tests total (222 before this PR, minus 4 deleted, plus 19 new). The golden and E2E tests from
  ADR-0029 pass unedited — the objective proof this PR changed no observable behavior.
- Verified against the real, tracked 153-report corpus: `mise run metrics` prints the same numbers
  as before this branch, and `mise run promote <fingerprint>` against a real seeded report prints
  the same `gh issue create` command shape. `git diff --stat` over `reports/` is empty.

### Bad

- `investigate_fn`/`fix_fn` are typed as `Callable[..., object]` rather than a precise `Protocol`
  matching `agent.investigate`'s/`fix_agent.fix`'s full keyword signature — Python's structural
  typing for a multi-keyword-argument callable doesn't have a clean `Callable[...]` spelling, and a
  `Protocol` with `__call__` would need to restate every keyword argument name. Accepted as a
  precision gap: the two real call sites (`cli.py`) pass `agent_investigate`/`agent_fix` directly,
  and `tests/test_pipeline.py` catches a shape mismatch at test-run time via any fake that expects
  different keywords.
- `resolve_repo` is injected as `resolve_repo_fn` even though it is a pure function reading a
  committed YAML file with its own six passing tests — a stricter reading of "only inject genuine
  swap points" would import it directly in `pipeline.py` instead. Kept as a parameter because
  `investigate_findings` calls it with one shape (`resolve_repo_fn(finding.service)`) and
  `fix_report` with another (`resolve_repo_fn(service, text)`) — `houston.service_repos.resolve_repo`
  already accepts both via a defaulted second argument, so in practice this is injecting the real
  function everywhere it's used today, not a live seam.

### Follow-up

- None planned for this refactor sequence (#29) beyond this PR — Moves A, B, and C are the three
  the tracking issue named. A subpackage reorganization (`houston/findings/`, `houston/datadog/`,
  `houston/claude/`, `houston/reporting/`) was scoped out of all three moves at the start and
  remains a separate, later decision.
