# ADR-0006: `--max-turns` does not exist — bound the agent by `--max-budget-usd` and a wall-clock timeout

**Status:** Accepted
**Date:** 2026-09-01
**Deciders:** Carla Cury (found live, corrected same session)
**Decision style:** Bug fix in the plan itself, found while implementing E4
against the installed CLI rather than against its `--help` output in the
abstract.
**Related:** [[0001-model-access-via-claude-code-cli]]

## Context

The parent plan specified `--max-turns 30` as E4's turn ceiling, in three
places (E4, E7, and the risk table), and cited
`medprev-skills/skill-creator/scripts/improve_description.py` and
`medprev-skills-qa/.../run_eval.py` as precedent for the `claude -p`
subprocess pattern.

Checked against the installed CLI (`claude --version` → `2.1.251 (Claude
Code)`): `claude --help` has no `--max-turns` flag, and no flag containing
the word "turn" as a limit at all. Neither cited precedent script actually
passes `--max-turns` either — the plan's premise was never verified against
either the CLI or its own cited example, only assumed by analogy to the
Claude API's `max_turns`-style agentic-loop parameters.

What the CLI does have: `--max-budget-usd <amount>` — "Maximum dollar amount
to spend on API" — and `--permission-mode <acceptEdits|auto|bypassPermissions|manual>`.
No turn-count knob exists at all in this version.

## Decision

E4 bounds a `claude -p` investigation two ways, neither of them turn-count:

1. **`--max-budget-usd`**, set conservatively per finding (E4's own token
   measurement from the first real round, per ADR-0001's consumption
   caution, decides the number — not guessed here).
2. **A subprocess-level wall-clock timeout** (Python's
   `subprocess.run(..., timeout=N)`), since nothing in the CLI itself caps
   wall-clock time or turn count. A timed-out investigation produces
   `state: incomplete`, per the plan's own existing rule that an incomplete
   result is valid and a fabricated one is not.

Every other reference to `--max-turns 30` in the parent plan (E4, E7, the
risk table) is superseded by this ADR; treat this file, not that table, as
current.

## Consequences

### Good
- The actual installed tool's flags govern the implementation, not an
  assumption carried over from the Claude API's shape.
- `--max-budget-usd` binds the thing the risk table actually cared about
  (cost per investigation), more directly than a turn count would have.

### Bad
- No hard step-count ceiling exists; a pathological loop that stays cheap
  in dollars but burns many turns is now bounded only by wall-clock time,
  not by turn count. Acceptable for a PoC at this volume; revisit if E7
  measurement shows this matters.

### Follow-up
Re-check `claude --help` for a turn-count or step-count flag on any future
CLI upgrade — this ADR is a snapshot of 2.1.251, not a permanent claim
about the tool.
