# ADR-0004: The PAN gate only Luhn-checks 15/16-digit runs unless card-formatted

**Status:** Accepted
**Date:** 2026-09-01
**Deciders:** Carla Cury (found live, fixed same session)
**Decision style:** Bug fix discovered by running E5 against real production
data, not a design meeting.
**Related:** none yet

## Context

Running `houston seed` against the 101 real findings E1 collects produced
22 quarantined reports — 22% of everything the tool touched. Every
quarantine cited `pan`, the Luhn-validated card-number class from the PII
gate (E5).

The actual content: `observed.first_seen` / `observed.last_seen`, both
13-digit Unix epoch-millisecond timestamps written as bare integers in the
YAML front-matter (e.g. `last_seen: 1788270085136`). A random 13-digit
number passes the Luhn checksum roughly 1 in 10 times; with two independent
timestamp fields per report, at least one passing is expected in
`1 - 0.9² ≈ 19%` of reports — matching the observed 22/101 almost exactly.

Nothing in this codebase generates or accepts a real payment card number
anywhere. The gate was correct to scan the full rendered markdown (front
matter included, per its own design note), but the original PAN detector
treated any 13–19 digit run as a card candidate, with no discrimination
between "this looks like a card" and "this is a machine-generated integer
that happens to be the right length."

## Alternatives considered

1. **Stop scanning front-matter's numeric fields, body text only** — cheap,
   but breaks the stated invariant ("a stray PII in a structured field is
   still a leak") for no good reason: the false positive is specific to
   *this* field shape, not to front-matter in general.
2. **Widen `_luhn_valid` tolerance or drop PAN checking entirely** —
   rejected outright: removes real protection, not just the false positive.
3. **Narrow which digit-runs get Luhn-checked** — chosen. Real PANs are
   almost always 15 (Amex) or 16 (Visa/Mastercard/Discover) digits. A bare,
   unformatted 13/14/17-19-digit run is now skipped unless it carries a
   space or dash separator (how a human or an LLM actually writes a card
   number in prose); 15/16-digit runs are still checked regardless of
   formatting, since that length alone is common-enough evidence.

## Decision

`_CARD_CANDIDATE` still matches 13–19 digit runs, but only 15/16-digit
matches are Luhn-checked unconditionally. A 13/14/17-19-digit match is
Luhn-checked only if the matched text contains a `-` or a space.

## Consequences

### Good
- Re-running `houston seed` against the same 101 real findings: **0
  quarantined**, all 101 written to `reports/`. Verified, not assumed.
- The two new regression tests (`test_bare_epoch_millisecond_timestamp_is_not_a_false_positive_pan`,
  using the exact value that triggered this) fail loudly if this regresses.
- The invariant "the gate scans everything reaching disk, not just prose"
  is preserved — the fix narrows precision, not scope.

### Bad
- A genuinely unformatted 13/14-digit card number (rare, but not
  impossible in some regions/card products) would now pass uncaught. Judged
  acceptable: the previous behavior's false-positive rate (~1 in 5 reports)
  made the gate itself the operational bottleneck, which is a worse
  failure mode for a tool meant to run unattended across 10 rounds.

### Follow-up
If quarantine ever starts filling with a new pattern this length-based
heuristic doesn't name, revisit the detector rather than assume the gate
is complete.
