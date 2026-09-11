# ADR-0028: promote files the issue, behind fail-closed guards

**Status:** Accepted
**Date:** 2026-09-11
**Deciders:** Carla Cury
**Decision style:** Closing the gap between the decision and the record it is measured by.
**Related:** [[0015-quarantine-is-a-tracked-state]],
[[0019-reason-is-the-diagnostic-label]],
[[0022-code-owned-timestamps-prebuilt-evidence-links-and-issue-outline]]

## Context

`houston promote` printed a `gh issue create` command and stopped. Filing
the issue and writing `issue:` + `state: promoted` back into the report
were two separate manual steps, and the second one is the one that
matters to this PoC: `metrics.false_positive_rate` is `None` until a
report is `promoted` or `discarded`, and `can_close_phase()` refuses
while any report is still `new`. A finding could be promoted in GitHub
and still count as unhandled here, because the record lives in a file
nobody was prompted to edit.

The printed form also has to survive a copy-paste through a shell. The
body is escaped for single quotes and runs to dozens of lines; on
11/09/2026, promoting `et-01cf6482-8474-11ee-a1fc-da7ad0900002` printed a
body that still carried the literal strings `window_from` and
`window_to` in its first section. Only a human reading the command
before pasting it caught that.

The decision that promotion measures is "actionable or noise". Typing
the command was never the deliberate part — it was the part ADR-0022's
issue outline was designed to make mechanical.

Writing to GitHub is not new here: `cmd_fix` already runs `gh issue
comment` and rewrites a report's front-matter after a fix PR opens.

## Decision

`houston promote <fingerprint>` still prints, and prints only. `--create`
files the issue through `gh issue create`, captures the URL it prints,
and writes `issue:` + `state: promoted` back into the report.

Filing is outward-facing — undoing it means a human closing an issue
other people already saw — so four guards run first, and any one of them
refuses the whole operation, leaving the report untouched:

1. the active `gh` account must be `carlacurymed`; an unreadable account
   counts as a failure, not as permission;
2. the report must not already carry an `issue:`, or a re-run files the
   same finding twice in a backlog other teams read;
3. the report must not be `quarantined` — that body is the redaction
   record of ADR-0015, not an investigation;
4. the issue body must carry no unexpanded marker: `window_from`,
   `window_to`, `{{ts:`.

With `--create` the body reaches `gh` through `argv`, never a shell, so
nothing needs quoting. Only the printed form is escaped, because only it
gets pasted into a shell.

`_update_fix_fields` becomes `update_front_matter(path, **fields)`,
shared by `fix` and `promote`. It does not re-run the PII gate: the
values it writes are a URL `gh` printed and a state this CLI chose, and
the body it leaves alone already passed the gate at write time.

## Consequences

A promoted finding is recorded as promoted in the same gesture that
promotes it, so `houston metrics` measures what actually happened rather
than what someone remembered to type. The printed path stays the default,
so reviewing the body before filing is still one command away, and a
mistyped fingerprint still costs nothing.

The duplicate guard sees only what the report records. An issue filed by
hand whose URL was never pasted back is invisible to it, and `--create`
would file a second one — the same failure this ADR removes from the
happy path, still reachable by not using it.

The marker guard is a list of three strings, not a template validator.
It catches what has been observed in a rendered body; a new placeholder
shape passes until it is added. The list belongs next to the renderer's
markers in `houston/timestamps.py` if a third one ever appears.

Both `gh` calls are mocked in the suite, which stays offline. What the
tests pin is the argv promote builds, the refusal of each guard, and
that a failed `gh issue create` leaves the report in `state: new` — no
issue means no promotion.
