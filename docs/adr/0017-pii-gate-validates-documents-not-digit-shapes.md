# ADR-0017: The PII gate validates documents, not digit shapes

**Status:** Accepted
**Date:** 2026-09-02
**Deciders:** Carla Cury (found in a full review of the E0 verification
branch; each case below was executed against the gate before it was changed)
**Decision style:** Bug fix. Third instance of the same class as ADR-0004
and ADR-0012, fixed structurally this time.
**Related:** [[0003-pii-gate-from-first-commit]], [[0004-pan-gate-scans-common-card-lengths-only]], [[0012-br-phone-gate-requires-a-real-separator]]

## Context

ADR-0004 stopped Luhn-checking bare 13-digit epoch timestamps by requiring
card-like separator formatting at uncommon lengths. The check was
`" " in candidate or "-" in candidate`, computed on the match text — and
`_CARD_CANDIDATE`'s trailing optional `[ -]` had already swallowed the
delimiter *after* the digits. So the bug reopened immediately:

- `scan("em 1788293058029 ocorreu") == ['pan']` — and 1788293058029 is this
  branch's own `window.to_ms`
- `scan("duration 1788270085136 ns") == ['pan']`
- `scan("Primeira ocorrencia 2022-07-25 2026-09-01 ainda ativo") == ['pan']`
  — two space-separated ISO dates are 16 Luhn-valid digits, and the prompt
  mandates a `## Linha do tempo` section made of exactly that

ADR-0012's Follow-up predicted the CPF/CNPJ version of this, and it was
already real: `scan("span_id: 12345678901") == ['cpf']` and
`scan("trace_id: 12345678901234") == ['cnpj']`, because every separator in
those regexes was optional, so any bare 11- or 14-digit run matched.

In the other direction, ADR-0012 bought its fix by requiring a dash before
the last four digits, which dropped the most common real formats:
`(41) 999998888`, `41999998888`, `+55 41 99999 8888` and `4133334444` all
passed the gate uncaught. The parenthesised-area-code-without-dash form is
standard in Brazilian data and was not among the cases ADR-0012's
Consequences section accepted losing.

Each false positive quarantines an investigation that was already paid for
(ADR-0015), which is why the gate's error rate is an operational cost in
both directions, not a cosmetic preference.

## Decision

Structure, not digit count:

- **Cards.** Separators may only sit between digits
  (`\b\d(?:[ -]?\d){12,18}\b`), so a trailing delimiter can no longer be
  read as formatting. A separator-formatted candidate qualifies only with
  card grouping: one separator character throughout, groups of 4+ digits
  (last may be 3+). Visa and Amex grouping pass; a pair of ISO dates does
  not. A bare run qualifies only at 15 or 16 digits (ADR-0004's rule).
- **CPF/CNPJ.** Canonical punctuation (`.`, `-`, `/`) is treated as a
  declaration of intent and still matches. A bare run must pass the real
  check-digit algorithm, and a run of identical digits never does.
- **Phone.** Shape plus an assigned area code, so the unformatted real
  formats are caught while `2525252525` — ADR-0012's live false positive,
  whose "25" is not an assigned DDD — stays out.

## Consequences

### Good
- 31 cases, including every one above and every case from ADR-0004 and
  ADR-0012, are asserted in `tests/test_pii_gate.py`.
- Phone coverage is strictly better than before ADR-0012, not traded away.
- A bare valid CPF or CNPJ, previously only caught by accident of shape,
  is now caught on purpose.

### Bad
- A CPF/CNPJ-shaped run with a *wrong* check digit (a redacted or
  fabricated document number) passes uncaught unless it carries
  punctuation. Real ones validate.
- **Accepted, measured gap:** a Luhn-valid PAN embedded in a digit run of
  20+ characters is not scanned. Sliding a 16-digit window over a 28-digit
  id gives 13 windows at roughly 10% Luhn odds each — about 75% odds of
  quarantining any report that quotes one long technical id. The gate would
  become the bottleneck again, which ADR-0012 already showed is the worse
  failure mode. Asserted as a deliberate gap in the tests.
- The proper-name gap of ADR-0003 is untouched.
