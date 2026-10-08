# ADR-0035: Airflow DAG failures are investigated by an interactive skill, outside the pipeline

**Status:** Accepted
**Date:** 2026-10-08
**Deciders:** Carla Cury (tracked in Medprev/medprev-product-backlog#6926, motivated by the
2026-10-07 sitemap incident, Medprev/medprev-product-backlog#6883)
**Decision style:** Scope decision — adds `.claude/skills/etl-failure-investigation/`; no change to
`houston/` code, the allowlist, or the report contract.
**Related:** [[0016-allowlist-allows-read-verbs-and-fails-closed]],
[[0001-model-access-via-claude-code-cli]], [[0003-pii-gate-from-first-commit]],
[[0008-kubernetes-fingerprint-at-namespace-granularity]]

## Context

On 2026-10-07, four sitemap DAGs of `medprev-analytics-etl` failed with
`ModuleNotFoundError: No module named 'psycopg'`. Houston saw none of it as a finding:

- The failure is not an Error Tracking issue or a monitor alert. It reaches people as an n8n Slack
  message, 8h30 after the first failed try.
- `medprev-analytics-etl-airflow` maps to `null` in `houston/service_repos.yaml`. The namespace's
  Kubernetes events are visible, but they carry no cause.

Proving the cause took eight sources. Only one of them is Datadog (the `image_id` tag on the job pods'
logs). The rest:

- the Slack thread;
- the Airflow REST API (runs, tries, task logs);
- the DAG and job code on `origin/main`;
- ECR (digest → tags, push time);
- `docker pull` + `pip freeze` diffed between the last good and the failing digest;
- PyPI release dates and the vendor's migration notes;
- `kubectl` for pull events and the digests running now.

The investigation agent (`houston/agent.py`) runs `claude -p` with Datadog read tools only and
`--disallowedTools Bash,Write,Edit` (ADR-0016). Giving it Bash, AWS or kube access to cover this case
would undo the property every report so far relies on: the model cannot write or execute anything.

## Decision

ETL failures are investigated by an **interactive skill**, `etl-failure-investigation`, run by a
person in a Claude Code session that has those tools. Houston's pipeline is unchanged.

The skill:

- **Is read-only until approved.** It probes access by capability (browser session on Airflow, AWS
  credentials, a kube context, Datadog and Slack MCPs, `gh`) and never assumes a user, account,
  profile or path. Posting to Slack, opening an issue or a PR each needs an explicit approval.
- **Answers "why now" by comparing the last success with the first failure.** It looks at the
  digest each pod ran (not the tag), the installed packages and the commits on the component. It
  then reproduces the error in the failing digest.
- **Writes its outputs in pt-BR, from one template.** The template covers the chat report, the
  thread reply and the incident issue in `Medprev/medprev-product-backlog`. The issue keeps the
  full timeline and evidence even when it passes the 50-line target.
- **Never pastes row content**, the same practice the PII gate's documented gaps rely on (ADR-0003).

`medprev-analytics-etl-airflow` stays `null` in `service_repos.yaml`: no automated `houston fix`
runs against the ETL repo until the investigation itself is measured.

## Consequences

### Good

- The 2026-10-07 trail is reusable by anyone with read access, not only by whoever ran it. The two
  process errors of that day are now explicit rules in the skill:
  - a cause first attributed to a PR whose diff did not touch the failing path;
  - an image comparison against the `:latest` tag instead of the digests that ran, which missed
    the Airflow deployment's second digest.
- No change to the agent's tool surface, the allowlist or the report contract. CI coverage is
  unaffected.

### Bad

- The skill's runs are not in `houston metrics`: there is no false-positive rate and no recorded
  spend for them.
- The skill depends on a logged-in browser for the Airflow API. The `kubectl exec` fallback is
  written down but not yet validated.
- The Glue branch is derived from the DAG code and has not been exercised on a real incident.

## Follow-up

Phase 2 — integrate with the report store (for example a `houston record` command that writes the
skill's report through `write_report` and the PII gate under an `af-{dag_id}-{run}` fingerprint, so
`promote`/`metrics` apply). Start it only after both of these hold:

1. the skill has been run on at least three real failures, including one Glue job;
2. the time-to-cause and the cost of those runs have been recorded on #6926.
