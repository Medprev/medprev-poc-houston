# ADR-0001: Reach the model through the `claude -p` subprocess, not a LangChain chat model

**Status:** Accepted
**Date:** 2026-09-01
**Deciders:** Carla Cury
**Decision style:** Autocratic. Evaluated in a design conversation after LangChain entered
scope as a possible framework for the agent layer (E4).
**Related:** none yet

## Context

E4 needs one process per finding that reads Datadog, reasons over the evidence, and returns
a report — without ever getting write access to disk. The original design already had this
solved with `claude -p` as a subprocess, the same pattern already in production use at
`medprev-skills/skill-creator/scripts/improve_description.py` and
`medprev-skills-qa/skill-creator/scripts/run_eval.py` (both strip `CLAUDECODE` from the env
to allow nesting).

LangChain came up as a possible replacement, on the premise that "the house already uses
LangChain." That premise doesn't hold: a full org code search turned up exactly one
occurrence, the AI Agent node inside an n8n workflow in
`medprev-support-automation/docs/contexto/arquitetura-existente.md:177` — not code this repo
owns, and not a precedent for a new Python codebase.

This is a PoC on a personal Medprev account. The explicit constraint from the deciders: no
new Anthropic API key on the company account for a PoC.

## Alternatives considered

1. **`langchain_anthropic.ChatAnthropic`** — authenticates only by `anthropic_api_key`
   (confirmed against the class reference: the constructor's auth surface is
   `anthropic_api_key`, `anthropic_api_url`, `default_headers`, `anthropic_proxy`; no OAuth
   path exists). Rejected: requires the API key the constraint rules out.
2. **Claude Agent SDK** — same requirement, and the SDK's own documentation states it
   explicitly: *"Unless previously approved, Anthropic does not allow third party
   developers to offer claude.ai login or rate limits for their products, including agents
   built on the Claude Agent SDK. Use the API key authentication methods."* Rejected on the
   same ground, reinforced by the vendor's own policy.
3. **`claude -p` as a subprocess** — authenticates via the Claude Code credential already on
   this machine (the same one an interactive session uses). The same SDK documentation
   sanctions this explicitly: *"To drive the same agent loop from another language, run the
   CLI as a subprocess with the `-p` flag and `--output-format json`."* Chosen.

A LangGraph-as-pipeline variant (nodes as plain functions, `claude -p` still doing the model
call) was also evaluated and rejected on its own terms: `reports/{fingerprint}.md` existing
already is the round's checkpoint, so a `StateGraph` buys almost nothing here. Recorded in
the design conversation, not a separate ADR — no code depends on it.

## Decision

The agent layer stays a `claude -p` subprocess call: fixed prompt, finding as JSON on
stdin, `--allowedTools` generated from the MCP tool inventory (write verbs filtered out),
`--disallowedTools Bash,Write,Edit`, `--max-turns 30`, `--output-format json`.

## Consequences

### Good
- No new credential, no new fatura on the company account — the constraint holds by
  construction, not by discipline.
- `--output-format json` gives cost in USD directly (`response.usage` equivalent); a
  chat-model route would only give token counts, pushing USD conversion onto this repo.
- The write-access trap (`--disallowedTools`) is unchanged from the original design.

### Bad
- Consumption comes out of the Claude Code account's usage quota, not a metered API bill.
  At up to 15 findings/day and up to 30 turns each, across 10 rounds (E7), this can hit a
  usage ceiling mid-round. Mitigated by measuring the first round's consumption before
  assuming the full ten, and by treating a mid-round failure as `state: incomplete` rather
  than a fabricated result.
- No task-level retry/backoff exists yet at this layer; it has to be written by hand in E4
  if the failure mode above proves common in practice.

### Follow-up
Revisit only if investigation stops being one shot per finding and needs branching or a
human-in-the-loop interrupt mid-investigation — that is the trigger for a real
orchestration layer, not volume or reliability.
