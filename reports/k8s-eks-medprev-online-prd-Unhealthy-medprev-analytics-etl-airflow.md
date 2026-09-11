---
fingerprint: k8s-eks-medprev-online-prd-Unhealthy-medprev-analytics-etl-airflow
source: kubernetes
reason: Unhealthy
novelty: new
service: medprev-analytics-etl-airflow
environment: production
window:
  from: 1788794372355
  to: 1789139972355
observed:
  count: 240
  first_seen: 1788795640000
  last_seen: 1789137711000
severity: medium
state: promoted
cost:
  input_tokens: 557870
  output_tokens: 10624
  cache_read_input_tokens: 463377
  cache_creation_input_tokens: 94481
  duration_s: 115.91
  usd: 0.5815494
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: https://github.com/Medprev/medprev-product-backlog/issues/6436
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-analytics-etl-airflow%20Unhealthy&from_ts=1788794372355&to_ts=1789139972355&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-analytics-etl-airflow%20Unhealthy&from_ts=1788794372355&to_ts=1789139972355&live=false

## Causa raiz

O achado é do namespace **medprev-analytics-etl-airflow** (cluster `eks-medprev-online-prd`), afetando múltiplos componentes do Airflow: scheduler (7 réplicas), triggerer, dag-processor (2 réplicas), worker e api-server (7 réplicas) — 20 pods distintos no total, não um pod isolado. É **SINAL**, não ruído: os logs de aplicação confirmam atrasos reais de heartbeat ("Heartbeat recovered after 45.64 seconds" e "after 55.30 seconds", `airflow.jobs.job.Job`) coincidindo com os primeiros eventos Unhealthy da janela, e o próprio último evento da janela (`11:41:51 11/09/2026 BRT (epoch 1789137711000 · 2026-09-11T14:41:51.000Z)`) mostra o probe de liveness **piorando**: em vez de "No alive jobs found", o comando de verificação (`airflow jobs check --job-type SchedulerJob --local`) **expirou após 20s** — o processo de check em si está sendo sufocado, não apenas encontrando o job "morto".

Correlacionado na mesma janela, mas fora do escopo direto deste achado (mesmo serviço, `status:error`): 737 ocorrências de `find: cannot delete '/opt/airflow/logs': Device or resource busy`, distribuídas ao longo de toda a janela (consulta `service:medprev-analytics-etl-airflow env:production status:(warn OR error)`, agrupada por padrão). Isso aponta para contenção no volume de logs compartilhado (provável EFS/NFS) como hipótese mais provável para os atrasos de heartbeat em múltiplos pods simultaneamente — mas essa causalidade específica (I/O do volume de logs → heartbeat perdido) **não foi confirmada por métrica de infraestrutura** (IOPS/latência do volume); é inferência a partir da correlação temporal e do padrão "mesmo erro, mesmos pods, mesma janela", não uma causa comprovada por telemetria de armazenamento.

Consultas executadas e o que cada uma devolveu:
- `search_datadog_events` (query do achado, janela completa): 241 eventos — próximo de `observed_count: 240`, divergência de 1 evento explicável por a consulta ter sido rodada depois da coleta do achado (janela idêntica, mas o feed de eventos pode ter recebido mais um registro entre a coleta e a consulta).
- `aggregate_events` por `kube_name`: 20 pods distintos, sem concentração isolada — o mais afetado (`triggerer-0`) responde por 49/240 (~20%), o resto pulverizado.
- `search_datadog_logs` (warn/error, use_log_patterns): 33 padrões, dominados pelo erro de `Device or resource busy` acima.
- `search_datadog_logs` ("heartbeat"/"no alive jobs"/SchedulerJob) na janela do primeiro evento: 2 logs, ambos "Heartbeat recovered".
- `get_change_stories` (deployment/kubernetes/crashloopbackoff/scale, mesma janela): 0 stories — não há deploy, mudança de manifesto k8s ou scale registrada que explique o início do problema.

## Linha do tempo

- 12:40:40 07/09/2026 BRT (epoch 1788795640000 · 2026-09-07T15:40:40.000Z) — primeiro evento Unhealthy da janela: liveness probe falha com "No alive jobs found" no pod `medprev-analytics-etl-airflow-main-scheduler-58dc789475-2q4tc` (evento #15 desde `2026-09-07 05:40:40 UTC`). Consulta: `query` de `evidence_links`.
- 12:41:15 07/09/2026 BRT (epoch 1788795675000 · 2026-09-07T15:41:15.000Z) / 12:42:01 07/09/2026 BRT (epoch 1788795721000 · 2026-09-07T15:42:01.000Z) — logs de aplicação no mesmo host (`i-0ca83cdf9028ce616`) registram `Heartbeat recovered after 55.30 seconds` e `after 45.64 seconds` (`airflow.jobs.job.Job`) — confirma que o probe está detectando um atraso real de heartbeat, não um falso positivo.
- 12:40:40 07/09/2026 BRT (epoch 1788795640000 · 2026-09-07T15:40:40.000Z) a 07:10:36 08/09/2026 BRT (epoch 1788862236000 · 2026-09-08T10:10:36.000Z) — mesma falha "No alive jobs found" se repete em outros pods do mesmo namespace: `triggerer-0`, `dag-processor-56668c4f5c5tcg`, outro `scheduler-...-748ml` (inclusive como startup probe às 01:07:12 08/09/2026 BRT (epoch 1788840432000 · 2026-09-08T04:07:12.000Z)).
- 07:05:11 08/09/2026 BRT (epoch 1788861911000 · 2026-09-08T10:05:11.000Z) a 07:06:21 08/09/2026 BRT (epoch 1788861981000 · 2026-09-08T10:06:21.000Z) — variante distinta no `api-server-7c86748db9-vhx6z`: startup probe falha com `connection refused` em `10.0.9.48:8080` (6 ocorrências em ~70s) — padrão consistente com container ainda subindo, não com o problema de heartbeat.
- 01:06:41 08/09/2026 BRT (epoch 1788840401000 · 2026-09-08T04:06:41.000Z) em diante — começa a aparecer em paralelo, e persiste até o fim da janela, o erro `find: cannot delete '/opt/airflow/logs': Device or resource busy` (737 ocorrências, distribuídas em rajadas ao longo de todos os dias da janela).
- 11:40:38 11/09/2026 BRT (epoch 1789137638000 · 2026-09-11T14:40:38.000Z) / 11:40:36 11/09/2026 BRT (epoch 1789137636000 · 2026-09-11T14:40:36.000Z) — mais duas falhas "No alive jobs found" em `scheduler-...-5fldv` e `triggerer-0`.
- 11:41:51 11/09/2026 BRT (epoch 1789137711000 · 2026-09-11T14:41:51.000Z) — último evento da janela (bate com `last_seen`): no mesmo pod `scheduler-...-5fldv`, o probe muda de padrão — o próprio comando de verificação (`airflow jobs check --job-type SchedulerJob --local`) **expira em 20s**, não apenas retorna "sem job vivo". É o sinal mais forte de que a contenção (provavelmente de I/O) está piorando, não estabilizando.
- Nenhum evento de deploy, mudança de manifesto Kubernetes ou scale foi encontrado nessa janela (`get_change_stories`, 0 resultados) — descarta uma regressão de deploy como gatilho.

## Evidência

- 241 eventos Unhealthy na janela `12:19:32 07/09/2026 BRT (epoch 1788794372355 · 2026-09-07T15:19:32.355Z)` a `12:19:32 11/09/2026 BRT (epoch 1789139972355 · 2026-09-11T15:19:32.355Z)`, vs. `observed_count: 240` do achado (mesma janela) — [Events Explorer](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-analytics-etl-airflow%20Unhealthy&from_ts=1788794372355&to_ts=1789139972355&live=false).
- Distribuição por pod (`aggregate_events`, group_by `kube_name`, mesma janela): 20 pods distintos afetados, liderados por `triggerer-0` (49), sete réplicas de `scheduler` (8–19 cada) e sete réplicas de `api-server` (4–7 cada) — consulta: `source:kubernetes env:production status:warn kube_namespace:medprev-analytics-etl-airflow Unhealthy`, `group_by: kube_name`.
- Logs de aplicação confirmando heartbeat real atrasado: consulta `service:medprev-analytics-etl-airflow env:production (heartbeat OR "no alive jobs" OR SchedulerJob OR "monitor/health")` na janela `12:16:40 07/09/2026 BRT (epoch 1788794200000 · 2026-09-07T15:16:40.000Z)`–`13:23:20 07/09/2026 BRT (epoch 1788798200000 · 2026-09-07T16:23:20.000Z)` → 2 logs, ambos `Heartbeat recovered after N seconds`.
- Padrão de erro correlacionado (`search_datadog_logs`, `use_log_patterns:true`, `service:medprev-analytics-etl-airflow env:production status:(warn OR error)`, mesma janela): 33 padrões distintos, com `find: cannot delete '/opt/airflow/logs': Device or resource busy` somando 737 ocorrências ao longo de toda a janela — sem `pod_name` atribuído no agrupamento (campo vazio no facet).
- Ausência de deploy/alteração de infraestrutura correlacionada: `get_change_stories` para `medprev-analytics-etl-airflow` entre `12:19:32 07/09/2026 BRT (epoch 1788794372000 · 2026-09-07T15:19:32.000Z)` e `12:19:32 11/09/2026 BRT (epoch 1789139972000 · 2026-09-11T15:19:32.000Z)`, tipos `deployment/kubernetes/crashloopbackoff/scale` → 0 resultados.

## Ação recomendada

Investigar a saúde do volume de logs compartilhado do Airflow (provável EFS/NFS montado em `/opt/airflow/logs`) neste namespace — métricas de IOPS/latência/erros de montagem no período — já que o erro `Device or resource busy` e os atrasos de heartbeat ocorrem na mesma janela e nos mesmos pods; se confirmado, tratar como contenção de I/O (aumentar throughput/IOPS provisionado ou revisar o cronjob de limpeza de logs que está batendo no `find: cannot delete`).

## Corpo da issue

### Descrição do incidente
No namespace `medprev-analytics-etl-airflow` do cluster `eks-medprev-online-prd`, pods de scheduler, triggerer, dag-processor, worker e api-server do Airflow vêm falhando repetidamente nos probes de liveness/startup do Kubernetes desde `12:40:40 07/09/2026 BRT (epoch 1788795640000 · 2026-09-07T15:40:40.000Z)` até `11:41:51 11/09/2026 BRT (epoch 1789137711000 · 2026-09-11T14:41:51.000Z)` (fim da janela de coleta), com a mensagem "Liveness probe failed: No alive jobs found" e, no evento mais recente, com o próprio comando de verificação do probe expirando após 20s. Impacto observável: reinícios/instabilidade de 20 pods diferentes do Airflow ao longo de ~4 dias, incluindo o scheduler (responsável por agendar DAGs) e o triggerer — risco direto de atraso ou falha na execução de pipelines de ETL/analytics.

### Causa raiz
SINAL, não ruído: logs de aplicação confirmam atrasos reais de heartbeat (45–55s) coincidindo com os primeiros eventos, e o último evento da janela mostra o probe piorando (timeout no próprio comando de check, não apenas "sem job vivo"). Causa raiz definitiva **não determinada** — a hipótese mais provável, por correlação temporal e não por métrica direta de infraestrutura, é contenção de I/O no volume compartilhado de logs: 737 ocorrências do erro `find: cannot delete '/opt/airflow/logs': Device or resource busy` ocorrem na mesma janela, nos mesmos dias, no mesmo serviço.

### Linha do tempo
- `12:40:40 07/09/2026 BRT (epoch 1788795640000 · 2026-09-07T15:40:40.000Z)` — primeiro Unhealthy: liveness probe falha ("No alive jobs found") no scheduler `...-2q4tc`.
- `12:41:15 07/09/2026 BRT (epoch 1788795675000 · 2026-09-07T15:41:15.000Z)` / `12:42:01 07/09/2026 BRT (epoch 1788795721000 · 2026-09-07T15:42:01.000Z)` — logs confirmam `Heartbeat recovered after 55.30s` / `45.64s` no mesmo host.
- `12:40:40 07/09/2026 BRT (epoch 1788795640000 · 2026-09-07T15:40:40.000Z)`–`07:10:36 08/09/2026 BRT (epoch 1788862236000 · 2026-09-08T10:10:36.000Z)` — mesma falha se repete em triggerer, dag-processor e outro scheduler.
- `07:05:11 08/09/2026 BRT (epoch 1788861911000 · 2026-09-08T10:05:11.000Z)`–`07:06:21 08/09/2026 BRT (epoch 1788861981000 · 2026-09-08T10:06:21.000Z)` — variante isolada: startup probe do api-server `...-vhx6z` falha com `connection refused` (padrão típico de container ainda inicializando, não relacionado ao heartbeat).
- `01:06:41 08/09/2026 BRT (epoch 1788840401000 · 2026-09-08T04:06:41.000Z)` em diante — erro paralelo `Device or resource busy` ao deletar `/opt/airflow/logs`, recorrente todos os dias até o fim da janela (737 ocorrências).
- `11:40:36 11/09/2026 BRT (epoch 1789137636000 · 2026-09-11T14:40:36.000Z)`/`11:40:38 11/09/2026 BRT (epoch 1789137638000 · 2026-09-11T14:40:38.000Z)` — mais duas falhas "No alive jobs found".
- `11:41:51 11/09/2026 BRT (epoch 1789137711000 · 2026-09-11T14:41:51.000Z)` — último evento da janela: o comando do probe (`airflow jobs check --job-type SchedulerJob --local`) expira após 20s no scheduler `...-5fldv` — sinal de piora, não de estabilização.
- Nenhum deploy, mudança de manifesto k8s ou scale foi registrado nessa janela (`get_change_stories`, 0 resultados) — descarta regressão por deploy.

### Evidências
- [Events Explorer — Unhealthy no namespace, janela fixada](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-analytics-etl-airflow%20Unhealthy&from_ts=1788794372355&to_ts=1789139972355&live=false)
- Consulta `search_datadog_logs`: `service:medprev-analytics-etl-airflow env:production (heartbeat OR "no alive jobs" OR SchedulerJob OR "monitor/health")` → 2 logs de heartbeat recuperado.
- Consulta `search_datadog_logs` (log patterns): `service:medprev-analytics-etl-airflow env:production status:(warn OR error)` agrupado por `pod_name` → 33 padrões, líder `Device or resource busy` com 737 ocorrências.
- Consulta `aggregate_events` agrupada por `kube_name`, mesma query/janela do achado → 20 pods distintos afetados.
- Consulta `get_change_stories` (`deployment`, `kubernetes`, `crashloopbackoff`, `scale`) para `medprev-analytics-etl-airflow` na janela → 0 resultados.

### Ação recomendada
`target_repo`: nulo — infra, sem repositório de código, ação operacional. Investigar as métricas de I/O (IOPS, latência, erros) do volume de armazenamento de logs do Airflow (provável EFS/NFS montado em `/opt/airflow/logs`) neste namespace durante a janela `12:19:32 07/09/2026 BRT (epoch 1788794372000 · 2026-09-07T15:19:32.000Z)`–`12:19:32 11/09/2026 BRT (epoch 1789139972000 · 2026-09-11T15:19:32.000Z)`; se houver saturação, aumentar throughput/IOPS provisionado ou revisar/corrigir o cronjob de limpeza de logs que gera o erro `Device or resource busy` (provavelmente concorrendo com processos que ainda têm handles abertos no diretório). Validar a correção observando se as falhas de liveness/startup probe (`Unhealthy` com "No alive jobs found" ou timeout do comando de check) e o erro de `Device or resource busy` cessam nas próximas 72h.

### Volume
`observed_count: 240` ocorrências entre `12:19:32 07/09/2026 BRT (epoch 1788794372355 · 2026-09-07T15:19:32.355Z)` e `12:19:32 11/09/2026 BRT (epoch 1789139972355 · 2026-09-11T15:19:32.355Z)`. Consulta direta ao Datadog na mesma janela retornou 241 (diferença de 1, provavelmente por a consulta ter rodado após a coleta do achado).

### Severidade e criticidade
`severity: medium` do achado. Criticidade avaliada (inferência): alta — o scheduler e o triggerer são componentes centrais do Airflow; instabilidade recorrente neles, distribuída por 20 pods e piorando ao final da janela (timeout do próprio probe), representa risco real de atraso/falha na execução de DAGs de ETL/analytics, não apenas ruído de configuração de probe.
