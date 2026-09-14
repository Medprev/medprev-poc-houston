# ADR-0032: The CLI is argparse and wiring; use cases are callable without it

**Status:** Accepted
**Date:** 2026-09-13
**Deciders:** Carla Cury (Move C of the dependency-inversion refactor tracked in #29; designed and
verified in `refactor/pipeline-out-of-the-cli`, against the `store`/`runner` collaborator shapes
from ADR-0030 and ADR-0031)
**Decision style:** Design fix — inverts a dependency direction. Report bytes are unchanged, proven
by the unedited E2E test bodies from ADR-0029; operator-facing stdout/stderr *ordering* is not
something those tests could see, and preserving it needed the callbacks described below.
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
2. **`cmd_fix` had zero tests.** At 58 lines it was the single largest untested function in the
   package. `cmd_promote --create` was not untested — `tests/test_cli_promote.py` covered it with
   seven tests through the CLI, including all four ADR-0028 guards — but nothing called
   `promotion_blockers` or the file-the-issue-and-record-it path directly, so both were reachable
   only through a `Namespace` and a patched `subprocess`.

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

`PipelineError` is what a refusal raises — no report at that fingerprint, wrong state, `gh` or the
agent failing — and `PromotionBlocked` subclasses it for the ADR-0028 guards, carrying the blockers
as a **list**: each blocker is its own stderr line, and one of them ends in a copy-pasteable
`gh auth switch --user carlacurymed`, so joining them with `"; "` would put shell syntax directly
after a command an operator selects and pastes. A `gh` failure is deliberately *not* a
`PromotionBlocked`: it happens after the guards passed and after the attempt, so it must not print
under a "refusing to promote" prefix that tells the operator nothing was filed — the one case where
that is wrong is `gh` exiting 0 with an unparseable URL, where the issue *is* in the shared backlog.

**What deliberately stayed in `cli.py`, not moved here:** the three `gh` subprocess calls
(`active_gh_account`, `create_issue`, the fix-PR issue comment). Same reasoning ADR-0031 applied to
`fix_agent.py`'s five `git` calls: they are plumbing to an external tool, not a use case, and
extracting a `gh`/`git` port is explicitly out of scope for this refactor (tracked in #29).
`promote_report` and `fix_report` take `create_issue_fn`/`notify_fn` as injected callables instead
— the blocker/state-writing logic they wrap is the use case; the subprocess call underneath it is
not.

**Callbacks, because output ordering around a paid step is behavior.** Returning a result object
instead of printing moves *when* the operator learns things, and for the three commands that spend
money that is not cosmetic. `investigate_findings` fires `on_plan` after planning and before the
first agent call, `on_start` before each call, and `on_result` after each report is written;
`fix_report` fires `on_start` with the resolved repo and issue URL before its agent call, and
`seed` fires `on_quarantine` per finding the gate catches. The rule they encode: anything the
operator would act on while a Ctrl-C still saves money has to be emitted before the money is spent,
and anything naming a specific finding has to stay attached to it.

Concretely, without them: the ADR-0023 tier/budget announcement printed only after all five
subprocesses had billed; `fix`'s repo mapping — which `resolve_repo` may derive from scanning the
report *body*, so it can resolve to the wrong repo — was disclosed only after the PR existed; five
`[i/N]` prefixes written with `end=" "` concatenated onto one line with the cost figures detached
below them; and an interrupted `seed` named none of the fingerprints it had quarantined.
`tests/test_e2e_pipeline.py` now asserts the ordering at the `main(argv)` boundary, and
`tests/test_pipeline.py` asserts the callback sequence directly.

One ordering change is deliberate rather than restorative: `fix_report` records `fix_pr`/`fix_state`
in the report *before* calling `notify_fn`. `gh` missing from `PATH` — the realistic cron case —
used to leave the URL of a PR the agent had already pushed and billed for recorded nowhere.

## Consequences

### Good

- `tests/test_cli_investigate.py` (4 tests, 20 patch decorators, asserted only that mocks were
  called) is deleted, not migrated — it carried no claim `tests/test_pipeline.py` and
  `tests/test_e2e_pipeline.py` don't already make more strongly. `tests/test_pipeline.py` (new, 19
  tests) drives `investigate_findings`/`seed`/`plan_run`/`promote_report`/`fix_report` directly
  with fakes and asserts on the real `InvestigationRun`/`SeedOutcome`/report bytes on disk, not on
  which internal function got called.
- `cmd_fix` has real tests for the first time: `test_fix_report_refuses_a_report_that_is_not_promoted`,
  `..._refuses_without_an_issue_url`, `..._refuses_a_service_with_no_repo_mapping`,
  `..._records_the_pr_and_notifies_the_issue`, `test_fix_discloses_the_resolved_repo_before_the_agent_runs`,
  and `test_the_pr_url_is_recorded_before_gh_is_told_about_it`. `promotion_blockers` and
  `promote_report` gain direct tests alongside the seven CLI-level `--create` tests that already
  existed.
- The seams Moves A and B introduced are verified for the first time rather than merely declared:
  mutation-testing showed that deleting `store=store`, `runner=runner`, or `warnings=result.warnings`
  from the forwards in `pipeline.py` left the whole suite green, because every collaborator defaults
  back to `DEFAULT_STORE`/`DEFAULT_RUNNER` and the `store` fixture repoints `DEFAULT_STORE.root` in
  place. `test_an_explicit_store_is_where_the_report_lands` and
  `test_investigation_writes_through_the_store_it_was_given` construct a *second* `ReportStore` and
  assert the report lands there; the `runner` assertions pin object identity. Eleven such mutations
  were run against the final suite and all eleven fail it.
- `houston/cli.py` shrank from 470 lines (252 statements) to 172 statements at 84% line coverage,
  on a now argparse-and-wiring-shaped file. `houston/pipeline.py` is at 97%. Package-wide coverage
  rose from the 89% baseline ADR-0029 recorded to 93% — Move C did not just relocate code, the
  direct-call tests reach branches the `cmd_*`-level tests never triggered.
- 249 tests total (222 before this PR, minus 4 deleted, plus 31 new). The golden and E2E report-byte
  tests from ADR-0029 pass unedited, which is what proves the *files* are unchanged; the stdout
  ordering tests added here are what proves the terminal is.
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
- `update_front_matter` is a candidate to move onto `ReportStore` as a method, now that every use
  case already receives a store — that would also put it behind `_filename`'s path-safety check.
  Out of scope here: it changes the contract ADR-0030 documents, not this one.
- A pre-existing bug this review surfaced and this PR does not touch, reproducible identically on
  `main`: a second `houston fix` whose agent fails rewrites `fix_pr: null` over the first run's
  recorded PR URL. `fix_agent._count_existing_attempts` shows re-runs are an expected workflow, and
  `metrics.py` and `generate_site.py` read that field. Filed separately.
