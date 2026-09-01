# medprev-poc-houston

PoC: investiga sinais do Datadog (Error Tracking, Monitors, Kubernetes events) e produz
laudo versionado com evidência reconferível. Um `claude -p` por achado, sem acesso de
escrita ao disco — todo laudo passa pelo gate de PII antes de chegar em `reports/`.

## Setup

```
cp .env.example .env
# preencher DD_API_KEY e DD_APP_KEY (escopo de leitura) e DD_SITE
```

## Origin

Derived from the Vigília architecture document, "Versão mínima" tab.


## Tasks

Task runner: [mise](https://mise.jdx.dev). `mise run <task>`, or see `mise tasks` for the full list.

| Task | What it does | Costs money? |
|---|---|---|
| `mise run setup` | Install dependencies into the project venv | No |
| `mise run lint` | `ruff check .` | No |
| `mise run test [pattern]` | Run the test suite | No |
| `mise run run` | Collect + dedup + cap, print what would be investigated | No |
| `mise run seed` | Record pre-existing findings as `state: seeded` | No |
| `mise run investigate` | Run the real agent on capped new findings | **Yes** — ~$0.24-0.40/finding |
| `mise run promote <fingerprint>` | Print (never run) a ready `gh issue create` | No |
| `mise run metrics` | FP rate, cost percentiles, phase-close readiness | No |
