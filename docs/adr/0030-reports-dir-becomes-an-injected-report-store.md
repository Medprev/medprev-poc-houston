# ADR-0030: reports/ becomes an injected ReportStore, not a module global

**Status:** Accepted
**Date:** 2026-09-13
**Deciders:** Carla Cury (Move A of the dependency-inversion refactor tracked in #29; designed and
verified in `refactor/report-store`, against the test net from ADR-0029)
**Decision style:** Design fix — inverts a dependency direction; no behavior change verified by the
unedited golden and E2E tests from ADR-0029.
**Related:** [[0029-refactor-net-anchored-at-boundaries-that-do-not-move]], [[0015-quarantine-is-a-tracked-state]]

## Context

`houston/dedup.py` defined `REPORTS_DIR = Path(...) / "reports"` at module import time.
`houston/frontmatter.py` imported a copy of that name (`from houston.dedup import REPORTS_DIR`)
and derived `QUARANTINE_DIR = REPORTS_DIR / ".quarantine"` from it, also at import time.
`houston/metrics.py` imported a third copy for `load_all_reports`. Three consequences, all
measured before this PR:

1. **A real import cycle.** `frontmatter.py` depended on `dedup.py` for `REPORTS_DIR`, and
   `dedup.needs_investigation` needed `frontmatter.read_report` — held apart only by a
   function-local import inside `needs_investigation`, with a comment explaining why.
2. **Isolating a test required patching four separate names**, not one: `dedup.REPORTS_DIR`,
   `frontmatter.REPORTS_DIR`, `frontmatter.QUARANTINE_DIR` (because it snapshotted `REPORTS_DIR` at
   import time, so patching the source name after import did nothing to it), and
   `metrics.REPORTS_DIR`. The fourth was isolated by no existing test — `cmd_metrics` and
   `scripts/generate_site.py` both call `load_all_reports()` with no argument.
3. **A mis-wired store would fail silently.** With the fourth copy unisolated, a bug in how a
   future refactor wired the reports directory would make `houston metrics` read the real
   `reports/`, possibly print "no reports yet", exit 0, and `can_close_phase` report the phase can
   close — a false green on the project's own exit criterion.

## Decision

`houston/report_store.py` introduces `ReportStore`, a small mutable class wrapping one `root: Path`:
`path`, `exists`, `write`, `write_quarantined`, `iter_paths`, and a `quarantine` **property**
computed from `self.root` on every access — never snapshotted. `DEFAULT_STORE = ReportStore(ROOT /
"reports")` is the one definition of the real path.

`dedup.py`, `frontmatter.py`, and `metrics.py` each take `store: ReportStore = DEFAULT_STORE` as a
keyword-defaulted parameter instead of touching a global. `write_report`, `_write_quarantine_record`,
`report_path`, `already_reported`, `needs_investigation`, `filter_new`,
`filter_needing_investigation`, and `load_all_reports` all thread it through. `houston/cli.py` and
`scripts/generate_site.py` needed no changes at all — their calls with no explicit store argument
already resolve to `DEFAULT_STORE`. `scripts/backfill_datadog_url.py` now imports `DEFAULT_STORE`
and calls `.iter_paths()` instead of globbing `REPORTS_DIR` directly.

`dedup.py` now imports `frontmatter.read_report` at the top of the file — the deferred,
function-local import and its explaining comment are gone, because the cycle they worked around no
longer exists. New direction: `report_store ← frontmatter ← dedup`, verified acyclic by walking the
import graph of every `houston/*.py` file.

**Test isolation collapses to one mutation, not four monkeypatches.** Because `DEFAULT_STORE` is a
single mutable object — every module's `from houston.report_store import DEFAULT_STORE` binds a
name to the *same instance*, and every function's `store: ReportStore = DEFAULT_STORE` default
parameter captures that same instance at definition time — a test can isolate every collaborator at
once by mutating one attribute on one object:

```python
monkeypatch.setattr(DEFAULT_STORE, "root", tmp_path)
```

`quarantine`, being a property derived from `self.root`, updates automatically; there is no second
name to patch the way `QUARANTINE_DIR` used to need. `tests/conftest.py`'s `store` fixture does
exactly this. 12 test call sites across `tests/test_dedup.py`, `tests/test_frontmatter.py`, and
`tests/test_cli_promote.py` dropped their local monkeypatch helpers (`_use_tmp`, `_write`'s
`monkeypatch.setattr` lines) in favor of the shared fixture — no assertion in any of them changed.

## Consequences

### Good

- The import cycle is gone, verified by an `ast`-based walk of `houston/*.py`'s import graph
  finding no cycle.
- Test isolation for reports-directory state is now one line (`monkeypatch.setattr(DEFAULT_STORE,
  "root", tmp_path)`) instead of three-to-four per test file.
- `metrics.py` lost its only `houston` import besides `frontmatter` and its only piece of dead
  code: `load_all_reports`'s `if p.parent.name != ".quarantine"` filter was checking a condition
  `Path.glob("*.md")` (non-recursive) can never make false. `iter_paths()` doesn't recurse, so the
  filter had nothing to do and is gone with it.
- `houston/cli.py` required zero changes — every call site it owns already used the
  `report_path`/`already_reported`/`load_all_reports` functions by their existing 0- or 1-argument
  shape, which the new default parameter satisfies exactly.
- Verified against the real, tracked corpus, not just tmp_path fixtures: `mise run metrics` (153
  reports) and `python scripts/generate_site.py` (153 reports, `site/index.html`) both read
  `DEFAULT_STORE` correctly.
- The golden and E2E tests from ADR-0029 pass unedited — the objective proof this PR changed no
  observable behavior.

### Bad

- `DEFAULT_STORE`'s mutability is what makes single-point test isolation work, but it means
  `ReportStore` is not the frozen, side-effect-free value type a strict reading of "dependency
  injection" would prefer. Accepted deliberately: the alternative (no default value, every caller
  constructs and threads its own `ReportStore`) was evaluated and would have required `cli.py`'s six
  `cmd_*` functions to accept and forward a `store` parameter each — real churn for a PoC, deferred
  to the use-case extraction (Move C, tracked in #29) where those functions are being rewritten
  anyway.
- `update_front_matter` (`houston/cli.py`, the function `cmd_fix` uses to write `fix_pr`/`fix_state`
  back into a report) still resolves its own path and writes directly, bypassing `write_report()`
  and the PII gate — unchanged from before this PR. That bypass is deliberate (the values it writes
  are code-owned: a URL `gh` printed, a state the CLI chose, never model text) and is out of scope
  here; this PR only changed *how a path is resolved*, not the write-path contract.

### Follow-up

- Move B (model-runner port) and Move C (use-cases out of `cli.py`), tracked in #29, build on this
  PR's `store` parameter shape.
