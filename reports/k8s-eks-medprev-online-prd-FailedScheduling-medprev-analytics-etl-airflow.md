---
fingerprint: k8s-eks-medprev-online-prd-FailedScheduling-medprev-analytics-etl-airflow
source: kubernetes
reason: FailedScheduling
novelty: new
service: medprev-analytics-etl-airflow
environment: production
window:
  from: 1788808256645
  to: 1789153856645
observed:
  count: 30
  first_seen: 1788924080000
  last_seen: 1789098426000
severity: medium
state: new
cost:
  input_tokens: 434645
  output_tokens: 9908
  cache_read_input_tokens: 350119
  cache_creation_input_tokens: 84516
  duration_s: 111.282
  usd: 0.5118908
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-analytics-etl-airflow%20FailedScheduling&from_ts=1788808256645&to_ts=1789153856645&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-analytics-etl-airflow%20FailedScheduling&from_ts=1788808256645&to_ts=1789153856645&live=false

## Causa raiz

O achado é de infraestrutura Kubernetes no cluster `eks-medprev-online-prd`, namespace `medprev-analytics-etl-airflow` (Airflow do pipeline de analytics/ETL) — não há repositório de aplicação associado (`target_repo: null`). O evento é **`FailedScheduling`**: o scheduler do Kubernetes não conseguiu alocar pods desse namespace por falta de capacidade nos nós. Consultei os eventos brutos (`search_datadog_events`, mesma `query` do achado) e confirmei que isso é **sinal, não ruído**: em nenhuma das 30 ocorrências existe alternativa de negócio tratada — é falha de infraestrutura real, recorrente desde 00:21:20 09/09/2026 BRT (epoch 1788924080000 · 2026-09-09T03:21:20.000Z) até 00:47:06 11/09/2026 BRT (epoch 1789098426000 · 2026-09-11T03:47:06.000Z). O padrão de mensagem é consistente em todas as ocorrências lidas: 7–9 nós sem CPU suficiente, 2–4 sem memória suficiente, 3–5 com taint não tolerado, sem vítimas de preempção — ou seja, o `karpenter_nodepool:default` está estruturalmente subdimensionado para os picos de demanda desse namespace, afetando três componentes distintos do Airflow (`main-api-server`, `main-worker-0`, `main-scheduler`), não um pod isolado.

Não há spans de APM para `service:medprev-analytics-etl-airflow` na janela (`aggregate_spans` retornou 0 buckets) — é um workload batch sem instrumentação de tracing, então a classificação `handled`/`unhandled` de span não se aplica aqui; a classificação sinal/ruído acima foi feita pelo próprio evento do Kubernetes. Não determinei uma causa raiz última para *por que* o nodepool ficou subdimensionado nesses horários específicos (ex.: se é concorrência com outro tenant do cluster ou pico previsível de carga do próprio ETL) — para isso seria necessário consultar métricas de capacidade/uso do nodepool, fora do escopo de eventos e logs que consultei. Consultas efetivamente rodadas e retorno de cada uma:
- `search_datadog_events` (query do achado, janela completa): 30 eventos, todos `FailedScheduling` afetando pods de `medprev-analytics-etl-airflow`.
- `aggregate_events` (mesma query, buckets de 3h): eventos concentrados em 6 janelas de 3h, não distribuídos uniformemente.
- `search_datadog_logs` (`status:(error OR warn)` no namespace): 2920 logs — dominados por entradas de outro serviço (`medprev-analytics-etl-silver-tape`) com `status:error` mas conteúdo `INFO` (rotulagem incorreta, não relacionado ao scheduling) e por uma falha recorrente de limpeza de log (`find: cannot delete '/opt/airflow/logs': Device or resource busy`, 762 ocorrências) e 22 ocorrências de `Terminated` no próprio `medprev-analytics-etl-airflow` — plausivelmente correlacionadas ao churn de pods/nós, mas não confirmei causalidade direta com o `FailedScheduling`.
- `aggregate_spans`: 0 spans para o serviço na janela — sem trace para aprofundar.

## Linha do tempo

- 00:21:20 09/09/2026 BRT (epoch 1788924080000 · 2026-09-09T03:21:20.000Z) — primeiro `FailedScheduling` do pod `medprev-analytics-etl-airflow-main-api-server-7c86748db9-m6qb6`: 0/11 nós disponíveis (3 sem memória, 4 com taint não tolerado, 7 sem CPU). [Events Explorer](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-analytics-etl-airflow%20FailedScheduling&from_ts=1788808256645&to_ts=1789153856645&live=false)
- 00:21:46 09/09/2026 BRT (epoch 1788924106000 · 2026-09-09T03:21:46.000Z) — mesmo pod, nova tentativa: 0/10 e depois 0/11 nós disponíveis, mesmo padrão de insuficiência.
- 00:24:56 09/09/2026 BRT (epoch 1788924296000 · 2026-09-09T03:24:56.000Z) — evento do kubelet no mesmo pod combina `FailedScheduling` (agora 0/12 nós) com `Unhealthy: Startup probe failed: connection refused` — indício de que, quando o pod finalmente sobe, ainda enfrenta instabilidade de inicialização.
- 03:43:58 09/09/2026 BRT (epoch 1788936238000 · 2026-09-09T06:43:58.000Z) a 03:44:31 09/09/2026 BRT (epoch 1788936271000 · 2026-09-09T06:44:31.000Z) — quatro novas tentativas de `FailedScheduling` para `medprev-analytics-etl-airflow-main-worker-0`, incluindo uma variante com `1 node(s) didn't match PersistentVolume's node affinity`.
- 07:01:12 09/09/2026 BRT (epoch 1788948072000 · 2026-09-09T10:01:12.000Z) a 07:01:37 09/09/2026 BRT (epoch 1788948097000 · 2026-09-09T10:01:37.000Z) — três tentativas para `medprev-analytics-etl-airflow-main-api-server-7c86748db9-q5bsc`.
- 01:35:04 10/09/2026 BRT (epoch 1789014904000 · 2026-09-10T04:35:04.000Z) a 01:35:30 10/09/2026 BRT (epoch 1789014930000 · 2026-09-10T04:35:30.000Z) — quatro tentativas para `main-worker-0`.
- 02:12:40 10/09/2026 BRT (epoch 1789017160000 · 2026-09-10T05:12:40.000Z) a 02:13:05 10/09/2026 BRT (epoch 1789017185000 · 2026-09-10T05:13:05.000Z) — três tentativas para `main-scheduler-58dc789475-mkcwr`.
- 21:25:47 10/09/2026 BRT (epoch 1789086347000 · 2026-09-11T00:25:47.000Z) a 21:26:47 10/09/2026 BRT (epoch 1789086407000 · 2026-09-11T00:26:47.000Z) — cinco tentativas para `main-worker-0` e `main-api-server-...-8tjpm`, incluindo nova falha de afinidade de PersistentVolume.
- 21:27:13 10/09/2026 BRT (epoch 1789086433000 · 2026-09-11T00:27:13.000Z) — última tentativa registrada nesse cluster de eventos, ainda com CPU/memória insuficientes.
- 00:45:35 11/09/2026 BRT (epoch 1789098335000 · 2026-09-11T03:45:35.000Z) a 00:46:00 11/09/2026 BRT (epoch 1789098360000 · 2026-09-11T03:46:00.000Z) — duas tentativas finais para `main-scheduler-58dc789475-s8jl6`, últimas do lote de 26 eventos retornados pela ferramenta (a busca indicou 30 no total; a `last_seen` do achado, 00:47:06 09/09/2026 BRT · 00:47:06 11/09/2026 BRT (epoch 1789098426000 · 2026-09-11T03:47:06.000Z), é minutos depois do último evento que li — os 4 eventos restantes não paginados provavelmente fecham esse mesmo padrão).
- Distribuição por bucket de 3h (`aggregate_events`): picos em 2026-09-09 03h/06h/09h UTC, 2026-09-10 03h UTC e 2026-09-11 00h/03h UTC — o problema se repete em horários semelhantes em dias consecutivos, não é um evento único.

## Evidência

- 30 ocorrências de `FailedScheduling` entre `window_from` (16:10:56 07/09/2026 BRT · 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z)) e `window_to` (16:10:56 11/09/2026 BRT · 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z)) — [Events Explorer](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-analytics-etl-airflow%20FailedScheduling&from_ts=1788808256645&to_ts=1789153856645&live=false), corresponde exatamente ao `observed_count` do achado.
- Três componentes distintos afetados (`main-api-server`, `main-worker-0`, `main-scheduler`), em pelo menos 6 pods/réplicas diferentes — mesma consulta acima, campo `pod_name`.
- Causa recorrente em texto do evento: insuficiência de CPU (7–9 nós) e memória (2–4 nós) e taints não tolerados (3–5 nós) no `karpenter_nodepool:default`, sem vítimas de preempção — mesma consulta.
- Evento correlacionado de `Unhealthy: Startup probe failed: connection refused` no mesmo pod (`main-api-server-...-m6qb6`) em 00:24:56 09/09/2026 BRT (epoch 1788924296000 · 2026-09-09T03:24:56.000Z) — mesma consulta, mesmo `event_id` do lote retornado.
- 0 spans de APM para `service:medprev-analytics-etl-airflow` na janela — consulta `aggregate_spans` (`query: service:medprev-analytics-etl-airflow`, `from/to` da janela do achado), sem link direto pois não há dado.
- 2920 logs com `status:(error OR warn)` no namespace na janela, mas dominados por ruído não relacionado (rotulagem incorreta em `medprev-analytics-etl-silver-tape`, 860+22+5+5+4 ocorrências, e falha de limpeza `find: cannot delete '/opt/airflow/logs'`, 762 ocorrências) — consulta `search_datadog_logs` com `use_log_patterns:true`, `pattern_group_by:["service"]`, mesma janela.
- 22 ocorrências do log `Terminated` em `medprev-analytics-etl-airflow` na janela — mesma consulta de patterns, possivelmente correlacionadas ao churn de pods, não confirmado como causal.

## Ação recomendada

Ação operacional de infraestrutura (sem repositório de código): aumentar a capacidade ou a prioridade de scale-up do `karpenter_nodepool:default` no cluster `eks-medprev-online-prd` — via limites de provisionamento do NodePool/Provisioner do Karpenter — para os horários em que o namespace `medprev-analytics-etl-airflow` concentra os picos (~00h–10h UTC), e revisar se os taints/tolerations dos pods do Airflow estão exigindo nós que raramente ficam disponíveis.

## Corpo da issue

### Descrição do incidente
O scheduler do Kubernetes não conseguiu alocar pods do Airflow (`main-api-server`, `main-worker-0`, `main-scheduler`) no namespace `medprev-analytics-etl-airflow`, cluster `eks-medprev-online-prd`, ambiente `production`, repetidamente entre 2026-09-09 e 2026-09-11. O impacto observável é atraso na disponibilidade desses componentes do Airflow — potencialmente atrasando execuções de DAGs do pipeline de analytics/ETL — e, em pelo menos um caso, instabilidade adicional na inicialização do pod (`Startup probe failed: connection refused`) após o agendamento eventualmente ocorrer.

### Causa raiz
Sinal real, não ruído: 30 eventos `FailedScheduling` consultados diretamente no Kubernetes Events, todos com o mesmo padrão de insuficiência de recursos, não uma exceção de negócio tratada. A causa imediata é falta de capacidade (CPU/memória) e taints não tolerados no `karpenter_nodepool:default` nos horários dos picos. A causa raiz de fundo — por que o nodepool fica subdimensionado repetidamente nesses horários específicos — não foi determinada com as ferramentas de eventos/logs consultadas; requer análise de métricas de utilização/escala do nodepool.

### Linha do tempo
- 00:21:20 09/09/2026 BRT (epoch 1788924080000 · 2026-09-09T03:21:20.000Z)–00:24:56 09/09/2026 BRT (epoch 1788924296000 · 2026-09-09T03:24:56.000Z): primeira sequência de `FailedScheduling` em `main-api-server-...-m6qb6`, culminando em `Unhealthy: Startup probe failed: connection refused` no mesmo pod.
- 03:43:58 09/09/2026 BRT (epoch 1788936238000 · 2026-09-09T06:43:58.000Z)–03:44:31 09/09/2026 BRT (epoch 1788936271000 · 2026-09-09T06:44:31.000Z): sequência em `main-worker-0`, incluindo falha de afinidade de PersistentVolume.
- 07:01:12 09/09/2026 BRT (epoch 1788948072000 · 2026-09-09T10:01:12.000Z)–07:01:37 09/09/2026 BRT (epoch 1788948097000 · 2026-09-09T10:01:37.000Z): sequência em `main-api-server-...-q5bsc`.
- 01:35:04 10/09/2026 BRT (epoch 1789014904000 · 2026-09-10T04:35:04.000Z)–01:35:30 10/09/2026 BRT (epoch 1789014930000 · 2026-09-10T04:35:30.000Z): sequência em `main-worker-0`.
- 02:12:40 10/09/2026 BRT (epoch 1789017160000 · 2026-09-10T05:12:40.000Z)–02:13:05 10/09/2026 BRT (epoch 1789017185000 · 2026-09-10T05:13:05.000Z): sequência em `main-scheduler-...-mkcwr`.
- 21:25:47 10/09/2026 BRT (epoch 1789086347000 · 2026-09-11T00:25:47.000Z)–21:27:13 10/09/2026 BRT (epoch 1789086433000 · 2026-09-11T00:27:13.000Z): sequência em `main-worker-0` e `main-api-server-...-8tjpm`, com nova falha de afinidade de PersistentVolume.
- 00:45:35 11/09/2026 BRT (epoch 1789098335000 · 2026-09-11T03:45:35.000Z)–00:46:00 11/09/2026 BRT (epoch 1789098360000 · 2026-09-11T03:46:00.000Z): sequência final em `main-scheduler-...-s8jl6`.
- Padrão temporal: eventos concentrados em janelas de 3h em 2026-09-09 (03h/06h/09h UTC), 2026-09-10 (03h UTC) e 2026-09-11 (00h/03h UTC) — recorrência diária, não incidente isolado.
- Correlação não confirmada: 22 ocorrências do log `Terminated` em `medprev-analytics-etl-airflow` sobrepostas à mesma janela.

### Evidências
- [Events Explorer — FailedScheduling no namespace, janela fixada](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-analytics-etl-airflow%20FailedScheduling&from_ts=1788808256645&to_ts=1789153856645&live=false) — 30 eventos.
- Consulta `aggregate_spans` (`service:medprev-analytics-etl-airflow`, mesma janela) — 0 spans, sem link (produto sem dado).
- Consulta `search_datadog_logs` (`kube_namespace:medprev-analytics-etl-airflow status:(error OR warn)`, `use_log_patterns:true`, mesma janela) — 2920 logs, padrão dominante não relacionado ao scheduling.

### Ação recomendada
Infra — sem repositório de código, ação operacional: ajustar o provisionamento do Karpenter (`NodePool`/`Provisioner` do `karpenter_nodepool:default`) no cluster `eks-medprev-online-prd`, aumentando limites de CPU/memória disponíveis ou a agressividade de scale-up nos horários de pico (00h–10h UTC), e revisar as tolerations dos pods do Airflow (`main-api-server`, `main-worker-0`, `main-scheduler`) frente aos taints atuais dos nós. Validar consultando novamente a mesma query de eventos (`FailedScheduling` no namespace) em uma janela equivalente após a mudança e confirmando queda para próximo de zero ocorrências.

### Volume
30 ocorrências entre 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) e 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z) — confirmado por consulta direta ao Datadog Events (mesmo total, mesma janela).

### Severidade e criticidade
`severity` do achado: `medium`. Avaliação de criticidade (inferência): impacto potencial em atraso de execuções do pipeline de analytics/ETL, sem indicação nas evidências consultadas de perda de dados ou indisponibilidade total do serviço — recorrência diária em múltiplos componentes do Airflow sugere risco crescente se a demanda do namespace continuar subindo sem ajuste de capacidade do nodepool.
