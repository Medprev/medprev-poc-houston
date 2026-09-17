# ADR-0033: The report has a read path, and it returns the whole report

**Status:** Accepted
**Date:** 2026-09-15
**Deciders:** Carla Cury (C1 of the deepening sequence tracked in #37, found by an architecture
review of `origin/main` at `3895324`; the duplication was counted before a line was written)
**Decision style:** Design fix — gives an existing seam its missing direction. One behavior change
was introduced and reverted during review (see Consequences); what ships is parity, verified by
diffing `houston metrics` and `houston promote` against the pre-refactor tree on the real corpus.
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

`update_front_matter` (`pipeline.py`) patches the document on top of `split_document` rather than
carrying a fourth copy of the split — which is what makes "the rendered shape is known in
`frontmatter.py` and nowhere else" true rather than aspirational, and removes a latent crash:
its own `yaml.safe_load` had no `or {}`, so an empty front-matter raised `AttributeError` on
`.update`. It still does not re-render the `Report`, and it must not: measured over the corpus,
**153 of 153** reports gain keys on a re-render (`cost.model` on all 153, `fix_pr`/`fix_state` on
149, `novelty` on 16, `datadog_url` on 2), and none loses a value.

`read_report` is deleted. `dedup`, `metrics`, `pipeline`, `scripts/generate_site.py` and
`scripts/backfill_datadog_url.py` all read typed attributes. `metrics.compute` and `can_close_phase`
take `list[Report]`; `_cost` and every `or 0.0` guard in that module are gone, because `Cost`'s
declared defaults now do that work once instead of at each call site.

**The parser is total, and that is a decision, not an oversight.** The committed corpus has measured
drift: 16 of 153 reports predate ADR-0019 and carry no `novelty` (their novelty sits in `reason`),
and **none of the 153 carries the `cost.model` ADR-0023 added**. An absent key therefore takes the
field's documented default rather than raising. The consequence is pinned by a test:
`to_markdown(from_markdown(r))` is *not* byte-identical for any report on disk. **Patching a report
in place must preserve the document, not re-render it** — which is why `split_document` is public
and why `update_front_matter` consumes it.

`scripts/backfill_datadog_url.py`'s 19-line hand rebuild collapses to a 5-line
`dataclasses.replace` over the three derived fields. Everything measured is carried rather than
re-listed, which is what closes #35 by construction: a field added to `Report` later cannot be
silently dropped there again.

## Consequences

### Good

- **A behavior change caught in review, before merge.** The first version built the promote command
  from `report.body` — the parsed, link-stripped body. 143 of the 153 committed reports carry no
  `## Corpo da issue` heading and hit `extract_issue_body`'s whole-body fallback, so every issue
  filed off one of them would have lost its `**Link do Datadog:**` line: the reader's only way to
  the evidence (ADR-0011), removed from a shared backlog, with no test able to see it. The promote
  path now takes the *document* body, `houston promote` output is `diff`-identical to the
  pre-refactor tree, and `test_the_filed_issue_body_keeps_the_datadog_link` pins it.

- 263 tests pass (249 before, +14). `tests/test_e2e_pipeline.py` is **untouched**; every assertion
  in `tests/test_report_golden.py` is unedited (only its docstring changed, to correct a report
  count that was already stale) — the ADR-0029 rule that proves the report bytes did not move.
  `ruff` clean.
- `mise run metrics` against the tracked 153-report corpus prints output byte-identical to the
  pre-refactor checkout, `diff`-verified, including the 22.2% false-positive rate and every
  percentile.
- Four re-parsing implementations become one, counting `update_front_matter`; `split("---", 2)`
  appears once in the package.
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

- **`from_markdown` is lenient, and the failure modes are not the ones a first reading suggests.**
  Measured, not assumed:
  - a document with no closing `---` fence, or an empty file, raises `ValueError` from the unpack —
    it does not parse into defaults;
  - a document truncated right after the fence parses with an empty body, silently;
  - **a wrong type is not coerced to a default.** `cost.usd: 'abc'` is truthy, so `or 0.0` passes the
    string straight through and `metrics.compute` raises `TypeError: unsupported operand type(s) for
    +: 'float' and 'str'` — three layers from the cause, with no filename and no field name.

  The tripwire is therefore not "every report parses", which only checks shape.
  `test_the_real_corpus_computes_metrics_without_raising` runs `compute()` over the real corpus, which
  is what catches a type. A schema-validating reader is still not worth its cost on a PoC whose corpus
  is 153 files it can check in full on every run.
- **`novelty` collapses "absent" and "not a regression".** 16 reports carry their novelty inside
  `reason` (pre-ADR-0019); `from_markdown` maps the absent key to `""`, and `issue_title` reads
  `!= "regression"`, so promoting one of those today produces a title that *asserts* it is not a
  regression when the file simply does not say. The backfill knows better (`_repaired_labels`);
  `issue_title` does not. A `None` default would keep the two distinguishable, at the cost of a
  `str | None` that ripples through the render path. Left as measured debt.
- **An absent `state` parses to `""`, which reads as "already handled".** In
  `dedup.needs_investigation`, `"" not in {"seeded", "incomplete"}` is `False`, so such a report
  leaves the queue permanently. Not a regression — `read_report(path).get("state")` returned `None`
  with the same effect — but the typed path makes it look deliberate.
- `Report` is still a mutable dataclass with a mutable `Cost`, so `pipeline.py` still fills seven
  cost fields by assignment after construction. The cause is not the missing `frozen=True`: it is
  that `Report.from_finding` has no `cost` parameter while `InvestigationResult` already carries
  exactly those seven values. Adding one collapses the block at construction; freezing then becomes
  mechanical. Both belong with the write-path work, next in #37.

### Follow-up

- `update_front_matter` is still the second, **untyped and ungated** door into `reports/`: it takes
  `**fields` with no validation, writes outside `ReportStore` (and so outside `_filename`'s
  path-safety check), and is where a failed second `houston fix` writes `fix_pr: null` over a real
  PR URL (#34). Typing and gating it is the next PR in #37; this one only stopped it carrying its
  own copy of the format.
- `scripts/generate_site.py` renders `observed.first_seen` in UTC while `houston/timestamps.py`
  renders the same field in America/São_Paulo. Out of scope here — it changes the rendered page, not
  the refactor — but it is a real divergence between two renderers of one field.
- The inverse of the link-line injection is wider than the injection: `from_markdown` drops **any**
  body line starting with `**Link do Datadog:**`, while `to_markdown` only ever writes one at the
  top. Measured: 0 of the 153 reports have such a line in the body without the matching front-matter
  field, so nothing is lost today.
