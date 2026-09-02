# ADR-0016: The tool allowlist allows read verbs and fails closed

**Status:** Accepted
**Date:** 2026-09-02
**Deciders:** Carla Cury (found in a full review of the E0 verification
branch, by reading the committed allowlist rather than the generator)
**Decision style:** Security fix.
**Related:** [[0001-model-access-via-claude-code-cli]]

## Context

`scripts/generate_allowlist.py` built the read-only allowlist by
**blacklisting** write-verb substrings. A mutating tool whose name contains
none of those verbs passed straight through, and six did, into the
committed file the agent runs with against production:

- `clean-up-flag` — deletes a feature flag
- `clone_datadog_form`, `clone_llmobs_dataset` — create objects
- `ddsql_run_query` — arbitrary DDSQL execution
- `run_synthetics_tests` — triggers billable synthetic runs
- `verify-onboarding-flag` — mutates onboarding state

This contradicts `agent.py`'s own first line ("Read-only tools only") and
CLAUDE.md. `--disallowedTools Bash,Write,Edit` does not help: these are MCP
tools, not built-ins.

The tests could not have caught it. One asserted the committed file equals
the generator's own output; the other asserted no name in the file matches
the generator's own regex. Both are tautologies against the generator.

The substring approach was also wrong in the other direction: `set` inside
`dataset`, `run` inside `runtime`, `up` inside `uploads` — read-only tools
denied by coincidence of spelling.

## Decision

The filter fails closed. A tool is allowed only if one of its name tokens
is a read verb (`get`, `list`, `search`, `read`, `describe`, `analyze`,
`aggregate`, `find`, `explore`, `inspect`, `summarize`, `diff`, `expand`,
`rank`, `schema`, `count`, `coverage`, `status`, `history`, `details`,
`load`) **and** no token is a write verb. Tokens, not substrings, in both
directions — read-only tools like `monitor_groups_search` and
`ddsql_schema_search_tables` put the verb in the middle.

The tests now name real tool names on both sides: thirteen mutating tools
that must be absent, ten read-only tools the investigation cannot work
without, and the two substring traps.

Result: 222 tools allowed, down from 262. Nothing new was admitted; every
read tool the investigation needs is still there.

## Consequences

### Good
- A new mutating tool in a refreshed snapshot is denied by default, and it
  takes a deliberate edit to READ_VERBS to allow anything.
- `load_datadog_skill` is explicitly allowed: it is read-only, and the MCP
  server's own instructions ask for it before its data tools.

### Bad
- Roughly fifteen genuinely read-only tools are collateral, denied because
  their names declare no read verb: `cost_recommendations`,
  `build_audit_trail_query`, `validate_*`, `visualize_tabular_data`,
  `check-flag-implementation`, the `_dd_*` internals. None is needed to
  investigate a Datadog signal; add them by name if one ever is.
- The `*_onboarding` wizards are gone. They mutate; that is correct.
