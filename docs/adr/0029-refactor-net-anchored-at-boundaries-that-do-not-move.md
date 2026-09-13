# ADR-0029: The refactor net is anchored at boundaries the refactor does not move

**Status:** Accepted
**Date:** 2026-09-13
**Deciders:** Carla Cury (found while planning the dependency-inversion refactor tracked in #29 --
the existing suite's coupling to module topology was measured before writing a single line of the
refactor itself)
**Decision style:** Design fix — a test net written to survive three planned moves, not to
characterize current behavior in general.
**Related:** [[0015-quarantine-is-a-tracked-state]], [[0020-retry-transients-and-fan-out-only-when-investigable]]

## Context

`houston/` is about to go through three dependency-inversion moves: `reports/` becomes an injected
`ReportStore` instead of a module-level global (`REPORTS_DIR`, with `QUARANTINE_DIR` derived at
import time), the `claude -p` subprocess call moves behind a port, and the `cmd_*` use-case logic
moves out of `houston/cli.py`. None of the three moves any module to a new directory.

Measured before touching anything: of 173 test functions on `origin/main`, 103 are coupled to
module topology -- `@patch("houston.cli.collect")`, `monkeypatch.setattr(dedup_mod, "REPORTS_DIR",
tmp_path)`. Every one of those breaks for a structural reason the moment a name it patches leaves
its module, independent of whether the refactor changed any actual behavior. The temptation in that
situation is to "fix" the broken test by retargeting the patch without checking that the assertion
still means anything -- which quietly deletes the coverage instead of migrating it.

Three real gaps existed, not the "no test exercises write_report" claim first suspected --
`tests/test_frontmatter.py` already calls the real `write_report()` seven times. The actual gaps:

1. **No byte-exact assertion on a rendered report.** Front-matter key order, the injected
   `**Link do Datadog:**` line, and the trailing newline are all load-bearing (`read_report`,
   `cmd_promote`, and the fix front-matter rewrite all `text.split("---", 2)`), and nothing would
   fail if any of them silently changed.
2. **`main()` took no `argv` parameter**, so nothing could drive the CLI end to end; every `cmd_*`
   test built an `argparse.Namespace` by hand, which cannot catch a subcommand wired to the wrong
   handler or a changed default.
3. **`cmd_metrics` and `scripts/generate_site.py` call `load_all_reports()` with no argument**,
   binding `metrics.REPORTS_DIR` -- a fourth copy of the global that no existing test isolates. A
   mis-wired store after the refactor would make `houston metrics` print "no reports yet", exit 0,
   and `can_close_phase` report the phase can close: a false green on the project's own exit
   criterion, with no failing test anywhere.

## Decision

Write the net first, in its own PR, before any of the three moves. Each new test is placed at a
boundary none of the three moves changes:

- **`main(argv: list[str] | None = None)`** -- the only production change in this PR. Makes the CLI
  drivable by argv; `argv=None` reproduces today's `sys.argv[1:]` behavior exactly.
- **`tests/test_report_golden.py`** -- byte-for-byte comparison of `write_report()`'s output
  against committed golden files, covering both the clean-write and quarantine paths.
- **`tests/test_e2e_pipeline.py`** -- drives `main(["seed"|"run"|"investigate"|"metrics", ...])`
  against the same recorded Datadog fixtures `test_collector.py` already uses, with `claude -p`
  stubbed by matching `argv[0] == "claude"` (never `houston.agent.subprocess.run` by name, so the
  stub survives wherever the eventual port adapter lands). Asserts on the files that land in a
  `tmp_path` store, never on which internal function was called.
- **`tests/test_report_corpus.py`** -- three invariants over the real, committed `reports/*.md`
  corpus: zero PII (measured true today, 0 hits over 166 files), every filename matches its own
  `fingerprint` (the entire dedup mechanism), and every report carries the fields `dedup` and
  `metrics` read. Deliberately does **not** assert the full current schema -- the corpus has real
  legacy drift (pre-ADR-0019 reports with no `novelty`, pre-ADR-0023 reports with no `cost.model`)
  that a strict schema check would flag as a bug it isn't.
- **`tests/test_cli_main.py`** -- proves argparse hands each `cmd_*` its documented defaults
  (`investigate --max-findings 5`, distinct from `run`'s `--max-findings 15` -- two different
  policies, not a duplicated constant) and that unknown/missing subcommands exit non-zero.
- **`tests/conftest.py`** (first in the repo) -- a `store` fixture that rebinds the four global
  names (`dedup.REPORTS_DIR`, `frontmatter.REPORTS_DIR`, `frontmatter.QUARANTINE_DIR`,
  `metrics.REPORTS_DIR`) to one `tmp_path`. Its body changes when `ReportStore` lands; no test using
  it should need to change.
- **`pytest-cov`**, opt-in via `mise run test --cov`, no threshold. A numeric gate on a PoC becomes
  noise before it becomes protection -- the baseline (89% line, measured on this branch) is recorded
  here for the refactor PRs to diff against, not enforced in CI.

## Consequences

### Good

- Each of the three coming PRs has an objective, mechanical check for "did this change behavior":
  the golden and E2E tests must pass unedited. If a PR needs to edit `tests/test_report_golden.py`
  or `tests/test_e2e_pipeline.py`, that PR changed what lands in `reports/`, which needs its own
  justification, not a silent golden regeneration.
- 173 pre-existing tests are untouched by this PR; 23 new ones (196 total) run in 1.4s.
- The `cmd_metrics` false-green gap (item 3 above) now has two failing-test tripwires
  (`test_metrics_on_an_empty_store_exits_0_and_does_not_claim_a_closed_phase`,
  `test_metrics_exits_1_while_work_is_owed_and_0_once_the_phase_can_close`) instead of zero.

### Bad

- The golden files are frozen bytes, not a generator -- an intentional format change requires
  regenerating and reviewing the diff by hand. No `--update-golden` flag was added on purpose: a
  regeneration flag is how goldens silently stop being goldens.
- Coverage baseline (89%) is not gated. `houston/fix_agent.py` sits at 73% and `houston/cli.py` at
  81% -- both pre-existing gaps (`cmd_fix` had zero tests before this PR), left for the PRs that
  touch those modules rather than backfilled here.

### Follow-up

- The 103 topology-coupled tests are migrated PR-by-PR as each move lands, per the rule: only the
  import and the patch target change, never the assertion. A test that would need more than that
  was testing structure, not behavior, and gets replaced before the move that breaks it, not during.
- `tests/test_cli_investigate.py`'s four tests stack five mocks and assert only that they were
  called -- they carry no claim the golden/E2E tests don't already make more strongly, so they are
  deleted, not migrated, once Move C lands.
