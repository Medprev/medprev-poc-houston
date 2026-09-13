---
fingerprint: k8s-eks-medprev-online-prd-FailedAttachVolume-medprev-analytics-etl-airflow
source: kubernetes
reason: FailedAttachVolume
novelty: new
service: medprev-analytics-etl-airflow
environment: production
window:
  from: 1788808256645
  to: 1789153856645
observed:
  count: 6
  first_seen: 1788924038000
  last_seen: 1789028732000
severity: medium
state: new
cost:
  input_tokens: 387452
  output_tokens: 8772
  cache_read_input_tokens: 320076
  cache_creation_input_tokens: 67366
  duration_s: 96.11
  usd: 0.42593320000000007
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-analytics-etl-airflow%20FailedAttachVolume&from_ts=1788808256645&to_ts=1789153856645&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-analytics-etl-airflow%20FailedAttachVolume&from_ts=1788808256645&to_ts=1789153856645&live=false

## Causa raiz

O achado é de infraestrutura Kubernetes (não Error Tracking) — cluster `eks-medprev-online-prd`, namespace `medprev-analytics-etl-airflow`, evento `FailedAttachVolume` do controller `attachdetach-controller`. A janela de coleta é `16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z)` até `16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z)`.

Como não é um achado de Error Tracking, a classificação `handled`/`unhandled` de spans não se aplica ao evento em si — confirmei isso rodando `aggregate_spans` para `service:medprev-analytics-etl-airflow status:error` na mesma janela e obtendo **0 buckets** (nenhum span de APM para esse serviço; `search_datadog_logs` também mostra que os logs são de execução batch do Airflow, não requisições HTTP instrumentadas). Este é um SINAL real, não ruído: os 6 eventos consultados via `search_datadog_events` são todos erros genuínos "Multi-Attach error" — dois PVCs (`pvc-820763f5-...` preso ao pod `medprev-analytics-etl-airflow-main-worker-0`, `pvc-ca67c7ea-...` preso ao pod `medprev-analytics-etl-airflow-main-redis-0`) tentando ser anexados a 6 nós EC2 diferentes ao longo da janela, todos sob `karpenter_nodepool:default`. Isso é o padrão clássico de EBS RWO (ReadWriteOnce) tentando reanexar num nó novo antes do nó antigo liberar o volume — típico de StatefulSet + rotação de nós pelo Karpenter (consolidação/spot/scale-down).

Correlacionado, mas causalmente separado: `search_datadog_logs` com `status:error` no mesmo serviço/janela devolveu **784 ocorrências**, e as 3 amostradas são todas a mesma mensagem `find: cannot delete '/opt/airflow/logs': Device or resource busy`, no host `i-024b74bba467087b4` — um host que não aparece em nenhum dos 6 eventos de `FailedAttachVolume`. Não consigo confirmar uma relação causal direta entre os dois; registro como um defeito real e separado encontrado durante a investigação, não como causa do `FailedAttachVolume`.

Consultas executadas e retorno de cada uma:
- `search_datadog_events` com a query do achado, janela completa → 6 eventos (bate com `observed_count`).
- `search_datadog_logs` `service:medprev-analytics-etl-airflow env:production`, mesma janela → 595.521 logs totais, amostra sem menção a volume/attach.
- `search_datadog_logs` `service:medprev-analytics-etl-airflow env:production status:error`, mesma janela → 784 logs, todos com a mensagem de `/opt/airflow/logs` busy nos 3 lidos.
- `aggregate_spans` `service:medprev-analytics-etl-airflow status:error`, mesma janela, agrupado por `@error.handling`/`@http.status_code` → 0 buckets (sem instrumentação APM neste serviço).
- `aggregate_events` agrupando eventos `warn` do namespace por `title` → 0 buckets (título tem cardinalidade alta por pod, não é um facet agregável; resultado vazio registrado, sem repetir a mesma pergunta).

## Linha do tempo

- 00:20:38 09/09/2026 BRT (epoch 1788924038000 · 2026-09-09T03:20:38.000Z) — `FailedAttachVolume`: Multi-Attach error para `pvc-820763f5-7a7c-4536-a3e3-e34e453ab769`, pod `medprev-analytics-etl-airflow-main-worker-0`, nó `i-04cbfccbdd30b4c5f`. [Events Explorer](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-analytics-etl-airflow%20FailedAttachVolume&from_ts=1788808256645&to_ts=1789153856645&live=false)
- 00:35:57 09/09/2026 BRT (epoch 1788924957000 · 2026-09-09T03:35:57.000Z) — `FailedAttachVolume`: Multi-Attach error para `pvc-ca67c7ea-6125-4b39-a740-25b7641da504`, pod `medprev-analytics-etl-airflow-main-redis-0`, nó `i-0b9dbb308fa1415ef`. Mesma query acima.
- 07:55:18 09/09/2026 BRT (epoch 1788951318000 · 2026-09-09T10:55:18.000Z) — Mesmo PVC `pvc-ca67c7ea-...`, mesmo pod `main-redis-0`, agora tentando anexar no nó `i-02e1959def1d7a347`. Mesma query.
- 01:36:06 10/09/2026 BRT (epoch 1789014966000 · 2026-09-10T04:36:06.000Z) — Mesmo PVC `pvc-ca67c7ea-...`, mesmo pod `main-redis-0`, nó `i-0d182364507ab45c3`. Mesma query.
- 02:13:50 10/09/2026 BRT (epoch 1789017230000 · 2026-09-10T05:13:50.000Z) — PVC `pvc-820763f5-...` volta a falhar, pod `main-worker-0`, nó `i-0f06661635d0938bb`. Mesma query.
- 05:25:32 10/09/2026 BRT (epoch 1789028732000 · 2026-09-10T08:25:32.000Z) — Última ocorrência da janela: PVC `pvc-ca67c7ea-...`, pod `main-redis-0`, nó `i-07aa79ff3b225aa0a`. Mesma query. Este é o `last_seen` do achado (`05:25:32 10/09/2026 BRT (epoch 1789028732000 · 2026-09-10T08:25:32.000Z)`).

Correlação separada, mesma janela: log de erro recorrente `find: cannot delete '/opt/airflow/logs': Device or resource busy` no host `i-024b74bba467087b4`, amostrado em 16:00:01 11/09/2026 BRT (epoch 1789153201000 · 2026-09-11T19:00:01.000Z), 16:00:00 11/09/2026 BRT (epoch 1789153200000 · 2026-09-11T19:00:00.000Z) e 15:45:01 11/09/2026 BRT (epoch 1789152301000 · 2026-09-11T18:45:01.000Z) — 784 ocorrências totais na janela via `search_datadog_logs status:error`, host distinto dos 6 eventos acima.

## Evidência

- 6 eventos `FailedAttachVolume` na janela, dois PVCs (`pvc-820763f5-...` → `main-worker-0`; `pvc-ca67c7ea-...` → `main-redis-0`), 6 nós EC2 distintos — [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-analytics-etl-airflow%20FailedAttachVolume&from_ts=1788808256645&to_ts=1789153856645&live=false).
- Sem spans de APM para este serviço na janela (0 buckets) — consulta: `aggregate_spans`, `service:medprev-analytics-etl-airflow status:error`, `1788808256645`–`1789153856645`.
- 595.521 logs de aplicação no total da janela — consulta: `search_datadog_logs`, `service:medprev-analytics-etl-airflow env:production`, mesma janela.
- 784 logs de nível `error` na janela, todos amostrados como falha de limpeza de `/opt/airflow/logs` por "Device or resource busy", em host distinto dos eventos de `FailedAttachVolume` — consulta: `search_datadog_logs`, `service:medprev-analytics-etl-airflow env:production status:error`, mesma janela.
- Agregação de eventos `warn` do namespace por `title` retornou vazia (0 buckets) — consulta: `aggregate_events`, `source:kubernetes env:production kube_namespace:medprev-analytics-etl-airflow status:warn`, mesma janela.

## Ação recomendada

Infra (`target_repo: null`): revisar a política de disruption/consolidation do Karpenter para o nodepool `default` em relação aos StatefulSets `medprev-analytics-etl-airflow-main-worker` e `medprev-analytics-etl-airflow-main-redis` (PDB e/ou anotação `karpenter.sh/do-not-disrupt` durante uso ativo do volume), para evitar reagendamento antes do detach do EBS.

## Corpo da issue

### Descrição do incidente
No namespace `medprev-analytics-etl-airflow` do cluster `eks-medprev-online-prd`, os pods StatefulSet `medprev-analytics-etl-airflow-main-worker-0` e `medprev-analytics-etl-airflow-main-redis-0` falharam repetidamente ao montar seus volumes EBS (RWO) após serem reagendados para um novo nó, com erro `Multi-Attach` do `attachdetach-controller`. Impacto observável: atraso na inicialização desses pods (o pod fica pendente até o volume antigo ser liberado), afetando potencialmente a execução de tasks do Airflow e a disponibilidade do Redis interno do ETL.

### Causa raiz
SINAL, não ruído — 6/6 ocorrências são erros reais de infraestrutura (sem instrumentação APM neste serviço para medir handled/unhandled; 0 spans de erro encontrados). Causa mais provável, não 100% confirmada pelas evidências disponíveis (sem acesso a logs do Karpenter/scheduler): rotação de nós pelo Karpenter movendo pods StatefulSet com volume EBS RWO para um novo nó antes do detach do nó anterior completar. Encontrado adicionalmente, e não relacionado ao `FailedAttachVolume`: 784 logs de erro na mesma janela com `find: cannot delete '/opt/airflow/logs': Device or resource busy`, em host diferente dos 6 eventos.

### Linha do tempo
- 00:20:38 09/09/2026 BRT (epoch 1788924038000 · 2026-09-09T03:20:38.000Z) — `pvc-820763f5-...` falha em `main-worker-0`, nó `i-04cbfccbdd30b4c5f`.
- 00:35:57 09/09/2026 BRT (epoch 1788924957000 · 2026-09-09T03:35:57.000Z) — `pvc-ca67c7ea-...` falha em `main-redis-0`, nó `i-0b9dbb308fa1415ef`.
- 07:55:18 09/09/2026 BRT (epoch 1788951318000 · 2026-09-09T10:55:18.000Z) — mesmo PVC/pod, novo nó `i-02e1959def1d7a347`.
- 01:36:06 10/09/2026 BRT (epoch 1789014966000 · 2026-09-10T04:36:06.000Z) — mesmo PVC/pod, novo nó `i-0d182364507ab45c3`.
- 02:13:50 10/09/2026 BRT (epoch 1789017230000 · 2026-09-10T05:13:50.000Z) — `pvc-820763f5-...` falha novamente em `main-worker-0`, nó `i-0f06661635d0938bb`.
- 05:25:32 10/09/2026 BRT (epoch 1789028732000 · 2026-09-10T08:25:32.000Z) — última ocorrência: `pvc-ca67c7ea-...` em `main-redis-0`, nó `i-07aa79ff3b225aa0a`.
- Sem correlação direta confirmada com o log de erro de `/opt/airflow/logs` (host distinto, mesmo intervalo amplo).

### Evidências
- [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-analytics-etl-airflow%20FailedAttachVolume&from_ts=1788808256645&to_ts=1789153856645&live=false) — 6 eventos.
- Query: `aggregate_spans` `service:medprev-analytics-etl-airflow status:error` — 0 spans na janela.
- Query: `search_datadog_logs` `service:medprev-analytics-etl-airflow env:production status:error` — 784 logs na janela.

### Ação recomendada
Infra — sem repositório de código, ação operacional. Componente: nodepool `default` do Karpenter em `eks-medprev-online-prd` e configuração dos StatefulSets `medprev-analytics-etl-airflow-main-worker` / `medprev-analytics-etl-airflow-main-redis`. Mudança: adicionar `PodDisruptionBudget` e/ou anotação `karpenter.sh/do-not-disrupt: "true"` a esses pods (ou mover para `terminationGracePeriodSeconds` maior e ajustar `consolidationPolicy` do nodepool para não expulsar pods com volume EBS anexado). Validação: após aplicar, monitorar a mesma query (`FailedAttachVolume` no namespace) por 7 dias e confirmar contagem zero.

### Volume
`observed_count`: 6, medido na janela `window_from` (`16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z)`) a `window_to` (`16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z)`). Consulta própria ao Datadog na mesma janela confirmou o mesmo total: 6.

### Severidade e criticidade
`severity` do achado: `medium`. Criticidade de negócio (inferência): moderada — o erro é auto-recuperável pelo Kubernetes (retry de attach), mas atrasa a inicialização de tasks do Airflow e do Redis interno do ETL, podendo adiar pipelines de analytics. O defeito separado encontrado (784 logs de erro de limpeza de `/opt/airflow/logs`, "Device or resource busy") não teve sua criticidade avaliada nesta investigação — merece triagem própria, pois pode indicar falha recorrente de rotina de limpeza no host `i-024b74bba467087b4`.
