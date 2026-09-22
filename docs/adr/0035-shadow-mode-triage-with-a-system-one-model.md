# ADR-0035: Shadow-mode triage with a System One model, before any investigation is skipped

**Status:** Accepted (shadow mode only; the API contract is unverified against a live key)
**Date:** 2026-09-22
**Deciders:** Carla Cury
**Decision style:** New capability behind a port, measured before it is allowed to act.
**Related:** [[0001-model-access-via-claude-code-cli]], [[0005-pages-summary-redacted-and-not-yet-enabled]],
[[0013-cost-includes-cache-tokens-and-failed-runs]], [[0018-cap-ranks-severity-then-round-robins-sources]],
[[0023-agent-model-and-effort-are-pinned]], [[0024-investigation-correlates-logs-and-classifies-noise]],
[[0031-model-runner-is-a-port]], [[0034-the-write-back-path-is-typed-and-a-fix-attempt-records-what-it-billed]]

## Context

Every finding the cap keeps costs a full `claude -p` investigation, ~$0.30–$0.42 on the pinned
Sonnet default (ADR-0023). Some of that spend buys a verdict of "noise": ADR-0024's
`UnauthorizedException` was 15,248 of 15,248 `handled` spans, an expected outcome modeled as an
exception, and it took a paid investigation to say so. Of the 9 reports a human has decided so far,
2 are `discarded`.

TypeSafe's Jev (launched 2026-09-15) is a "System One" model: structured state plus typed questions
in, calibrated probabilities out, no generated text. It is priced at $0.042 per million input tokens
with output free, so one triage of a finding's structured fields (~400–1,000 tokens) costs about
$0.00004, roughly 1/9,000 of one investigation. It cannot investigate, since it cannot write a report,
but it can make the decision in front of one.

What we do not know yet is whether its verdicts are right on *our* signals. The vendor's speed,
cost, and calibration claims are a week old and unmeasured here, and 9 human decisions are too few
to trust it with skipping anything.

## Decision

Add triage as a **shadow-mode** step: every verdict is recorded and measured, and none is acted on.

1. **A port.** `houston/triage.py` defines `Classifier` (`classify(report) -> Triage`, raising
   `TriageError` and nothing else), the same shape as `ModelRunner` (ADR-0031). `JevClassifier` is
   the one implementation. Tests use a fake and never reach the network.
2. **The state is a whitelist of front-matter fields**: source, reason, service, severity, novelty,
   in-window count, window length, active span. It is never `Finding.raw` and never a report body.
   This is the line `generate_site.py` already draws (ADR-0005), and it matters more here because
   this is a new third party receiving Datadog-derived data. `triage_state` takes a `Report`, so the
   same function serves a live finding (`Report.from_finding`) and a report already on disk.
3. **The PII gate runs before the network.** A serialized state that trips `pii_gate.scan` is
   refused with no request made.
4. **Fail open.** Refusals, HTTP errors, and unrecognized response shapes are all `TriageError`. The
   pipeline records no verdict, warns, and investigates as it would have. A triage outage never
   costs an investigation, and never silently drops one.
5. **After the cap, not before.** `plan_run` triages only `kept`, so shadow mode cannot move a
   finding in or out of the cap (ADR-0018). Moving it before the cap is part of the later enforcing
   decision, not this one.
6. **Recorded like a cost.** `Report.triage` holds decision, confidence, probabilities, the model
   that served it, input tokens, and `usd`, which code computes from the billed tokens (ADR-0013).
   The block is rendered only when present, like `fix_cost`, so the 153 committed reports are
   unchanged. `record_triage` patches it onto an existing report the way `record_fix_attempt` does
   (ADR-0034). It is a label from a closed set plus numbers, with no free model text.
7. **Measured against the human.** `houston metrics` reports verdicts, triage spend (apart from
   `usd_total`), and agreement keyed by (decision, state). `noise_on_promoted` is the cell that
   matters: a finding a human filed as an issue that triage would have skipped.
8. **A backfill.** `houston triage` records verdicts on `promoted`, `discarded`, and `seeded`
   reports. The whitelist is what makes a verdict on an already-decided report a fair test: Jev sees
   exactly what it would have seen before the investigation, and never `state`, `issue`, or the body.

The opt-in is `--triage shadow` on `run`/`investigate` (default `off`), plus `TYPESAFE_API_KEY` in
`.env`. A command asked to triage without a key refuses up front instead of running untriaged.

## What is not verified

This sandbox's egress policy blocks `docs.typesafe.ai` and the API host. The request shape
(`POST https://api.typesafe.ai/v1/systemone` with `model`, `state`, and a `choice` question with
`criteria`) and the response shape (`answers.<q>.choice/probabilities/confidence`,
`usage.input_tokens`, `model`) are taken from the public API reference as quoted in secondary
sources. They live in `_request_body` and `_verdict_from` and nowhere else, and
`tests/fixtures/jev_choice_response.json` is the public example, not a recorded response. The first
live call has to confirm both and replace the fixture with a real one, the way `docs/e0-verification.md`
did for Datadog. An unrecognized shape already fails open, so a mismatch shows up as warnings and not
as wrong verdicts.

`DEFAULT_MODEL = "jev-latest"` is an alias, not a pinned version. ADR-0023's rule (never let the
tier float) matters less here because output is free and input is priced the same across versions,
but the verdict still records the version that served it, so a behavior change is traceable.

## Consequences

**Good.** The question "would this have been noise?" gets a measured answer per report for fractions
of a cent, without changing a single investigation. The 9 decided reports can be scored today with
the backfill, before any live run.

**Bad.** It adds a second model vendor and a new outbound dependency (the environment's network
policy has to allow the API host). `houston run --triage shadow` is no longer strictly free, though
it costs fractions of a cent. A verdict on a decided report is only as honest as the whitelist, so a
field added to `triage_state` has to be checked against leaking the decision.

**Enforcing is a separate decision.** Letting a verdict skip an investigation needs its own ADR with
a threshold measured here. The starting proposal is ≥30 decided reports, zero `noise_on_promoted` at
the chosen confidence floor, and a non-blocking state for a skipped finding so it is neither
silently lost nor counted by `can_close_phase()` as owed work.
