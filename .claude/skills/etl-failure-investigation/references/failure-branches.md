# Failure branches by operator

Classify each failed task by its operator, read in the DAG file on `origin/main`. The branch decides where
the error lives and what "the runtime" is in step 5.

## Controller — `TriggerDagRunOperator` + `watcher` (validado 2026-10-07)

- Pattern: tasks trigger child DAGs with `wait_for_completion=True` and `reset_dag_run=True`; a final
  `watcher` with `TriggerRule.ONE_FAILED` raises when any upstream task failed.
- The `watcher` failure and the controller task failures are **symptoms**. Go to each child DAG run
  (`trigger_run_id`, e.g. `<controller>_<run_id>_<suffix>`) and investigate the child.
- Trigger rules are often `ALL_DONE`, so siblings keep running after one fails: list which children passed.
  They are the discriminating evidence.
- Each child task fails after its own `retries`; the controller's `try_number` counts controller retries,
  not child retries.
- Reprocessing: Clear the controller run with "only failed tasks". `reset_dag_run=True` re-runs the
  same child run ids. Children whose upstream already succeeded may start in parallel.

## Kubernetes pod — `CustomKubernetesPodOperator` / `KubernetesPodOperator` (validado 2026-10-07)

- Runtime = the container image + `cmds` + `env_vars` from Airflow variables. Image references use Jinja
  variables (for example `local_medprev_analytics_etl_silver_tape_image`) and often the `:latest` tag.
- No `image_pull_policy` set → Kubernetes default `Always` for `:latest`: every pod pulls whatever `latest`
  points to at start. A merge that pushes a new `latest` changes the runtime of the next run with no deploy.
- Pods are deleted after finishing (`on_finish_action="delete_pod"`), so `kubectl get pod` is empty
  afterwards. The digest survives in Datadog (`image_id` tag on the pod's logs). Pull events stay in
  `kubectl get events` for about an hour.
- The job's own logging can end with `return 1` after catching the exception: the first error line is in
  the log, the exit code alone says nothing.
- Why-now order: digest change → `pip freeze` diff → package release date. Code commits on `silver-tape/`
  also rebuild the image, because the Dockerfile does `COPY . .` before `pip install`.

## Glue — `GlueJobOperator` (não validado)

- Runtime = Glue 5 (Python 3.11) + `script_location` on S3 + wheels in `--additional-python-modules`
  (`medprev_etl_utilities`, …), synced by the deploy workflow on every push to `main`.
- The Airflow task log shows the Glue `JobRunId` and final state. The error itself is in CloudWatch for
  that run (see [evidence-commands.md](evidence-commands.md#glue-jobs--não-validado)).
- Why-now candidates: script or wheel changed on S3 (commits on `glue/` reaching `main`), source schema or
  data changed, IAM/secret change, capacity/timeouts.
- Validate this branch on the first real Glue failure, then remove the "não validado" marks.

## Python task — `@task` / `PythonOperator`

- Runtime = the Airflow image (worker digest) + DAG code (git-sync). The error is in the task log itself.
- Compare the worker's digest(s) and the DAG `dag_versions` between last success and first failure.
