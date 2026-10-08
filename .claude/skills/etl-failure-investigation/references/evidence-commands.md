# Evidence commands

Every command here was run against production during the 2026-10-07 sitemap incident unless marked
**não validado**. Each one says which question it answers. Placeholders:

- `$AIRFLOW` — Airflow UI origin (default `https://airflow.medprev.app`).
- `$ETL` — local clone of `medprev-analytics-etl`, fetched.
- `$ECR_REGISTRY`, `$AWS_REGION` — read from `$ETL/.env.defaults.yaml`.
- `$NS` — `medprev-analytics-etl-airflow` (Airflow and its job pods).
- AWS and kube commands use whatever credentials/context the operator has; add `--profile` / `--context`
  only with the value the operator gave.

Quote image references as `"${REPO}:${TAG}"` or `"${REPO}@${DIGEST}"` — in zsh `$REPO:latest` is the `:l`
modifier and silently produces a wrong name.

## 0. Probes

| Question | Command |
|---|---|
| Airflow API reachable from the browser tab? | `(await fetch('/api/v2/dags?limit=1')).status` → `200` |
| Which AWS identity? | `aws sts get-caller-identity --query Arn --output text` |
| ECR readable? | `aws ecr describe-repositories --region "$AWS_REGION" --repository-names medprev-analytics-etl-silver-tape medprev-analytics-etl-airflow --query 'repositories[].repositoryName'` |
| Which kube context is production? | `kubectl config get-contexts` → pick the one whose cluster is the production EKS, then `kubectl --context <ctx> get pods -n "$NS"` |
| GitHub org reachable? | `gh api orgs/Medprev --jq .login` |
| Code current? | `git -C "$ETL" fetch -q origin && git -C "$ETL" log -1 --format='%h %ad' origin/main` |

## 2. Airflow

Run in the browser tab on `$AIRFLOW` (the session cookie authenticates `fetch`). Keep each call short: the
tool times out near 45 s.

```js
const j = async u => { const r = await fetch('/api/v2' + u); const t = await r.text();
  if (!r.ok || t[0] !== '{') throw new Error(r.status + ' ' + t.slice(0, 150)); return JSON.parse(t); };
// Last runs of one DAG: first failure vs last success, and whether the DAG version changed
(await j('/dags/<dag_id>/dagRuns?order_by=-logical_date&limit=8')).dag_runs
  .map(r => [r.dag_run_id, r.state, r.start_date, r.end_date, r.dag_versions.map(v => v.version_number + '@' + v.created_at).join()]);
```

```js
// Task instances of one run, with tries
const rid = encodeURIComponent('<dag_run_id>');
(await j(`/dags/<dag_id>/dagRuns/${rid}/taskInstances`)).task_instances
  .map(t => [t.task_id, t.state, 'try' + t.try_number, t.start_date, t.end_date].join(' | ')).join('\n');
```

```js
// First error of one try (filter, do not dump the whole log)
const o = JSON.parse(await (await fetch(`/api/v2/dags/<dag_id>/dagRuns/${rid}/taskInstances/<task_id>/logs/<try>?full_content=true`,
  { headers: { Accept: 'application/json' } })).text());
(Array.isArray(o.content) ? o.content : [o.content]).map(e => typeof e === 'string' ? e : (e.event || ''))
  .filter(l => /error|exception|traceback|not found/i.test(l)).slice(0, 8).join('\n');
```

```js
// Every failed run across DAGs in a window
(await j('/dags/~/dagRuns?state=failed&start_date_gte=<iso>&limit=100')).dag_runs.map(x => x.dag_id + ' ' + x.start_date);
// Paused state and schedule of a DAG on the blast-radius list
const d = await j('/dags/<dag_id>'); [d.is_paused, d.timetable_summary];
```

Controller child runs follow `trigger_run_id`; for the sitemap controller it is
`<controller_dag_id>_<controller_run_id>_<suffix>`.

Fallback without a browser session — **não validado**: `kubectl -n "$NS" exec deploy/<api-server> --
airflow dags list-runs <dag_id> -o json`. Validate before relying on it, and prefer the API.

## 4. Code at origin/main

```bash
git -C "$ETL" grep -n 'dag_id="<dag_id>"' origin/main -- airflow/dags          # DAG file
git -C "$ETL" show origin/main:<dag_file>                                       # operator, image, cmds
git -C "$ETL" grep -n -E '<symbol>' origin/main -- silver-tape/src glue         # follow the stack
```

## 5. Why now

**Commits on the component between the two runs** (first-parent = what reached `main`):

```bash
git -C "$ETL" log origin/main --first-parent --since=<last_success_iso> --until=<first_failure_iso> \
  --format='%h %ad %an %s' --date=iso -- silver-tape <dag_file>
git -C "$ETL" diff --stat <sha>^1 <sha> -- silver-tape                           # what a merge changed there
```

**Digest each pod actually ran** (Datadog `analyze_datadog_logs`):

- filter: `service:medprev-analytics-etl-silver-tape` (or `kube_namespace:$NS`)
- extra columns: `pod_name` varchar, `image_id` varchar
- SQL: `SELECT pod_name, image_id, min(timestamp) AS first_log, count(*) AS n FROM logs GROUP BY pod_name, image_id ORDER BY min(timestamp)`

Use a window covering the last success *and* the first failure. Pod logs carry `status:error` for stderr;
read messages, not status.

**Digests running now in the Airflow deployment** (more than one is normal):

```bash
kubectl -n "$NS" get pods -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{range .status.containerStatuses[*]}{.name}={.imageID}{" "}{end}{"\n"}{end}'
kubectl -n "$NS" get events --sort-by=.lastTimestamp | grep -E 'Pulling|Pulled'   # did the pod pull? (no digest here)
```

**Digest → tags, push time, build time**:

```bash
aws ecr describe-images --region "$AWS_REGION" --repository-name <repo> \
  --image-ids imageDigest=<sha256:...> --query 'imageDetails[0].[imagePushedAt,imageTags]'
aws ecr describe-images --region "$AWS_REGION" --repository-name <repo> --image-ids imageTag=latest \
  --query 'imageDetails[0].[imagePushedAt,imageDigest]' --output text
docker image inspect "${REPO}@${DIGEST}" --format '{{.Created}}'   # built long before pushed = cached layers
```

**Installed packages, failing vs last good digest**:

```bash
aws ecr get-login-password --region "$AWS_REGION" | docker login -u AWS --password-stdin "$ECR_REGISTRY"
for D in <good_digest> <bad_digest>; do
  docker pull -q "${REPO}@${D}" >/dev/null
  docker run --rm --entrypoint pip "${REPO}@${D}" freeze | sort > "$SCRATCH/freeze-${D#sha256:}.txt"
done
diff "$SCRATCH"/freeze-<good>.txt "$SCRATCH"/freeze-<bad>.txt
# Airflow image: docker run --rm --user airflow --entrypoint python "${REPO}@${D}" -m pip freeze
```

**When did the suspect version ship** (PyPI JSON):

```bash
curl -s https://pypi.org/pypi/<package>/json | python3 -c "import json,sys;d=json.load(sys.stdin)
print(*sorted(((f[0]['upload_time'],v) for v,f in d['releases'].items() if f),reverse=True)[:6],sep='\n')"
```

Then read the vendor's changelog / migration guide and quote the line that matches the error.

## 6. Reproduce

Smallest call that hits the failing path, no network or database. 2026-10-07 example:

```bash
docker run --rm --entrypoint python "${REPO}@${BAD}"  -c 'from sqlalchemy import create_engine; create_engine("postgresql://u:p@h:5432/d")'
# → ModuleNotFoundError: No module named 'psycopg'
docker run --rm --entrypoint python "${REPO}@${GOOD}" -c 'from sqlalchemy import create_engine; print(create_engine("postgresql://u:p@h:5432/d").dialect.driver)'
# → psycopg2
```

## 7. Blast radius

```bash
git -C "$ETL" grep -ln -E '<shared_class_or_module>' origin/main -- silver-tape/src glue   # same code path
git -C "$ETL" grep -n -E 'schedule=' origin/main -- <dag_file>                             # when it runs
```

Paused state comes from the Airflow API (`/dags/<dag_id>` → `is_paused`).

## Glue jobs — não validado

Derived from `GlueJobOperator(job_name=...)` in the DAGs; not yet exercised on a real incident:

```bash
aws glue get-job-runs --region <glue_region> --job-name <job_name> --max-items 5 \
  --query 'JobRuns[].[Id,JobRunState,StartedOn,CompletedOn,ErrorMessage]'
```

Logs live in CloudWatch under the job's log group (`/aws-glue/jobs/error`, `/aws-glue/jobs/output`, or the
continuous-logging group). Confirm the region and group on the first real case and update this section.
