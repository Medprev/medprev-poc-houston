# ADR-0014: A count travels with its window, and evidence points at one finding

**Status:** Accepted
**Date:** 2026-09-02
**Deciders:** Carla Cury (found in a full review of the E0 verification
branch; the Datadog query syntax below was verified live before it was
written into the collector)
**Decision style:** Bug fix in the evidence contract.
**Related:** [[0007-observed-count-from-search-step]], [[0008-kubernetes-fingerprint-at-namespace-granularity]], [[0011-datadog-links-and-portuguese-report-body]]

## Context

`observed_count` is scoped to the collection window (ADR-0007). The
investigation payload sent it next to a years-old `first_seen_ms` and no
window at all, so the model had no way to know which scope it was holding.
It narrated the window count as a cumulative total — "2272 ocorrências
desde 2025-03-18", "13.840 ocorrências acumuladas" — and that figure landed
in the `## Quanto` section of a ready-to-paste GitHub issue. Proof that the
count is window-scoped: between two runs the same findings moved
13643 -> 13613 and 2312 -> 2272, which a cumulative counter cannot do.
Three reports flagged the resulting mismatch against Datadog's own
`impact.total_errors` as an unexplained divergence; the explanation was the
window the model was never given.

Separately, the evidence a human is handed did not isolate the finding it
was attached to. `models.py` documents `query` as "the exact query that
produced this finding — reconferible evidence", but the collector stored
the source-wide query, and the Kubernetes deep link was scoped by namespace
only despite a comment claiming namespace + reason. On the real corpus six
findings in `medprev-rest-api` (Unhealthy, FailedScheduling,
FailedGetResourceMetric, ...) shared one byte-identical `datadog_url`, and
five more shared the `medprev-web-app` one. Kubernetes and monitor findings
also hardcoded `first_seen_ms`/`last_seen_ms` to `None` while holding event
timestamps, which made the prompt's mandated `## Linha do tempo` section
unfillable for 49 of 151 findings.

## Decision

The payload carries `window_from_ms` and `window_to_ms`, and the prompt
states the scope difference explicitly: cite `observed_count` with its
window, never combine it with `first_seen_ms` in one sentence, and explain
a divergence against a self-run query as a window difference rather than
leaving it unexplained. `raw` travels too, so the pod identity ADR-0008
drops from the fingerprint reaches the agent as that ADR claims.

Each finding stores the narrowest query that reproduces it, verified live
(2026-09-02) rather than assumed:

- Kubernetes: `... kube_namespace:<ns> <Reason>`. The reason has no facet
  on this endpoint, but the free-text term filters — 192 events against 409
  for the namespace alone, and every event in the scoped result carried
  `**Unhealthy**`. The deep link is built from that same query.
- Monitor: `... @monitor.id:<id>` — 72 events for one monitor over 30 days,
  while the bare tag form `monitor_id:<id>` returns zero.
- Error Tracking: the per-finding locator is the issue page in
  `datadog_url`; `query` stays the window-scoped query the volume came
  from, and `models.py` now says so instead of overclaiming.

Kubernetes and monitor findings record the window's own first and last
sighting from the event timestamps.

## Consequences

### Good
- No two findings share a deep link, so "the link that shows the error" is
  the link that shows *that* error.
- The mandated timeline section is fillable for all three sources.
- A count in a report or a promoted issue now says what it counted.

### Bad
- The Kubernetes reason is a free-text term, not a facet: a message that
  mentions another reason's name in its text can still be matched. It
  narrows honestly; it does not partition.
- The 151 reports already on disk keep the unscoped query and the shared
  links until the backfill is re-run.
