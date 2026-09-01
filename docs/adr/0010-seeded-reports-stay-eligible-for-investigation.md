# ADR-0010: `houston seed`'s output stays eligible for real investigation

**Status:** Accepted
**Date:** 2026-09-02
**Deciders:** Carla Cury (raised as a direct complaint: reports showed no
evidence/cause/timeline; found the mechanism was a dedup design gap, not
a missing feature)
**Decision style:** Bug fix in the pipeline's core dedup semantics.
**Related:** none yet

## Context

`houston seed` (E3) deliberately writes a report with `state: seeded` and
no real investigation, for pre-existing debt found on the first run. That
was always correct on its own. The bug was in what happened next:
`houston run` and `houston investigate` both used `filter_new`, which
excludes any finding whose `reports/{fingerprint}.md` already exists —
full stop, regardless of that report's `state`.

Consequence: once a finding was seeded, it could **never** be picked up
by `houston investigate` again. Its report would sit forever with the
generic "Seeded on first run... not investigated" body — no root cause,
no evidence, no timeline — because the only mechanism that could replace
that body treated "has a file" as "already handled," identically to how
it treats an already-`promoted` or `discarded` report. 148 of the repo's
149 reports were in exactly this state.

The dedup mechanism (`reports/{fingerprint}.md` existing) is correct for
its original purpose — don't re-collect or re-normalize a signal already
tracked. It was wrong to reuse for a second, different question:
"does this finding still need real investigation?" Those are not the same
question. A `seeded` or `incomplete` report answers "tracked, not yet
resolved into evidence." A `new`, `promoted`, or `discarded` report
answers "already has a real investigation or a human decision — leave it
alone."

## Decision

`houston/dedup.py` gains `filter_needing_investigation`, used by
`houston run` and `houston investigate`: a finding is included if its
report doesn't exist yet, **or** exists with `state` in `{seeded,
incomplete}`. `houston seed` keeps using the original `filter_new`
(existence-only) — seeding must never overwrite an already-decided or
already-investigated report.

`write_report` already overwrites unconditionally by path, so no change
was needed there: investigating a previously-seeded finding simply
replaces its stub body with the real one.

## Consequences

### Good
- Verified against production immediately: `houston run` went from
  `0 needing investigation` to `148 needing investigation` out of 149
  tracked findings, with the correct one (`et-114e7438`, already
  genuinely investigated) staying excluded.
- The backlog `houston seed` recorded on day one is now actually
  clearable through normal operation, not a permanent dead end.

### Bad
- None identified. This closes a straightforward correctness gap; no
  tradeoff was traded away.

### Follow-up
None expected. If a future state value is added to the front-matter
contract, decide explicitly whether it belongs in
`NEEDS_INVESTIGATION_STATES` rather than assuming.
