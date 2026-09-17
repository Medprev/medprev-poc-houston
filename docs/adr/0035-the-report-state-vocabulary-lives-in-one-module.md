# ADR-0035: The report's state vocabulary lives in one module, and is enforced on the way in

**Status:** Accepted
**Date:** 2026-09-17
**Deciders:** Carla Cury (C3 of the deepening sequence tracked in #37)
**Decision style:** Design fix — collapses four partial vocabularies into one and closes a latent
bug ADR-0033 measured and left open. One behavior change ships with it: a state this package cannot
read now keeps the phase open instead of disappearing from it.
**Related:** [[0034-the-write-back-path-is-typed-and-a-fix-attempt-records-what-it-billed]],
[[0033-the-report-has-a-read-path]], [[0015-quarantine-is-a-tracked-state]],
[[0010-seeded-reports-stay-eligible-for-investigation]], [[0028-promote-files-the-issue-behind-fail-closed-guards]]

## Context

`state` is the field the whole PoC turns on: it decides what gets investigated (money), what blocks
the phase from closing, and — through `promoted`/`discarded` — the false-positive rate this PoC
exists to produce. Measured on `origin/main` (`0475f8c`), it had no owner.

1. **Four partial vocabularies, in four modules.** `dedup.NEEDS_INVESTIGATION_STATES`
   (`{seeded, incomplete}`), `metrics.BLOCKING_STATES` (`(new, incomplete, quarantined)`),
   `scripts/generate_site.py:_STATE_ORDER` (six values, the only exhaustive list in code), and
   `frontmatter.QUARANTINED_STATE` (one). The other exhaustive list was a **comment** on
   `Report.state`; a fourth lived in a set literal inside `tests/test_report_corpus.py`.

2. **Nothing validated a state on the way to disk.** `write_report` took any string. `state: promted`
   would have been rendered, written, parsed back as itself, and counted as its own row in
   `houston metrics`'s by-state table — with a green suite, because no test writes a typo.

3. **An unreadable state left the queue permanently.** ADR-0033 made the parser total, so an absent
   `state` key parses to `""`. `"" not in BLOCKING_STATES` is False, so such a report did not block
   the phase; `"" not in NEEDS_INVESTIGATION_STATES` is also False, so it was never re-investigated
   either. ADR-0033 recorded this as measured debt: "the typed path makes it look deliberate."

4. **`fix_state`'s vocabulary was partly fiction.** `Report.fix_state`'s comment listed
   `attempted | pr_open | merged | rejected | incomplete`. `pr_open` and `incomplete` are written by
   `fix_agent.fix`; `merged` and `rejected` are the reviewer's verdict on the PR and no code writes
   them; **`attempted` appears nowhere** — not in the package, not in the 153-report corpus, not in
   `docs/pipeline.md`.

## Decision

`houston/report_state.py` owns the vocabulary: `ReportState` and `FixState` as `StrEnum`, the three
derived collections (`NEEDS_INVESTIGATION`, `BLOCKING`, `DISPLAY_ORDER`), and the questions the rest
of the package asks. The four scattered lists are gone, `metrics.BLOCKING_STATES` included: `cli.py` prints the
operator message from `report_state.BLOCKING` directly rather than through a constant `metrics.py`
only re-exported.

**The two questions answer an unreadable state differently, and that is the point.**

- `needs_investigation(raw)` answers **no**. It spends money: re-running the agent against a document
  nobody can vouch for is a real charge against a real cap.
- `blocks_phase(raw)` answers **yes**. `houston metrics` refuses to close the phase and names the
  count, which is what makes a human look. Before this, both answered no, and the report vanished.

**Validation happens on the way in.** `write_report` refuses a state outside the vocabulary before
rendering anything, and `record_fix_attempt` refuses an unknown `fix_state`. Fail closed on write is
the cheap side: a bad value on disk is a document a human has to find and fix by hand.

**Values stay `str` on `Report`.** `yaml.safe_dump` raises `RepresenterError` on a `StrEnum` member,
and the rendered bytes of 153 committed reports are the product (ADR-0029). The enum is what code
compares and decides with; `to_markdown` coerces with `str()`, so passing a member is safe rather
than a crash at write time — a real trap, because a `StrEnum` satisfies every `str` annotation on the
way there.

**`attempted` is deleted rather than kept.** `merged` and `rejected` stay in `FixState`, marked in
code as human-owned with no writer: that is the real workflow `docs/pipeline.md` draws, and naming
them is how the gap stays visible instead of looking like an oversight.

## Consequences

### Good

- The vocabulary is in one place, and `DISPLAY_ORDER` is covered by a test that compares it against
  the enum — a state added later cannot silently disappear from the incident page.
- 292 tests pass (281 before, +11). `reports/` is untouched, `tests/test_report_golden.py` and
  `tests/test_report_corpus.py` are unedited, and `mise run metrics` over the real 153-report corpus
  prints output byte-identical to the pre-change checkout, `diff`-verified. `ruff` clean.
- The two central tests are verified by mutation, not by passing: making an unreadable state
  non-blocking again, and dropping the write-time validation, each fail a test.
- `houston/dedup.py` lost its own copy of the rule and now asks the module, so the collector's
  expensive fan-out and the investigation itself cannot drift apart on what "needs investigating"
  means.

### Bad

- **The state machine names transitions it does not enforce.** `promoted` and `discarded` are human
  gestures (ADR-0028), and nothing checks that a report moving to `promoted` came from a state where
  that makes sense. Promoting a `discarded` report is still allowed — a human changing their mind is
  legitimate, and the false-positive rate recomputes — but so is promoting anything else.
- **`discarded` still has no writer.** The input to the headline metric is a human editing YAML by
  hand. That is deliberate (the decision is the instrument), but it means the one state the PoC
  measures itself by is the one the code cannot produce or validate at the moment it is chosen.
- **`merged`/`rejected` remain unreachable.** Naming them as human-owned does not record a reviewer's
  verdict; nothing closes the loop after `pr_open`, so `houston metrics` cannot say whether a fix was
  accepted.
- An unreadable state now blocks the phase forever until a human edits the file. That is the intent,
  but it is a way to wedge `can_close_phase` that did not exist before.

### Follow-up

- A `houston decide <fingerprint> --promote|--discard` command would give `discarded` a writer and put
  the transition under the same validation as the rest. It is a new command, not a refactor, so it is
  not in #37's sequence.
- C4 (the report body's section contract) is the last place a literal string still carries meaning
  across two modules — `## Corpo da issue`, duplicated between `agent.py`'s prompt and
  `pipeline.py`'s parser.
