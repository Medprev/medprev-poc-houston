---
name: etl-failure-investigation
description: >-
  Investigates a failed Airflow DAG run of medprev-analytics-etl end to end and proves why it failed now:
  reads the alert, the Airflow runs, task tries and logs, maps the DAG to its code on origin/main, compares
  the runtime of the last success against the first failure (image digest the pod actually ran, installed
  packages, commits on the component), reproduces the error in the failing image, measures blast radius,
  then drafts the Slack thread reply and an incident issue for the user to approve. Read-only until the
  user approves each write. Use it whenever someone shares the n8n alert "Foram encontrados erros de
  execução para as seguintes DAGS", an airflow.medprev.app link, a dag_id, or asks why a DAG/ETL/sitemap/
  Glue/silver-tape job failed, "investigar a falha da DAG", "por que a ETL quebrou". For a Datadog Error
  Tracking issue use error-tracking-investigation; for a support ticket use trilha.
---

# ETL failure investigation

You are reconstructing, with primary-source proof, why an Airflow DAG of `medprev-analytics-etl` failed
**and why it failed now**, and drafting what the team needs to act. The reader makes irreversible calls
from your report, so every claim carries its source and every gap is declared.

Everything the user reads is in **Brazilian Portuguese**. This file is the method.

## Ground rules

- **Read-only until approved.** No Clear, trigger, pause, or variable change in Airflow; no Slack post; no
  issue, branch, or PR without an explicit "sim" for *that* action. One action per approval.
- **Capability, not identity.** Never assume a person, GitHub account, AWS profile, kube context or local
  path. Probe each access (step 0), use whatever the operator has, and when one is missing, say which access
  is missing, skip only what depends on it, and list it under "não verificado".
- **Digest, not tag.** `:latest` (or any mutable tag) proves nothing about what ran. The image a pod ran is
  the `image_id` digest recorded for that pod.
- **Trigger ≠ root cause.** The trigger is what changed the runtime (a merge, a rebuild, a new release);
  the root cause is why that change could break it (an unpinned dependency, a missing driver). Never blame a
  PR whose diff does not touch the failing path without explaining the mechanism that connects them.
- **No PII in anything you draft.** ETL logs can carry patient/partner data. Evidence is a pointer + query
  (run id, pod name, Datadog query, digest), never pasted row content; counts, not records (LGPD, same rule
  as this repo's PII gate, ADR-0003).
- **Kill the competing hypothesis.** Explain why sibling DAGs/tasks that share the controller *passed*. That
  contrast is usually the strongest evidence.

## Step 0 — Probe access

Run each probe; report a one-line table (acesso → ok / falta + como obter). Commands are in
[references/evidence-commands.md](references/evidence-commands.md#0-probes).

| Access | Needed for | Probe |
|---|---|---|
| Browser session on the Airflow UI (default `https://airflow.medprev.app`, ask if different) | runs, tries, logs | `fetch('/api/v2/dags?limit=1')` in that tab returns 200 |
| AWS credentials (any profile/SSO/env the operator uses) | ECR digests, image pull | `aws sts get-caller-identity`; `aws ecr describe-repositories` on the ETL repos. If it fails, ask which profile to use |
| kube context for the production cluster running Airflow | pull events, running digests | find it in `kubectl config get-contexts`, confirm with `kubectl get pods -n medprev-analytics-etl-airflow` |
| Datadog MCP | pod `image_id`, logs across time | one `search_datadog_logs` on the namespace |
| Slack MCP | read alert thread | `slack_read_thread` |
| `gh` authenticated with access to the `Medprev` org | code, PRs, issue search | `gh api orgs/Medprev --jq .login` |
| Local clone of `medprev-analytics-etl` | code at `origin/main` | ask for the path or find it; `git fetch` |

Registry and region come from `ECR_REGISTRY` / `AWS_REGION` in that clone's `.env.defaults.yaml`, never
hard-coded.

## Step 1 — Read the alert

From the thread: the DAG display names, the alert time, and any human replies. Record the lag between the
first failure (step 2) and the alert — it belongs in the timeline.

## Step 2 — Airflow: what failed, and since when

For every DAG named (snippets in [evidence-commands.md](references/evidence-commands.md#2-airflow)):

1. Last runs, newest first: find the **first failed** run and the **last successful** one.
2. Task instances of the failed run with `try_number`, start and end.
3. `dag_versions[].created_at` of both runs: did the DAG itself change between them?
4. Classify each DAG with [references/failure-branches.md](references/failure-branches.md): controller
   (`TriggerDagRunOperator` + `watcher`) → descend to the child DAG runs; leaf → step 3.
5. Other failed runs in the same window across all DAGs (`~/dagRuns?state=failed`): same cause or unrelated?

## Step 3 — First error per try

Fetch each failed try's log and keep the **first** error line (exception type + message), not the last
retry noise. Group DAGs by identical error — one group, one hypothesis. Note which sibling tasks succeeded
and what they do differently (another data source, another code path).

## Step 4 — Map to code at `origin/main`

`git fetch`, then read from `origin/main` (a local `main` can be months behind). Locate the DAG file by
`dag_id`, the operator, the image and tag, the `cmds`/script it runs, and the component path
(`silver-tape/`, `glue/`, `airflow/`). Follow the stack to the line that raises.

## Step 5 — Why now

Compare the runtime of the **last success** with the **first failure**, in this order, stopping when one
explains the error:

1. **Code**: `git log --first-parent origin/main` on the component and the DAG file between the two runs.
2. **Image**: the digest each pod ran (Datadog `image_id` per `pod_name`), then for each digest its ECR tags,
   `imagePushedAt` and the image `Created` date. A digest built long before it was pushed means cached
   layers; the first push that *rebuilt* the layer is the trigger.
3. **Packages**: `pip freeze` diff between the two digests. For the suspect package, its release date on
   PyPI and the vendor's own changelog / migration notes — quote the line that matches the error.
4. **Config/infra** (variables, secrets, cluster events) only if 1–3 explain nothing; mark as checked.

## Step 6 — Prove it

Reproduce the smallest form of the error inside the failing digest and show it absent in the last good
digest — an import or constructor call, no network and no database (example in
[evidence-commands.md](references/evidence-commands.md#6-reproduce)). Without a reproduction, the cause is
"provável", not proven, and the report says so.

## Step 7 — Blast radius

- Other jobs on the same code path (grep on `origin/main`), with their DAG schedule and paused state — a
  paused DAG is a latent failure, say so.
- Data impact: which partitions/outputs were not written. If not checked, it goes to "não verificado".

## Step 8 — Deliver, then ask

Write the chat report with [references/report-template.md](references/report-template.md#relatório-no-chat):
verdict first, timeline (BRT, one source per row), cause (trigger vs root), proof, solution (imediata /
seguinte / estrutural, with tradeoffs), risks and "não verificado".

Then ask, **one at a time**, and wait for each answer:
1. Postar a resposta na thread? (show the draft from the template)
2. Abrir a issue de incidente no `Medprev/medprev-product-backlog`? (show the draft)
3. Preparar o PR da correção imediata?

## Step 9 — Only after each approval

- **Thread reply**: in the alert thread, no broadcast. The Slack MCP cannot edit — get the text right first;
  corrections go as a new reply that says what changed.
- **Issue**: search duplicates first (`gh issue list --search`), show the active `gh` account and confirm,
  then create with the incident template. Timeline and evidence are complete even if the body passes 50
  lines; trim prose elsewhere instead.
- **PR**: worktree from `origin/main`, follow `create-pr` (Problema / Mudança / Impacto / Risco, pt-BR),
  validate by building the image and diffing `pip freeze` against the digest that runs in production.
- **After merge**: confirm the new digest in ECR and its `pip freeze`; guide the Clear of the failed run in
  the UI (Clear Run → only failed tasks) or, with permission, do it via API; poll the run; confirm the new
  pods' `image_id` in Datadog. Comment each milestone on the issue.

## Pitfalls (each one happened)

- zsh expands `$R:latest` as the `:l` modifier and mangles the image name. Always `"${R}:latest"`.
- `pip` as root fails in the Airflow image: `docker run --user airflow --entrypoint python <img> -m pip freeze`.
- Browser JS calls time out at ~45 s: one request or a ≤35 s wait per call, never a long polling loop.
- The Airflow deployment runs **two** image digests across components (api-server/scheduler vs
  worker/triggerer/dag-processor) — compare every digest that runs, not one.
- `silver-tape` pod logs reach Datadog as `status:error` (stderr): status is not a signal; read the message.
- The alert reaches Slack hours after the failure; the incident starts at the first failed try.
- A PR title or author is not evidence; the diff and the mechanism are.
