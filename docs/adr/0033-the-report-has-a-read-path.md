# ADR-0033: The report has a read path, and it returns the whole report

**Status:** Accepted
**Date:** 2026-09-15
**Deciders:** Carla Cury (C1 of the deepening sequence tracked in #37, found by an architecture
review of `origin/main` at `3895324`; the duplication was counted before a line was written)
**Decision style:** Design fix — gives an existing seam its missing direction. No behavior change:
the golden and E2E tests from ADR-0029 pass unedited, and `houston metrics` against the real
153-report corpus prints byte-identical output.
**Related:** [[0030-reports-dir-becomes-an-injected-report-store]],
[[0029-refactor-net-anchored-at-boundaries-that-do-not-move]], [[0019-reason-is-the-diagnostic-label]],
[[0023-agent-model-and-effort-are-pinned]], [[0014-window-scoped-counts-and-per-finding-evidence]]

## Context

`houston/frontmatter.py` owned the rendered report shape in one direction only. `Report.to_markdown`
defined the `---` fences, the nested `window`/`observed`/`cost` blocks and the injected
`**Link do Datadog:**` line; the way back was `read_report(path) -> dict`, three lines that returned
an untyped mapping and **threw the body away**. Measured on `origin/main`:

1. **Four implementations of the same split.** `frontmatter.py:183`, `pipeline.py:153`,
   `pipeline.py:337`, `scripts/backfill_datadog_url.py:86`. Three of them existed only to recover
   the half `read_report` dropped. `fix_report` opened one file twice for that reason —
   `read_report(path)` at `pipeline.py:416`, then `path.read_text()` at `:426`.
2. **The nested YAML shape travelled to three modules that should never have seen it.**
   `scripts/generate_site.py:50` (`r["observed"]["first_seen"]`), `houston/metrics.py:49` (a `_cost`
   helper plus six `.get(...) or 0.0` guards re-deriving defaults `Cost` already declares), and
   `scripts/backfill_datadog_url.py:106` (`Cost(**(existing.get("cost") or {}))`, which couples YAML
   key names straight onto Python field names and raises on any key it does not know).
3. **The missing inverse cost real data.** With no `from_markdown`, `backfill_datadog_url.py`
   rebuilt a `Report` by hand from 17 of its 19 fields (`:91-109`), so `fix_pr` and `fix_state` took
   their dataclass default of `None` and were erased on every run — issue #35, against the three
   reports in the corpus that carry a real PR URL. The same absence forced `_strip_link_line`, whose
   own docstring records the bug it exists to undo: "keeping the previous one in the body is what
   duplicated it on every re-run."

## Decision

`Report.from_markdown(text) -> Report` is the inverse of `to_markdown`, and `load_report(path)` is
the counterpart of `write_report(report)`. The reader lives in `frontmatter.py`, not on
`ReportStore`: ADR-0030 fixed the direction as `report_store ← frontmatter`, and a `ReportStore.load`
returning a `Report` would invert it back into a cycle. `write_report(report, store)` is already a
module-level function in `frontmatter.py`; the reader is its mirror.

**Two views of a report file, one implementation of the `---` rule.**

- `split_document(text) -> (mapping, raw_body)` — the *document* view. Nothing is normalized. For
  callers that must see the keys a file actually carries, or patch one without re-rendering it.
- `Report.from_markdown(text) -> Report` — the *value* view. Built on `split_document`, then strips
  the injected link line, which is exactly the inverse of what `to_markdown` injects.

`read_report` is deleted. `dedup`, `metrics`, `pipeline`, `scripts/generate_site.py` and
`scripts/backfill_datadog_url.py` all read typed attributes. `metrics.compute` and `can_close_phase`
take `list[Report]`; `_cost` and every `or 0.0` guard in that module are gone, because `Cost`'s
declared defaults now do that work once instead of at each call site.

**The parser is total, and that is a decision, not an oversight.** The committed corpus has measured
drift: 16 of 153 reports predate ADR-0019 and carry no `novelty` (their novelty sits in `reason`),
and **none of the 153 carries the `cost.model` ADR-0023 added**. An absent key therefore takes the
field's documented default rather than raising. The consequence is pinned by a test:
`to_markdown(from_markdown(legacy))` is *not* byte-identical, because it renders keys that report
never had. **Patching a report in place must preserve the document, not re-render it** — which is
why `split_document` is public, and what the next PR in #37 builds `ReportStore.update` on.

`scripts/backfill_datadog_url.py`'s 19-line hand rebuild collapses to a 5-line
`dataclasses.replace` over the three derived fields. Everything measured is carried rather than
re-listed, which is what closes #35 by construction: a field added to `Report` later cannot be
silently dropped there again.

## Consequences

### Good

- 255 tests pass (249 before, +6). `tests/test_report_golden.py` and `tests/test_e2e_pipeline.py`
  pass **unedited** — the ADR-0029 rule that proves the report bytes did not move. `ruff` clean.
- `mise run metrics` against the tracked 153-report corpus prints output byte-identical to the
  pre-refactor checkout, `diff`-verified, including the 22.2% false-positive rate and every
  percentile.
- Four re-parsing implementations become one; the rendered shape is known in `frontmatter.py` and
  nowhere else.
- New invariants, each earning its place: `from_markdown(to_markdown(r)) == r` field-by-field (a
  field rendered but not parsed now fails a test, which is the exact drift that caused #35); a
  re-render does not stack a second link line; every one of the 153 committed reports parses; no
  parsed body carries an injected link line.
- `tests/test_report_corpus.py` keeps reading raw keys, through `split_document`. Routing it through
  the tolerant parser would have made "this key is on disk" vacuous — the silent coverage deletion
  ADR-0029 warns about.
- `promotion_blockers` could be called with `{}` and four tests did exactly that. Its parameter is
  now a `Report`, so those tests state what they mean, and the "already carries an issue" guard
  gained the direct test it never had.

### Bad

- `Report` is still a mutable dataclass with a mutable `Cost`, so `pipeline.py:300-306` still fills
  seven cost fields by assignment after construction. Making it frozen is a separate change and
  belongs with the use-case work later in #37.
- `from_markdown` is lenient by construction. A genuinely corrupt report — wrong types, a truncated
  document — parses into defaults rather than failing loudly. The corpus test that every committed
  report parses is the tripwire; a schema-validating reader is not worth its cost on a PoC whose
  corpus is 153 files it can check in full on every run.

### Follow-up

- `update_front_matter` (`pipeline.py:144`) is still the second, untyped door into `reports/` and
  still the only remaining `split("---", 2)` in the package. It is the next PR in #37, and
  `split_document` exists for it.
- `scripts/generate_site.py` renders `observed.first_seen` in UTC while `houston/timestamps.py`
  renders the same field in America/São_Paulo. Out of scope here — it changes the rendered page, not
  the refactor — but it is a real divergence between two renderers of one field.
