# ADR-0012: The Brazilian-phone gate requires an actual separator, not just digit count

**Status:** Accepted
**Date:** 2026-09-02
**Deciders:** Carla Cury (found live, on the very first real investigation
run under the new Portuguese prompt, fixed same session)
**Decision style:** Bug fix. Same class of bug as ADR-0004, on a
different regex.
**Related:** [[0004-pan-gate-scans-common-card-lengths-only]], [[0011-datadog-links-and-portuguese-report-body]]

## Context

The first real investigation run after ADR-0011's changes (a genuine
root-cause finding: a cascading percent-encoding bug in a city-slug
lookup) was quarantined. The report's own evidence section quoted the
malformed slug value verbatim — `fazenda-rio%2525252525...2520grande` —
because that string *is* the evidence: it shows the encoding bug directly.

The gate's Brazilian-phone regex, before this fix, required no separator
at all: `\(?\d{2}\)?\s?9?\d{4}-?\d{4}\b` matches a bare, unformatted
10-digit run just as readily as a properly-written phone number. The
substring `2525252525` — ten digits, no punctuation, lifted straight from
the repeating `%25` sequence — matched it by pure coincidence of shape.

This is the exact same failure mode as ADR-0004's epoch-millisecond
false positive: a gate regex built to only check "does this look like N
digits in roughly the right shape" instead of "does this look like how a
person actually writes this," applied to a domain (encoded URLs, hex IDs,
repeating technical patterns) that produces exactly the kind of
digit-heavy noise the loose regex was never tested against.

## Decision

`_BR_PHONE` now requires an actual separator between the area code and
the number (`(11)`, or a bare two digits with a mandatory following space/
dot/dash) **and** a mandatory dash before the last four digits. A bare,
unformatted run of digits — of any length — no longer matches, regardless
of how many digits it has or what shape they fall into.

Fixing this also surfaced an unrelated regex bug in the same line: the
leading `\b` anchor failed to match immediately before `(`, because `\b`
requires a transition between a word and non-word character, and both the
preceding space and the `(` itself are non-word — so `(11) 98888-7766`
was *never actually being matched by the original regex either*, parens
or not. The word boundary is now scoped to only the bare-digits
alternative, where it's actually meaningful (in the parens case, a naked
`(` already can't extend a word or digit run into an unrelated match).

## Consequences

### Good
- The exact report that surfaced this (a genuine, high-value root-cause
  finding) now reaches `reports/` instead of `.quarantine/`.
- Regression test uses the literal triggering string, same discipline as
  ADR-0004's.
- The parens-anchor bug fix means the regex is now *more* correct at
  catching real formatted phone numbers than it ever was before this
  change, not just less prone to false positives.

### Bad
- A genuinely unformatted 10-11 digit Brazilian phone number (rare in
  prose, but possible — e.g. copy-pasted from a system field with no
  formatting) would now pass uncaught. Same judgment call as ADR-0004:
  the false-positive rate this replaced made the gate itself the
  operational bottleneck for a tool meant to run unattended, which is the
  worse failure mode.

### Follow-up
CPF and CNPJ share the same class of risk (their regexes also make every
separator optional, so a bare 11 or 14-digit run could false-positive the
same way) but neither has actually been observed to misfire yet. Fix them
on the same evidence-first basis if and when a real one does — not
speculatively.
