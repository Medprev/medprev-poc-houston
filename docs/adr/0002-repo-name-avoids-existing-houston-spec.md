# ADR-0002: Repository named `medprev-poc-houston`, not `medprev-houston`

**Status:** Accepted
**Date:** 2026-09-01
**Deciders:** Carla Cury
**Decision style:** Autocratic. Resolved before repo creation, once the collision surfaced.
**Related:** none yet

## Context

The plan this repo implements inherited the name "Houston" from its parent architecture
document ("Vigília"), without checking whether the name was already spoken for in the
backlog. Before creating the repository, a check against `Medprev/medprev-product-backlog`
found it was:

- **#242** (opened 2025-03-12, by wellnovaes): specifies `medprev-houston` as a Node.js
  project in hexagonal architecture, deployed to Lambda (test/hml/prd), with SQS/SNS
  messaging — a system that **reacts** to events (Slack alert, email, firewall rule).
- **#5483** (opened 2026-08-05, by Carla Cury): an umbrella issue wrapping #242 under the
  same name, "single point of reception and routing for system events."
- **#5635** (opened 2026-08-18): confirms `#houston` is already the infra paging channel in
  production, with a live Zabbix routing rule.

This repo is the opposite shape: Python, local CLI, reads Datadog, **produces** a report.
No `medprev-houston` repository exists yet under any account, so nothing is being renamed
out from under existing code — but the name was already committed to a different spec, by
a different author, with production usage riding on the same word (the paging channel).

## Alternatives considered

1. **Reuse `medprev-houston` for this PoC** — closest to the original design document's
   wording. Rejected: would require re-scoping #242/#5483 first, which is a conversation
   with another stakeholder (wellnovaes) — exactly the kind of dependency the slicing
   decision in the parent plan was meant to avoid before starting.
2. **Proceed as `carlacurymed/medprev-houston` and resolve at org transfer** — costs
   nothing today. Rejected: the plan's own PII-gate reasoning applies here too — a
   collision is cheap to fix now and expensive once the name is in CI, IaC, docs, and git
   history at transfer time.
3. **Rename now, before any code exists** — chosen. `medprev-poc-houston` follows the
   `medprev-poc-*` naming already in use (`medprev-poc-monitoring`) and reads as
   provisional, which this repo is.

## Decision

Repository: `medprev-poc-houston`. CLI binary name stays `houston` (`houston run`,
`houston metrics`) — the PoC prefix belongs to the repo, not to every command a human types.
`medprev-houston` remains free for #242/#5483.

## Consequences

### Good
- Zero conversation needed to unblock E0 — no scope negotiation with another issue's author.
- No ambiguity in Slack or in the backlog between "the paging channel", "the event-reaction
  project", and "the signal-triage PoC."

### Bad
- If this PoC graduates past Slice 1 and moves to the org, `medprev-poc-houston` is not the
  final name either — a second rename is likely, this time with real history to carry.

### Follow-up
If #242/#5483 are ever formally dropped or renamed, `medprev-houston` becomes free and this
repo's own transfer-time name can be reconsidered.
