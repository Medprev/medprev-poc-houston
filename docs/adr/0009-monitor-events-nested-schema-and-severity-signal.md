# ADR-0009: Monitor events — nested attributes, real severity signal, no env scoping

**Status:** Accepted
**Date:** 2026-09-02
**Deciders:** Carla Cury (bug found live, fixed same session)
**Decision style:** Bug fix, twice over — the first implementation shipped
a silent bug that only surfaced by actually printing real output, not by
tests against a schema I'd only read, not queried.
**Related:** [[0007-observed-count-from-search-step]], [[0008-kubernetes-fingerprint-at-namespace-granularity]]

## Context

E1's third and final source, Monitor alert events (`source:alert`), closes
the plan's original three-source design. Three real surprises, none
guessable from the OpenAPI spec alone:

1. **The response nests one level deeper than its own schema implies.**
   `POST /api/v2/events/search`'s documented `V2EventAttributes` schema
   lists `message`, `tags`, `timestamp`, and a `oneOf` `attributes` field
   for category-specific data. What the spec doesn't make obvious: for a
   monitor alert, that `attributes.attributes` sub-object (`AlertEventAttributes`)
   is where `title`, `status`, `priority`, `service`, and a **structured**
   `monitor: {id, name, ...}` object all live — not at the top level
   alongside `message`/`tags`. A first version of `collect_monitor_findings`
   read `event["title"]` directly; it never raised an error, it just always
   fell through to the `monitor {id}` fallback, for every single finding,
   silently. Only printing real output (not just green tests) caught it —
   the fixtures I'd have hand-written from the spec would have encoded the
   same wrong assumption.
2. **The structured `priority` field is dead weight here.** Every one of
   56 real triggered events sampled reports `priority: "normal"`,
   regardless of the monitor's actual configured urgency. The real
   severity signal is the plain `priority:pN` **tag** (P1-P5) Datadog
   attaches separately; `status` (`error`/`warning`) is the fallback when
   no priority tag exists.
3. **`env` is not a reliable tag on this source**, unlike Error Tracking
   and Kubernetes. Of 56 real triggered (`status:error|warning`) events in
   a 96h window, only 4 carried an `env` tag at all. Scoping this query by
   `env:production`, matching the other two sources, would silently drop
   52 of 56 real incidents.

Separately, `medprev-product-backlog#5635` already established the house's
own operational answer to a directly analogous question for the
`#houston` Slack channel's Zabbix routing: recovery notifications
(`[RESOLVIDO]`) are noise, not signal, for anything meant to page or be
investigated. The same call applies here.

## Decision

`collect_monitor_findings` reads `event["attributes"]["monitor"]["id"]`
and `["name"]` (structured, when present) for fingerprint and reason,
falling back to regex-extracting `/monitors/{id}` from the message and
stripping the title's bracket prefix only when the `monitor` object is
absent. Severity: `priority:pN` tag when present, else `status`-based
(`error` → high, `warning` → medium). The query
(`source:alert (status:error OR status:warn)`) excludes `status:ok`
(recovery) events and is **not** scoped by `env`.

## Consequences

### Good
- Fingerprint and reason now come from the more reliable structured
  `monitor` object instead of parsing a rendered message string, when it's
  present.
- Real severity reflects what the team actually tagged (P1-P5), not a
  structured field that carries no information in practice.
- Not env-scoping means the source actually reports what it's for —
  dropping 93% of real incidents to match a pattern that worked for a
  different source would have been a much worse bug than the one caught.

### Bad
- The regex fallback for `monitor_id`/title-stripping is now dead code on
  every event sampled so far (the `monitor` object was always present) —
  kept because nothing guarantees every alert-event integration path
  populates it identically forever, and it's a cheap fallback to leave in.

### Follow-up
If a future finding shows the `monitor` object genuinely absent on some
event shape, that's the moment to check whether the fallback path was
ever actually exercised correctly (there's no direct evidence for it yet,
only the fixture-based test).
