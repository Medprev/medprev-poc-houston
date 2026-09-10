# ADR-0024: The investigation correlates logs by trace and classifies signal vs. noise

**Status:** Accepted
**Date:** 2026-09-10
**Deciders:** Carla Cury (found by reading a paid report against the same
Datadog data the agent had access to; every number below was measured live
in the report's own window, `1788711003325`–`1789056603325`)
**Decision style:** Bug fix in the conclusion the report exists to deliver.
**Related:** [[0011-datadog-links-and-portuguese-report-body]],
[[0014-window-scoped-counts-and-per-finding-evidence]],
[[0016-allowlist-allows-read-verbs-and-fails-closed]],
[[0022-code-owned-timestamps-prebuilt-evidence-links-and-issue-outline]]

## Context

The report for `et-161c8400-0c26-11ed-9fb1-da7ad0900002` (`$0.38`,
`state: new`) stopped at "causa raiz não confirmada", giving this reason:

> **Não consultei logs de aplicação nem o corpo das requisições** (fora do
> escopo de leitura seguro)

That scope restriction does not exist. `search_datadog_logs` and
`analyze_datadog_logs` are both in `houston/allowedtools.txt`, and the
prompt's own opening line names logs as something to query. The agent
invented a constraint and then reported a conclusion limited by it.

The prompt is what produced the invention. Its `## Evidência` section said
"Nunca cole linha de log ou dado de usuário" — a ban on *pasting* log
content, which exists because the PII gate cannot catch a person's proper
name (ADR-0003, ADR-0004). Read as one rule with the instruction to query,
it becomes a ban on *reading* logs at all.

What the missing query would have found, in one call:

| Measurement | Value | Query |
|---|---|---|
| Error spans on the route, by `@error.handling` | **15,248 / 15,248 `handled`**, `Unauthorized`, zero `unhandled` (single bucket) | `aggregate_spans` on `resource_name:sendValidationCodeForRegistrationDocumentationV2 status:error` |
| reCAPTCHA guard skipped for a missing site key, same route | **10,983** | `@context:GoogleRecaptchaGuard @recaptcha.skipReason:MISSING_SITE_KEY @recaptcha.route:OnlineCustomerController.sendValidationCodeForRegistrationDocumentationV2` |
| Same, all routes of the service | **25,715** | `@context:GoogleRecaptchaGuard status:warn "No recaptcha site key provided"` |
| reCAPTCHA actually refusing a request | **37** | pattern `Recaptcha verification refused the request` |
| Log records for the exception itself | **0** | `service:medprev-rest-api "UnauthorizedException"` |

One trace carries both halves: `trace_id:4daa12eb5e8307e4cb2f69b0f739a4c5`
is a `POST /v2/online/customers/is-pending-email-validation` returning
`http.status_code: 401`, whose error span is `handled`, and whose only
other log record is the reCAPTCHA guard reporting that it skipped
validation. The record that explained the error was one field away from the
error, in the same trace, and the report never looked.

Two conclusions follow, and the report reached neither. The exception is
noise: the service classifies 100% of it as a handled outcome, so it is an
expected result modeled as an exception, not a fault — and the report
instead described it as possible brute force or real login friction.
Behind it sits a defect more severe than the finding: a bot guard that
fails open on a public endpoint, warning and proceeding.

Reports are written by code from the model's body (`houston/frontmatter.py`),
so the fix belongs in the prompt, not in the file on disk.

## Decision

The prompt states three things it previously left implicit:

1. **Querying is mandatory, pasting is forbidden, and they are separate
   rules.** Every tool in the agent's list is in scope for the
   investigation; the restriction governs what the model *writes*, never
   what it *reads*. Writing that a query was out of scope is always false.
2. **Correlate by `trace_id`.** Take an occurrence's trace and list every
   log and span in it before concluding anything about cause. The
   explanation usually sits in a neighbouring record at another level.
3. **Classify signal vs. noise, with the number.** Aggregate the error
   spans by `@error.handling` and `@http.status_code`. An error that is
   entirely `handled`, with no failure log, is noise in Error Tracking, and
   saying so is a valid conclusion. When it is noise, the defect to report
   is the noise itself and whatever the trace correlation surfaced — never
   a cause invented to fill the section.

"Não determinada" now has to carry the list of queries actually run and
what each returned, empty results included. Without that list it is not an
acceptable conclusion.

## Consequences

A report can now conclude "this is noise" and still be useful — the
`discarded` state stops meaning "the investigation failed" and starts
meaning "the investigation answered". `houston metrics` reads
`false_positive_rate` from exactly those states, so the number it computes
becomes a measurement of the *sources* rather than of the agent's
willingness to commit.

The cost is more tool round-trips per finding: log and span queries the
agent skipped before. The `$0.50` cap and the wall-clock timeout are
unchanged, so a finding needing more correlation than the cap allows lands
as `state: incomplete` rather than as a confident wrong answer — which is
the trade this PoC already made in ADR-0006.

The paste ban itself is unchanged and still load-bearing. The same
investigation window contains an `info` log whose payload carries a
customer's full name and id, exactly the proper-name gap ADR-0003 and
ADR-0004 document the gate cannot catch. Keeping that field is a deliberate
decision of the service's logging contract, which is why the mitigation
stays where it was: reference the query, never the content.
