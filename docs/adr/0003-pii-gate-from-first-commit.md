# ADR-0003: The PII gate runs from commit 1, not from org transfer

**Status:** Accepted
**Date:** 2026-09-01
**Deciders:** Carla Cury
**Decision style:** Autocratic, inherited from the parent design and reaffirmed at
implementation time.
**Related:** none yet

## Context

This repo starts as `carlacurymed/medprev-poc-houston`, private, on a personal account, and
is expected to transfer to the Medprev org once Slice 1 produces a measured false-positive
rate. A GitHub repository transfer carries its full git history — every commit, on every
branch — to the new owner. Rewriting history after the fact (to scrub something that
shouldn't have been committed) is expensive and, once anything has been fetched or forked,
not fully reversible.

Separately, `medprev-product-backlog#5748` ("Dado pessoal de cliente indexado no log do
caminho de pagamento") is open and unresolved since 2026-08-25: production logs already
carry customer PII into a system this codebase reads from (Datadog). Evidence the agent
pulls from those logs can carry that PII forward into a report.

The regex-based gate (E5) is not complete protection: it catches CPF, CNPJ, email, Brazilian
phone numbers, and Luhn-validated card numbers, but not a person's name in free text. That
residual gap is real and stays real until #5748 closes — the gate reduces exposure, it does
not eliminate it.

## Alternatives considered

1. **Add the PII gate only when transferring to the org** — cheaper to skip during solo
   development, since the repo is private and only one person reads it. Rejected: the
   transfer takes history with it. Anything written before the gate existed ships intact to
   the org regardless of when the gate is added — the gate has to have been running for
   every commit that will ever be transferred, which means running from the first one.
2. **Gate from commit 1** — chosen. Every write to `reports/` passes through the gate before
   the file exists, from the very first report this PoC produces.

## Decision

The PII gate (CPF, CNPJ, email, Brazilian phone, Luhn-validated PAN) runs before every
write to `reports/`, starting with the first report E5 produces — not deferred to a later
milestone or to org transfer. A report that fails the gate goes to `reports/.quarantine/`,
which is gitignored, never `reports/` itself.

## Consequences

### Good
- No retroactive history cleanup is ever needed at transfer time — the invariant "nothing
  ungated reached git" holds for the entire life of the repo by construction.
- Forces the gate to exist before the first real report is produced, rather than being
  deferred until "there's something to protect."

### Bad
- The gate has a known, undeferred gap: a person's proper name is not regex-matchable and
  still leaks. The mitigating practice — evidence stored only as a pointer + query, never a
  pasted log excerpt — depends on discipline in E4's prompt, not on the gate itself.
- Full closure of this residual risk depends on `medprev-product-backlog#5748`, which this
  repo does not own and cannot close.

### Follow-up
Revisit the gate's coverage if #5748 closes (the underlying log exposure may narrow what
this gate still needs to catch) or if quarantine ever fills with a pattern the current
regex set doesn't name.
