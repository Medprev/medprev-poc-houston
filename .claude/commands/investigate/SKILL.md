---
name: investigate
description: >-
  Runs the real houston agent (claude -p subprocess) on capped new Datadog findings, spending real
  Claude Code usage quota (the per-finding cap lives in houston/agent.py; run `mise run metrics`
  for what runs have actually cost). Use when the user wants to actually
  investigate new findings, not just preview them. Shows the finding count and cost cap before running,
  and surfaces the total spend after.
argument-hint: "[--max-findings N] [--max-budget-usd AMOUNT]"
---

# Investigate

Run `mise run investigate` to invoke the real agent on capped new findings. This spends real quota --
unlike every other houston task, this is not free.

## Usage
```bash
mise run investigate --max-findings 3
```

## Instructions

1. Parse `$ARGUMENTS` for `--max-findings` (default 5) and `--max-budget-usd`. **Never supply a
   default for the budget** -- read `DEFAULT_MAX_BUDGET_USD` from `houston/agent.py` and pass the
   flag only when the user actually set one. ADR-0024 raised that constant after a run died in
   `error_max_budget_usd` having spent $0.5280 and produced no report; a number pinned here instead
   of read from the constant is how that regression comes back.
2. Before running, state plainly: how many findings will be attempted and the worst-case spend
   (`max-findings * the cap`). This is a real cost, not a preview -- per ADR-0001, measure before
   assuming a larger batch, especially on the first run of a day.
3. Run `mise run investigate` with the parsed flags.
4. Report per-finding outcome (fingerprint, state, cost) and the total spend line the task prints.
   A finding that came back `state: incomplete` is not a failure to retry automatically -- it's a valid
   result (timeout or agent error); mention it, don't re-run it without being asked.
5. Remind the user that each written report still needs a human decision (`state: promoted` or
   `discarded`) before `mise run metrics` reflects a real false-positive rate.
