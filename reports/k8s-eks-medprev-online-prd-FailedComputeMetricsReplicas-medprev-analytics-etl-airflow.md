---
fingerprint: k8s-eks-medprev-online-prd-FailedComputeMetricsReplicas-medprev-analytics-etl-airflow
source: kubernetes
reason: FailedComputeMetricsReplicas
novelty: new
service: medprev-analytics-etl-airflow
environment: production
window:
  from: 1788808256645
  to: 1789153856645
observed:
  count: 7
  first_seen: 1789085870000
  last_seen: 1789085960000
severity: medium
state: new
cost:
  input_tokens: 409364
  output_tokens: 8446
  cache_read_input_tokens: 320913
  cache_creation_input_tokens: 88441
  duration_s: 87.063
  usd: 0.5071886000000001
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-analytics-etl-airflow%20FailedComputeMetricsReplicas&from_ts=1788808256645&to_ts=1789153856645&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-analytics-etl-airflow%20FailedComputeMetricsReplicas&from_ts=1788808256645&to_ts=1789153856645&live=false

## Causa raiz

O HPA (`horizontal-pod-autoscaler`) do Deployment `medprev-analytics-etl-airflow-main-worker`, no namespace `medprev-analytics-etl-airflow` do cluster `eks-medprev-online-prd`, não consegue calcular métricas de CPU/memória para decidir o número de réplicas, porque o container `worker-log-groomer` do Pod `medprev-analytics-etl-airflow-main-worker-0` não declara `resources.requests` de CPU nem de memória. Sem `requests`, o Metrics Server não tem base percentual para calcular utilização, e o HPA falha (`FailedGetResourceMetric` → `FailedComputeMetricsReplicas`, "invalid metrics (2 invalid out of 2)").

Isso é **sinal**, não ruído: é uma falha de configuração real e persistente que impede o autoscaling do worker — não um erro de negócio tratado. Não há classificação `handled`/`unhandled` porque este achado não é um erro de aplicação (Error Tracking/span), é um evento de controle do Kubernetes; a divisão sinal/ruído aqui vem de outra evidência — consultei o Events Explorer com uma janela mais ampla (mesmo intervalo `from`/`to` do achado) e o mesmo Reason apareceu **1143 vezes**, com a mensagem do próprio HPA registrando "_seen at 2026-09-07 19:11:59 +0000 UTC since 2026-09-05 03:01:50 +0000 UTC_" — ou seja, a condição já existe desde pelo menos 00:01:50 05/09/2026 BRT (epoch 1788577310000 · 2026-09-05T03:01:50.000Z) e se repete continuamente a cada poucos minutos, não é um pico isolado.

Consultei também logs de aplicação (`search_datadog_logs`, filtro `kube_namespace:medprev-analytics-etl-airflow kube_deployment:medprev-analytics-etl-airflow-main-worker`, mesma janela do achado) e spans APM (`search_datadog_spans`, `service:medprev-analytics-etl-airflow env:production`, mesma janela): ambas retornaram **0 registros**. Isso é esperado — este componente não expõe HTTP/traces nem logs indexados sob esse nome de serviço — e confirma que o problema é de configuração de infraestrutura (K8s), não uma falha de código de aplicação com sintoma em log/trace.

## Linha do tempo

1. 00:01:50 05/09/2026 BRT (epoch 1788577310000 · 2026-09-05T03:01:50.000Z) — primeira ocorrência conhecida da condição subjacente (falta de `requests` de CPU/memória no container `worker-log-groomer`), conforme texto do próprio evento do HPA ("since 2026-09-05 03:01:50 +0000 UTC").
2. 16:11:59 07/09/2026 BRT (epoch 1788808319000 · 2026-09-07T19:11:59.000Z) até 18:41:56 07/09/2026 BRT (epoch 1788817316000 · 2026-09-07T21:41:56.000Z) — repetição contínua do evento `FailedGetResourceMetric` a cada ~5 minutos, dentro da janela de coleta (`window_from`: 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) até `window_to`: 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z)) — consulta: `source:kubernetes kube_namespace:medprev-analytics-etl-airflow kube_name:medprev-analytics-etl-airflow-main-worker` (1143 eventos retornados na janela, paginação truncada).
3. 21:17:50 10/09/2026 BRT (epoch 1789085870000 · 2026-09-11T00:17:50.000Z) — 1ª das 7 ocorrências específicas de `FailedComputeMetricsReplicas` deduplicadas pelo Houston (`first_seen`: 21:17:50 10/09/2026 BRT (epoch 1789085870000 · 2026-09-11T00:17:50.000Z)).
4. 21:18:05 10/09/2026 BRT (epoch 1789085885000 · 2026-09-11T00:18:05.000Z), 21:18:20 10/09/2026 BRT (epoch 1789085900000 · 2026-09-11T00:18:20.000Z), 21:18:35 10/09/2026 BRT (epoch 1789085915000 · 2026-09-11T00:18:35.000Z), 21:18:50 10/09/2026 BRT (epoch 1789085930000 · 2026-09-11T00:18:50.000Z), 21:19:05 10/09/2026 BRT (epoch 1789085945000 · 2026-09-11T00:19:05.000Z) — 2ª a 6ª ocorrências, todas com a mesma mensagem ("invalid metrics (2 invalid out of 2)... missing request for cpu/memory in container worker-log-groomer").
5. 21:19:20 10/09/2026 BRT (epoch 1789085960000 · 2026-09-11T00:19:20.000Z) — 7ª e última ocorrência dentro da janela (`last_seen`: 21:19:20 10/09/2026 BRT (epoch 1789085960000 · 2026-09-11T00:19:20.000Z)).

Não há evento de deploy/versão correlacionado nos resultados retornados — a busca de eventos por `kube_name` não trouxe nenhum `source:change_tracking` nem mudança de manifesto no período consultado; a causa é uma configuração já existente, não uma regressão recente de deploy.

## Evidência

- 1143 ocorrências de eventos do HPA para o Deployment `medprev-analytics-etl-airflow-main-worker` na janela `window_from`–`window_to` acima, das quais 7 correspondem ao Reason específico `FailedComputeMetricsReplicas` que gerou este achado — [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-analytics-etl-airflow%20FailedComputeMetricsReplicas&from_ts=1788808256645&to_ts=1789153856645&live=false).
- A mensagem do próprio evento do HPA declara a causa estrutural: container `worker-log-groomer` sem `requests` de CPU nem memória no Pod `medprev-analytics-etl-airflow-main-worker-0` — mesma consulta acima.
- A condição já existia desde 00:01:50 05/09/2026 BRT (epoch 1788577310000 · 2026-09-05T03:01:50.000Z), medido via `search_datadog_events` com query `source:kubernetes kube_namespace:medprev-analytics-etl-airflow kube_name:medprev-analytics-etl-airflow-main-worker`, janela igual à do achado: 1143 eventos retornados (paginação truncada em 31 exibidos).
- Logs de aplicação do namespace/deployment na mesma janela: `search_datadog_logs` com `kube_namespace:medprev-analytics-etl-airflow kube_deployment:medprev-analytics-etl-airflow-main-worker` → 0 registros.
- Spans APM do serviço na mesma janela: `search_datadog_spans` com `service:medprev-analytics-etl-airflow env:production` → 0 spans.

## Ação recomendada

Adicionar `resources.requests` (CPU e memória) ao container `worker-log-groomer` no manifesto/values do Deployment `medprev-analytics-etl-airflow-main-worker` (namespace `medprev-analytics-etl-airflow`, cluster `eks-medprev-online-prd`), e confirmar que o HPA volta a computar métricas sem erro.

## Corpo da issue

### Descrição do incidente
O HPA do Deployment `medprev-analytics-etl-airflow-main-worker` (namespace `medprev-analytics-etl-airflow`, cluster `eks-medprev-online-prd`, ambiente `production`) não consegue calcular métricas de CPU/memória para decidir escala, porque o container `worker-log-groomer` do Pod `medprev-analytics-etl-airflow-main-worker-0` não declara `resources.requests` de CPU nem de memória. Impacto observável: o autoscaling horizontal do worker Airflow está efetivamente inoperante — o HPA não tem base para escalar réplicas por CPU/memória enquanto essa condição persistir.

### Causa raiz
Sinal (não ruído) — evento de infraestrutura contínuo, não um erro de negócio tratado; medido via 1143 ocorrências do mesmo Reason na janela do achado. Causa confirmada pela própria mensagem do evento do HPA: falta de `resources.requests` (CPU e memória) no container `worker-log-groomer` do Pod `medprev-analytics-etl-airflow-main-worker-0`, presente desde pelo menos 00:01:50 05/09/2026 BRT (epoch 1788577310000 · 2026-09-05T03:01:50.000Z).

### Linha do tempo
1. 00:01:50 05/09/2026 BRT (epoch 1788577310000 · 2026-09-05T03:01:50.000Z) — primeira ocorrência conhecida da condição, conforme texto do evento do HPA.
2. 16:11:59 07/09/2026 BRT (epoch 1788808319000 · 2026-09-07T19:11:59.000Z)–18:41:56 07/09/2026 BRT (epoch 1788817316000 · 2026-09-07T21:41:56.000Z) — repetição a cada ~5 minutos, dentro da janela de coleta do achado (1143 eventos totais na busca ampla por deployment/namespace).
3. 21:17:50 10/09/2026 BRT (epoch 1789085870000 · 2026-09-11T00:17:50.000Z) a 21:19:20 10/09/2026 BRT (epoch 1789085960000 · 2026-09-11T00:19:20.000Z) — as 7 ocorrências específicas de `FailedComputeMetricsReplicas` deduplicadas pelo Houston, em rajada de ~90s (a cada 15s).
4. Nenhum evento de deploy/mudança de versão correlacionado foi encontrado nas consultas rodadas.

### Evidências
- [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-analytics-etl-airflow%20FailedComputeMetricsReplicas&from_ts=1788808256645&to_ts=1789153856645&live=false)
- Consulta `source:kubernetes kube_namespace:medprev-analytics-etl-airflow kube_name:medprev-analytics-etl-airflow-main-worker`, mesma janela → 1143 eventos, confirmando persistência desde 00:01:50 05/09/2026 BRT (epoch 1788577310000 · 2026-09-05T03:01:50.000Z).
- Consulta `search_datadog_logs` `kube_namespace:medprev-analytics-etl-airflow kube_deployment:medprev-analytics-etl-airflow-main-worker`, mesma janela → 0 registros.
- Consulta `search_datadog_spans` `service:medprev-analytics-etl-airflow env:production`, mesma janela → 0 spans.

### Ação recomendada
Repositório: não determinado (`target_repo` nulo) — infra, sem repositório de código associado neste achado; ação operacional no manifesto/Helm chart/Kustomize que define o Deployment `medprev-analytics-etl-airflow-main-worker` no cluster `eks-medprev-online-prd`. Adicionar `resources.requests.cpu` e `resources.requests.memory` ao container `worker-log-groomer` (dimensionar pelo uso real observado do sidecar, não um valor arbitrário). Validar rodando `kubectl describe hpa medprev-analytics-etl-airflow-main-worker -n medprev-analytics-etl-airflow` e confirmando ausência de `FailedGetResourceMetric`/`FailedComputeMetricsReplicas` nos eventos subsequentes, e no Events Explorer do link acima, por pelo menos um ciclo completo de scale (~15 min) sem novas ocorrências.

### Volume
7 ocorrências entre 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) e 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z) — contagem do achado (`observed_count`). Consulta direta ao Datadog na mesma janela, mas sem filtro de Reason específico (namespace + deployment), retornou 1143 eventos — divergência explicada por escopo mais amplo (todos os Reasons do HPA, não só `FailedComputeMetricsReplicas`) e pela dedup por namespace do Houston (ADR-0008).

### Severidade e criticidade
`severity` do achado: medium. Criticidade para o negócio: inferência — como o HPA está impedido de calcular métricas para todo o Pod (não só o sidecar), o worker Airflow do pipeline analytics-etl não escala por CPU/memória sob carga, o que pode degradar o throughput de processamento de ETL em picos de volume sem gerar alerta visível de erro de aplicação (por não haver logs/spans associados). Recomenda-se tratar como prioridade operacional, não apenas informativa.
