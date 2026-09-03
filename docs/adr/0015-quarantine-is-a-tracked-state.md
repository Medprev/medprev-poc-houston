# ADR-0015: Quarantine is a tracked state, and unfinished work blocks phase close

**Status:** Accepted
**Date:** 2026-09-02
**Deciders:** Carla Cury (found in a full review of the E0 verification
branch)
**Decision style:** Bug fix in the pipeline's bookkeeping.
**Related:** [[0003-pii-gate-from-first-commit]], [[0010-seeded-reports-stay-eligible-for-investigation]], [[0012-br-phone-gate-requires-a-real-separator]]

## Context

Two gaps in the same place: what the pipeline records about work it has
already paid for.

A PII hit wrote the full text to `reports/.quarantine/` (gitignored) and
left nothing in `reports/`. `write_report` returned `written=False`,
`cmd_investigate` printed `QUARANTINED` and exited 0, and dedup — which is
file existence plus `state` — never learned the finding had been handled.
`filter_needing_investigation` re-selected it, and `cap()`, ordering by
descending volume, put the same high-volume finding back at the front of
the queue. Each cycle cost another ~$0.32, and `metrics.py` had no
quarantine counter, so the loop was invisible in every number the
phase-close decision used. ADR-0012 records this happening for real to a
genuine root-cause finding.

`can_close_phase` counted only `state == "new"`. A run where all five
`claude -p` subprocesses time out writes five reports with
`state: incomplete` and no evidence, and `houston metrics` then printed
"phase can close: no report left in state: new" and exited 0 — directly
contradicting `dedup.py`'s own `NEEDS_INVESTIGATION_STATES` and ADR-0010,
which both define `incomplete` as tracked-but-unresolved.

## Decision

A PII hit still routes the full text to the gitignored quarantine, and now
also writes a redacted record to `reports/{fingerprint}.md` with
`state: quarantined`, the cost that was already spent, and a body saying
where the text is and how to resume. That record is itself run through the
gate; if its own structured fields trip it, they are the leak, so
`service`, `reason` and `datadog_url` are dropped and it is retried. If
even that trips, nothing is written and the CLI says so on stderr.

`quarantined` is not in `NEEDS_INVESTIGATION_STATES` — the investigation
happened and was paid for; what it needs is a human. `can_close_phase`
blocks on `new`, `incomplete` and `quarantined`. `seeded` still does not
block: it is pre-existing debt recorded deliberately (ADR-0010).

## Consequences

### Good
- The same finding is never investigated twice by accident, and the money
  spent on a quarantined investigation shows up in `houston metrics`.
- A phase can no longer close on a run where every investigation failed.

### Bad
- A quarantined finding is out of the automatic queue until a human acts on
  it. That is the intent, but it is a manual step the pipeline cannot do
  for itself: read the quarantined file, then set `promoted`/`discarded`,
  or delete the record to send the finding back to the queue.
