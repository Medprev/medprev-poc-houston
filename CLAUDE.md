# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

PoC: investigates Datadog signals (Error Tracking, Kubernetes events; Monitor `source:alert` events not yet implemented), deduplicates them, runs one `claude -p` subprocess per new finding to investigate root cause, and writes the result as a versioned Markdown report with structured front-matter — after the full rendered file passes a PII gate. Nothing the agent produces reaches disk directly: it has no `Write`/`Edit`/`Bash` tools, so every report is written by this Python code, never by the model.

Derived from the Vigília architecture document ("Versão mínima" tab). Every non-obvious design decision — and every bug found by actually running this against production data — is recorded in `docs/adr/`; read the relevant one before changing behavior it documents, and add a new one when you make a comparable decision or fix a comparable bug.

## Setup

Task runner: [mise](https://mise.jdx.dev), single toolchain (Python 3.14, flat task names — no
namespace, see `.claude/skills/medprev-poc-houston-mise/SKILL.md`). Prefer `mise run <task>` over
activating the venv directly; if you're about to `source .venv/bin/activate && <cmd>`, check `mise
tasks` first — it's probably already there.

```bash
mise trust   # first time only, in a fresh clone
mise run setup
cp .env.example .env
# fill in DD_API_KEY and DD_APP_KEY (read-scoped) and DD_SITE
```

Without mise: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt`.

## Commands

```bash
# run the whole test suite (no network — everything hits recorded fixtures or mocked subprocess calls)
mise run test
# equivalent to: python -m pytest tests/ -q  (bare `pytest` fails -- see the comment in .mise/tasks/test)

# run a single test
mise run test kubernetes_findings_fingerprint_by_namespace_not_workload
# equivalent to: python -m pytest tests/test_collector.py::test_kubernetes_findings_fingerprint_by_namespace_not_workload -v

# lint
mise run lint   # ruff check .

# regenerate houston/allowedtools.txt from the committed MCP tool snapshot
python scripts/generate_allowlist.py

# regenerate the static incident-summary page (site/, gitignored)
python scripts/generate_site.py
```

The `houston` CLI, reached through mise (`mise run run`, `mise run seed`, `mise run investigate`,
`mise run promote <fingerprint>`, `mise run metrics`) — each wraps `python -m houston.cli <command>`:

| Command | What it does | Costs money/quota? |
|---|---|---|
| `houston run` | Collect + dedup + cap, print what *would* be investigated | No — read-only Datadog REST calls |
| `houston seed` | Record pre-existing findings as `state: seeded`, no investigation | No |
| `houston investigate` | Run the real agent (`claude -p` subprocess) on capped new findings, write real reports | **Yes** — real Claude Code usage quota, ~$0.24–$0.40/finding measured live. Default `--max-findings` is 5, deliberately small |
| `houston promote <fingerprint>` | Print (never run) a ready `gh issue create` command from a report's own "Issue body" section | No |
| `houston metrics` | Compute false-positive rate, cost percentiles, and whether the phase can close | No |

## Architecture

The pipeline is six deterministic steps around one LLM step, and the LLM step is the only one that costs money or touches the network beyond read-only Datadog calls:

```
collector → dedup/cap → [claude -p, read-only tools] → PII gate → write → (human decides state) → metrics
```

- **`houston/datadog_client.py`** — thin REST v2 wrapper. Two schema facts that are easy to get wrong and already caused real bugs (see ADR-0007, ADR-0008): Error Tracking's search endpoint returns only `{id, total_count}` per result — full attributes (`first_seen`, `regression`, ...) need a second `GET /issues/{id}` per finding, and that second call's response has **no** `total_count` field at all. The Events Search endpoint (`/api/v2/events/search`, used for Kubernetes) accepts relative date-math strings (`now-96h`) for `from`/`to`; the Error Tracking search endpoint does not — it requires epoch milliseconds. Don't assume the two v2 search endpoints behave the same way.
- **`houston/collector.py`** — one `collect_*_findings()` function per source, each normalizing into the same `Finding` shape (`houston/models.py`), each carrying the exact query that produced it (reconferible evidence). Kubernetes events are fingerprinted at **namespace** granularity, not per-workload — measured live over 7 real days (ADR-0008): per-workload was 340/day (fails the 30/day gate), per-namespace is 7/day (passes).
- **`houston/fingerprint.py`** — pure functions, one per source (`et-{issue_id}`, `mon-{monitor_id}[-{group}]`, `k8s-{cluster}-{reason}-{namespace}`). No I/O, no LLM; this is what makes dedup deterministic.
- **`houston/dedup.py`** — `reports/{fingerprint}.md` existing on disk *is* the entire dedup mechanism. No separate index or database.
- **`houston/agent.py`** — the one step that shells out to `claude -p`. `CLAUDECODE` is stripped from the subprocess env to allow nesting (same pattern as `medprev-skills/skill-creator/scripts/{run_eval,improve_description}.py`). Bounded by `--max-budget-usd` and a Python-level `subprocess.run(..., timeout=...)` wall-clock cap — **not** `--max-turns`, which does not exist in the installed CLI (ADR-0006; verify against `claude --help` before assuming otherwise if the CLI version changes). `--allowedTools` is read from `houston/allowedtools.txt`, generated by `scripts/generate_allowlist.py` from `houston/mcp_tool_inventory_snapshot.txt` (a committed, hand-refreshed snapshot of the Datadog MCP server's tool names — there's no scriptable "list tools" introspection, so refresh the snapshot by hand via a Claude Code session's `ToolSearch` when the server's tool set changes). `--disallowedTools Bash,Write,Edit` is hardcoded regardless of the allowlist. A timeout or non-zero exit produces `state: incomplete`, never a fabricated result.
- **`houston/frontmatter.py`** — the report contract and the *only* path anything reaches `reports/` through. `write_report()` renders front-matter + body to Markdown and runs `houston/pii_gate.py` over the **full rendered file**, not just the body — a PII hit routes to `reports/.quarantine/` (gitignored) instead. This has been true since the repo's first commit on purpose (ADR-0003): a GitHub repo transfer carries full history, so the gate has to have been running for every commit that will ever be transferred.
- **`houston/pii_gate.py`** — regex gate for CPF, CNPJ, email, Brazilian phone, Luhn-validated card numbers. The Luhn check only runs unconditionally on 15/16-digit runs (common real card lengths); a bare 13/14/17-19-digit run needs card-like separator formatting to qualify — a bare 13-digit Unix epoch-millisecond timestamp (exactly what `observed.first_seen`/`last_seen` are) passes Luhn by chance about 1 in 10 times, and did, for real, on 22% of the first production run (ADR-0004). Known gap, not fixed by regex: a person's proper name. The mitigating practice is evidence as pointer+query, never pasted log text.
- **`houston/metrics.py`** — every number is read from `reports/*.md` front-matter, never typed by hand. `false_positive_rate` is `None`, not a divide-by-zero, until at least one report is `promoted` or `discarded`. `can_close_phase()` refuses while any report is `state: new`.
- **`scripts/generate_site.py`** — reads *only* structured front-matter fields into a static page (`site/`, gitignored, regenerated on demand) — never a report's body, which is exactly the free-text surface the PII gate's proper-name gap applies to (ADR-0005). `.github/workflows/pages.yml` builds and deploys it on push to `reports/**`, but enabling GitHub Pages itself is a deliberate, separate decision (private-repo Pages needs GitHub Enterprise Cloud; deferred until this repo transfers to the Medprev org).

## Naming

This repo is `medprev-poc-houston`, not `medprev-houston` — that name is already spoken for by `Medprev/medprev-product-backlog#242`/`#5483`, a different, unrelated system (an event-reaction service, not this one). See ADR-0002 before assuming the name can be reused.
