# ADR-0008: Kubernetes source stays in Slice 1, fingerprinted at namespace granularity

**Status:** Accepted
**Date:** 2026-09-02
**Deciders:** Carla Cury
**Decision style:** Measured, not estimated — the plan's own E2 rule was
applied in the order it was written: decide the threshold before seeing
the number.
**Related:** [[0007-observed-count-from-search-step]]

## Context

E1's original design named three collector sources: Error Tracking issues,
`source:alert` Monitor events, and Kubernetes Warning events. Only Error
Tracking was implemented at first, on the assumption that the Kubernetes
source was blocked by the `kubernetes` MCP server's `CONNECTION_CLOSED`
failure in this environment.

That assumption was wrong. The `kubernetes` MCP server is for direct
cluster access (kubectl-style); Kubernetes events reach **Datadog itself**
through the Datadog Agent's Kubernetes integration and are queryable like
any other Datadog event, with no dependency on that separate server.
Confirmed live: `source:kubernetes env:production` returns 17,888 events
over 96h in this account.

Two things had to be found by querying real data, because neither is
documented anywhere the plan or the OpenAPI spec could have named them:

1. **The severity facet is `status`, not `alert_type`.** `alert_type` is
   the field other Datadog products (RUM, APM) use for severity;
   Kubernetes events use `status: warn | info` instead. Querying
   `alert_type:warning` silently returns nothing — no error, just an empty
   facet. `status:warn` is the correct filter for what the plan calls
   "eventos Warning".
2. **There is no structured reason field.** The Kubernetes Event object's
   native `reason` (BackOff, Unhealthy, FailedScheduling, ...) is not a
   Datadog tag or attribute — it has to be parsed out of the event
   message's `**Reason**:` marker with a regex. Error Tracking's
   `error_type` field has no equivalent here.

E2's gate, run for real over 7 days of `status:warn` events in
`env:production` (7,387 raw events, no sampling):

| Granularity | Distinct fingerprints / 7 days | Per day |
|---|---|---|
| Per-workload (pod name) | 2,383 | **340.4** |
| Per-namespace | 50 | **7.1** |

## Decision

Per-workload fails the plan's own 30/day gate by more than 10×.
Per-namespace passes with margin. Per the plan's own rule ("coarsen to
namespace; if still over, drop the source"), Kubernetes **stays in Slice
1**, fingerprinted as `k8s-{cluster}-{reason}-{namespace}`, not
`k8s-{cluster}-{reason}-{workload}`. The specific pod that emitted a given
occurrence is kept in the finding's `raw` field for the agent to read
during investigation — it just doesn't fragment the fingerprint.

## Consequences

### Good
- The gate did exactly what it was designed for: caught a 340/day volume
  that would have flooded E3's investigation queue, before a single
  `claude -p` call was spent on it.
- At 7.1/day, Kubernetes now contributes a small, sane slice of the daily
  new-finding volume alongside Error Tracking's ~4/day already measured.

### Bad
- Two pods failing for the same reason in the same namespace now produce
  one report, not two — if they're actually unrelated root causes that
  happen to share a namespace and a Reason string, the report only
  reflects whichever pod's occurrence file `sample_by_fp` kept first, and
  the agent has to notice the ambiguity itself from `raw`.

### Follow-up
If a real report turns out to conflate two genuinely unrelated incidents
under one namespace-level fingerprint, split by `kube_kind` (e.g.,
Deployment vs. CronJob) before reverting to full per-workload granularity.
