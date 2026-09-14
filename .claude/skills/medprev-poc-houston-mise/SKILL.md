---
name: medprev-poc-houston-mise
description: >-
  medprev-poc-houston task runner -- all repeatable workflows (setup, lint, test, and the houston
  pipeline itself: run, seed, investigate, promote, metrics) run through mise as `mise run <task>`.
  Use whenever running, adding, or debugging a setup/lint/test/pipeline command in this repo, or when
  tempted to `python -m houston.cli ...` or `source .venv/bin/activate && pytest ...` directly -- that
  means reaching for the mise task instead. Single toolchain (Python), flat task names, no namespace.
---

# medprev-poc-houston mise tasks

All repeatable work is a mise task. Prefer `mise run <task>` over activating the venv and invoking
`pytest`/`python -m houston.cli` directly -- mise resolves the pinned Python version and the project
venv consistently.

## Tasks

- `mise run setup` -- install dependencies (requirements-dev.txt) into the project venv
- `mise run lint` -- `ruff check .`
- `mise run test [pattern]` -- run the test suite (`pytest -k <pattern>` if given). No network: everything
  hits recorded fixtures or mocked `subprocess` calls.
- `mise run run --window-hours 96` -- collect + dedup + cap, print what *would* be investigated. Read-only,
  free.
- `mise run seed --window-hours 96` -- record pre-existing findings as `state: seeded`, no investigation.
  Free.
- `mise run investigate --max-findings 5` -- run the real agent (`claude -p` subprocess) on capped
  new findings, write real reports. **Spends real Claude Code usage quota.** Pass
  `--max-budget-usd` only to override; the per-finding cap has one source of truth,
  `houston/agent.py:DEFAULT_MAX_BUDGET_USD`, and the task forwards the flag only when you set one --
  a number pinned in a doc is exactly the drift ADR-0024 measured and fixed. `mise run metrics`
  reports what runs have actually cost.
- `mise run promote <fingerprint>` -- print (never run) a ready `gh issue create` for one report.
- `mise run metrics` -- false-positive rate, cost percentiles, and whether the phase can close (refuses
  while any report is `state: new`).

## Adding a task

1. Create an executable bash file at `.mise/tasks/<task>` (flat, no namespace -- single toolchain).
2. Add `#!/usr/bin/env bash`, `set -e`, and `#MISE description="..."` (and `#USAGE` for args/flags).
3. `chmod +x` it and confirm with `mise tasks`.

## Rule

Every repeatable workflow is a mise task. If you reach for `source .venv/bin/activate && <cmd>` or
`python -m houston.cli` directly, a task is probably already there -- use it instead of running raw.
