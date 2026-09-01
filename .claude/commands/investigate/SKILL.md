---
name: investigate
description: >-
  Runs the real houston agent (claude -p subprocess) on capped new Datadog findings, spending real
  Claude Code usage quota (~$0.24-0.40/finding, measured live). Use when the user wants to actually
  investigate new findings, not just preview them. Shows the finding count and cost cap before running,
  and surfaces the total spend after.
argument-hint: "[--max-findings N] [--max-budget-usd AMOUNT]"
---

# Investigate

Run `mise run investigate` to invoke the real agent on capped new findings. This spends real quota --
unlike every other houston task, this is not free.

## Usage
```bash
mise run investigate --max-findings 3 --max-budget-usd 0.50
```

## Instructions

1. Parse `$ARGUMENTS` for `--max-findings` (default 5) and `--max-budget-usd` (default 0.50). If the
   user gave neither, use the defaults but say so explicitly -- don't silently assume a larger cap.
2. Before running, state plainly: how many findings will be attempted and the worst-case spend
   (`max-findings * max-budget-usd`). This is a real cost, not a preview -- per ADR-0001, measure before
   assuming a larger batch, especially on the first run of a day.
3. Run `mise run investigate` with the parsed flags.
4. Report per-finding outcome (fingerprint, state, cost) and the total spend line the task prints.
   A finding that came back `state: incomplete` is not a failure to retry automatically -- it's a valid
   result (timeout or agent error); mention it, don't re-run it without being asked.
5. Remind the user that each written report still needs a human decision (`state: promoted` or
   `discarded`) before `mise run metrics` reflects a real false-positive rate.
