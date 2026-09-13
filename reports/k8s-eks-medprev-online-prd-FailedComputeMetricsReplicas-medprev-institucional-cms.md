---
fingerprint: k8s-eks-medprev-online-prd-FailedComputeMetricsReplicas-medprev-institucional-cms
source: kubernetes
reason: FailedComputeMetricsReplicas
novelty: new
service: medprev-institucional-cms
environment: production
window:
  from: 1788808256645
  to: 1789153856645
observed:
  count: 14
  first_seen: 1788924182000
  last_seen: 1789086442000
severity: medium
state: new
cost:
  input_tokens: 521501
  output_tokens: 10959
  cache_read_input_tokens: 428930
  cache_creation_input_tokens: 92559
  duration_s: 120.381
  usd: 0.5703779999999999
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-institucional-cms%20FailedComputeMetricsReplicas&from_ts=1788808256645&to_ts=1789153856645&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-institucional-cms%20FailedComputeMetricsReplicas&from_ts=1788808256645&to_ts=1789153856645&live=false

## Causa raiz

O evento é **ruído no sentido de não ser um bug do serviço `medprev-institucional-cms`**, mas sinaliza um problema real de infraestrutura do cluster: nenhuma ocorrência tem relação com o código da aplicação. As 14 ocorrências entre **16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z)** e **16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z)** são todas emitidas pelo `HorizontalPodAutoscaler` do namespace, com `status:warn` (14/14 — não há uma variante "error" desse Reason), reportando falha ao consultar `pods.metrics.k8s.io` ("the server is currently unable to handle the request" / "no metrics returned from resource metrics API"). Não há span nem log de erro do serviço correlacionados: `service:medprev-institucional-cms` não tem nenhum span de APM na janela (0 registros, instrumentação ausente ou sem tráfego capturado) e a única linha de log `status:error` no período é um `npm error` de log de build, sem relação temporal ou de conteúdo com o Reason investigado — não foi tratado como evidência do incidente.

O que a investigação mostra é que o `FailedComputeMetricsReplicas` **não é isolado a este namespace**: no mesmo intervalo, o mesmo Reason ocorreu em 8 namespaces (`medprev-rest-api`: 75, `medprev-face-liveness-app`: 46, `medprev-web-app`: 32, `medprev-cms`: 17, `medprev-institucional-cms`: 14, `medprev-metabase`: 14, `nginx-gateway-fabric`: 14, `medprev-analytics-etl-airflow`: 7) — 219 eventos no total, todos atribuíveis ao mesmo componente cluster-wide: o `metrics-server` em `kube-system`. Os eventos desse pod (`kube-system/metrics-server-*`) mostram um padrão recorrente de `Killing` → `SuccessfulCreate`/`Nominated` (Karpenter realocando o pod para um novo node) → `Pulling`/`Pulled`/`Started` → `Unhealthy: Readiness probe failed (connection refused :10250)`, e cada um desses ciclos de recriação coincide, no minuto, com uma rajada de `FailedComputeMetricsReplicas` em múltiplos namespaces (ex.: kill às 00:22:50 09/09/2026 BRT (epoch 1788924170000 · 2026-09-09T03:22:50.000Z) → evento às 00:23:02 09/09/2026 BRT (epoch 1788924182000 · 2026-09-09T03:23:02.000Z); kill/recreate entre 03:44:48 09/09/2026 BRT (epoch 1788936288000 · 2026-09-09T06:44:48.000Z) e 03:45:28 09/09/2026 BRT (epoch 1788936328000 · 2026-09-09T06:45:28.000Z) → eventos às 03:45:29 09/09/2026 BRT (epoch 1788936329000 · 2026-09-09T06:45:29.000Z) e 03:45:44 09/09/2026 BRT (epoch 1788936344000 · 2026-09-09T06:45:44.000Z); ciclo entre 07:35:41 09/09/2026 BRT (epoch 1788950141000 · 2026-09-09T10:35:41.000Z) e 07:54:40 09/09/2026 BRT (epoch 1788951280000 · 2026-09-09T10:54:40.000Z) → eventos às 07:35:53 09/09/2026 BRT (epoch 1788950153000 · 2026-09-09T10:35:53.000Z), 07:36:08 09/09/2026 BRT (epoch 1788950168000 · 2026-09-09T10:36:08.000Z), 07:54:40 09/09/2026 BRT (epoch 1788951280000 · 2026-09-09T10:54:40.000Z), 07:54:55 09/09/2026 BRT (epoch 1788951295000 · 2026-09-09T10:54:55.000Z); kill/recreate entre 21:26:45 10/09/2026 BRT (epoch 1789086405000 · 2026-09-11T00:26:45.000Z) e 21:27:06 10/09/2026 BRT (epoch 1789086426000 · 2026-09-11T00:27:06.000Z) → eventos às 21:27:07 10/09/2026 BRT (epoch 1789086427000 · 2026-09-11T00:27:07.000Z) e 21:27:22 10/09/2026 BRT (epoch 1789086442000 · 2026-09-11T00:27:22.000Z)). A causa provável (inferência, não prova de código-fonte) é que o `metrics-server` está sujeito a churn de nodes do Karpenter (nodepool `default`) sem redundância suficiente para absorver a rotação sem uma janela de indisponibilidade — mas não consultei manifesto/HelmRelease do `metrics-server` nem confirmei réplica única versus PDB, então a causa exata da falta de resiliência não está determinada por evidência direta de configuração.

## Linha do tempo

- 00:22:25 09/09/2026 BRT (epoch 1788924145000 · 2026-09-09T03:22:25.000Z) — Karpenter nomeia novo node para o pod `metrics-server-6bcb764664-x5tq4`.
- 00:22:50 09/09/2026 BRT (epoch 1788924170000 · 2026-09-09T03:22:50.000Z) — kubelet mata o container `metrics-server` (pod `clmwr`) enquanto o replicaset cria `x5tq4`.
- 00:23:02 09/09/2026 BRT (epoch 1788924182000 · 2026-09-09T03:23:02.000Z) — 1ª ocorrência de `FailedComputeMetricsReplicas` no namespace (`first_seen` do achado).
- 00:23:18 09/09/2026 BRT (epoch 1788924198000 · 2026-09-09T03:23:18.000Z) — 2ª ocorrência do Reason, mesmo erro ("server is currently unable to handle the request").
- 00:33:06 09/09/2026 BRT (epoch 1788924786000 · 2026-09-09T03:33:06.000Z)–00:33:12 09/09/2026 BRT (epoch 1788924792000 · 2026-09-09T03:33:12.000Z) — novo ciclo kill/recreate do `metrics-server` (pod `s4gbm`).
- 00:33:19 09/09/2026 BRT (epoch 1788924799000 · 2026-09-09T03:33:19.000Z), 00:33:34 09/09/2026 BRT (epoch 1788924814000 · 2026-09-09T03:33:34.000Z) — 3ª e 4ª ocorrências do Reason.
- 03:44:48 09/09/2026 BRT (epoch 1788936288000 · 2026-09-09T06:44:48.000Z)–03:45:28 09/09/2026 BRT (epoch 1788936328000 · 2026-09-09T06:45:28.000Z) — kill/recreate do `metrics-server` (pod `9t4g8`), incluindo `Unhealthy: readiness probe failed (connection refused)`.
- 03:45:29 09/09/2026 BRT (epoch 1788936329000 · 2026-09-09T06:45:29.000Z), 03:45:44 09/09/2026 BRT (epoch 1788936344000 · 2026-09-09T06:45:44.000Z), 03:45:59 09/09/2026 BRT (epoch 1788936359000 · 2026-09-09T06:45:59.000Z) — 5ª, 6ª e 7ª ocorrências (a última já com mensagem "no metrics returned", indicando API já respondendo mas sem dados ainda).
- 07:35:41 09/09/2026 BRT (epoch 1788950141000 · 2026-09-09T10:35:41.000Z)–07:35:54 09/09/2026 BRT (epoch 1788950154000 · 2026-09-09T10:35:54.000Z) e 07:54:08 09/09/2026 BRT (epoch 1788951248000 · 2026-09-09T10:54:08.000Z)–07:54:40 09/09/2026 BRT (epoch 1788951280000 · 2026-09-09T10:54:40.000Z) — dois novos ciclos kill/recreate do `metrics-server`.
- 07:35:53 09/09/2026 BRT (epoch 1788950153000 · 2026-09-09T10:35:53.000Z), 07:36:08 09/09/2026 BRT (epoch 1788950168000 · 2026-09-09T10:36:08.000Z), 07:36:23 09/09/2026 BRT (epoch 1788950183000 · 2026-09-09T10:36:23.000Z), 07:54:40 09/09/2026 BRT (epoch 1788951280000 · 2026-09-09T10:54:40.000Z), 07:54:55 09/09/2026 BRT (epoch 1788951295000 · 2026-09-09T10:54:55.000Z) — 8ª a 12ª ocorrências.
- 21:26:45 10/09/2026 BRT (epoch 1789086405000 · 2026-09-11T00:26:45.000Z)–21:27:06 10/09/2026 BRT (epoch 1789086426000 · 2026-09-11T00:27:06.000Z) — kill/recreate final do `metrics-server` (pod `j9t7z`, node `ip-10-0-1-119`).
- 21:27:07 10/09/2026 BRT (epoch 1789086427000 · 2026-09-11T00:27:07.000Z) e 21:27:22 10/09/2026 BRT (epoch 1789086442000 · 2026-09-11T00:27:22.000Z) — 13ª e 14ª ocorrências (`last_seen` do achado: **21:27:22 10/09/2026 BRT (epoch 1789086442000 · 2026-09-11T00:27:22.000Z)**).

Nenhum evento adicional foi observado entre 21:27:22 10/09/2026 BRT (epoch 1789086442000 · 2026-09-11T00:27:22.000Z) e o fim da janela de coleta (`window_to`), consistente com `last_seen` já ter sido atingido dentro da janela.

## Evidência

- 14 ocorrências de `FailedComputeMetricsReplicas` neste namespace na janela indicada — [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-institucional-cms%20FailedComputeMetricsReplicas&from_ts=1788808256645&to_ts=1789153856645&live=false).
- Todas as 14 ocorrências têm `status:warn` (nenhuma em `error`) — consulta `aggregate_events` com `query: "source:kubernetes env:production kube_namespace:medprev-institucional-cms FailedComputeMetricsReplicas"`, `group_by: status`, janela igual à do achado → `warn: 14`.
- O mesmo Reason ocorre em 8 namespaces no mesmo intervalo (219 eventos no total) — consulta `aggregate_events` com `query: "source:kubernetes env:production status:warn FailedComputeMetricsReplicas"`, `group_by: kube_namespace`, mesma janela → `medprev-rest-api:75, medprev-face-liveness-app:46, medprev-web-app:32, medprev-cms:17, medprev-institucional-cms:14, medprev-metabase:14, nginx-gateway-fabric:14, medprev-analytics-etl-airflow:7`.
- O serviço `medprev-institucional-cms` não tem nenhum span de APM na janela — consulta `aggregate_spans` com `query: "service:medprev-institucional-cms env:production"`, mesma janela → 0 registros.
- Não há span de erro do serviço na janela — consulta `aggregate_spans` com `query: "service:medprev-institucional-cms env:production status:error"` → 0 registros (não foi possível calcular a razão `handled`/`unhandled` por ausência total de spans).
- Único log `status:error` do serviço na janela é um `npm error` de build sem relação com o Reason — consulta `search_datadog_logs` com `query: "service:medprev-institucional-cms env:production status:error"` → 240 logs no total, primeiro registro em 15:02:30 11/09/2026 BRT (epoch 1789149750000 · 2026-09-11T18:02:30.000Z), fora de qualquer janela de ocorrência do Reason.
- O pod `metrics-server` em `kube-system` foi morto e recriado (via Karpenter) repetidas vezes na mesma janela, com falha de readiness probe (`connection refused :10250`) logo após cada recriação — consulta `search_datadog_events` com `query: "source:kubernetes env:production kube_namespace:kube-system metrics-server"`, mesma janela → 25 eventos, coincidindo em minuto com as rajadas do Reason listadas na Linha do tempo.

## Ação recomendada

Não há ação de código para `medprev-institucional-cms`; a ação cabe à infraestrutura do cluster: revisar a resiliência do Deployment `metrics-server` (réplicas, PodDisruptionBudget e afinidade contra o churn de nodes do Karpenter no nodepool `default`) para eliminar a janela de indisponibilidade que gera o `FailedComputeMetricsReplicas` cluster-wide.

## Corpo da issue

### Descrição do incidente
`FailedComputeMetricsReplicas` aparece repetidamente no HPA do namespace `medprev-institucional-cms` (14 ocorrências entre 07/09 e 11/09/2026, `status:warn`) porque o `metrics-server` do cluster (`eks-medprev-online-prd`, namespace `kube-system`) fica indisponível por curtos períodos sempre que o Karpenter recria seu pod em outro node. O mesmo Reason atinge simultaneamente outros 7 namespaces (219 ocorrências no total na mesma janela), confirmando que o problema é do `metrics-server`/cluster, não do workload `medprev-institucional-cms`. Impacto observável: o HPA do serviço fica sem dados de CPU/memória por alguns minutos a cada ciclo, podendo atrasar decisões de scale up/down durante picos de carga; não há impacto de erro de aplicação nem indisponibilidade do serviço em si (sem spans de erro, sem logs de erro correlacionados).

### Causa raiz
Sinal fraco/ruído para este workload especificamente: 0 de 0 spans de erro do serviço (`medprev-institucional-cms` não tem instrumentação APM na janela) e nenhum log de aplicação correlacionado — o defeito real não está no código deste serviço. Causa provável (inferência, sem confirmação de manifesto/config): o `metrics-server` tem resiliência insuficiente (réplicas/PDB/afinidade) para absorver o churn de nodes causado pelo Karpenter no nodepool `default`, gerando janelas de indisponibilidade da API `pods.metrics.k8s.io` que se propagam como `FailedComputeMetricsReplicas` em todos os HPAs do cluster. Não foi consultada a configuração do Deployment `metrics-server` (Helm values/Terraform), então a causa exata da falta de redundância não está determinada.

### Linha do tempo
Ver seção `## Linha do tempo` acima — cada rajada de `FailedComputeMetricsReplicas` no namespace coincide, no minuto, com um ciclo `Killing` → `SuccessfulCreate`/`Nominated` (Karpenter) → `Pulled`/`Started` → `Unhealthy (readiness probe, connection refused)` do pod `metrics-server` em `kube-system`, observado em 25 eventos na mesma janela.

### Evidências
- [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-institucional-cms%20FailedComputeMetricsReplicas&from_ts=1788808256645&to_ts=1789153856645&live=false)
- Query executada — cross-namespace: `source:kubernetes env:production status:warn FailedComputeMetricsReplicas`, agrupado por `kube_namespace`, janela 1788808256645–1789153856645 → 219 eventos em 8 namespaces.
- Query executada — pod `metrics-server`: `source:kubernetes env:production kube_namespace:kube-system metrics-server`, mesma janela → 25 eventos de kill/recreate/readiness-failure.
- Query executada — spans do serviço: `service:medprev-institucional-cms env:production` (e variante `status:error`), mesma janela → 0 registros em ambas.
- Query executada — logs de erro do serviço: `service:medprev-institucional-cms env:production status:error`, mesma janela → 240 logs, sem correlação temporal/semântica com o Reason.

### Ação recomendada
Repositório: infra — sem repositório de código de aplicação aplicável (`target_repo` do achado, `Medprev/medprev-institucional-cms`, não é o dono do defeito real). Ação concreta para a equipe de infraestrutura no repositório de IaC do cluster (`Medprev/medprev-cloud-iac`, conforme padrão do projeto): revisar o Deployment/HelmRelease do `metrics-server` no cluster `eks-medprev-online-prd` — aumentar réplicas (hoje aparenta rodar como pod único sendo recriado a cada disrupção) e/ou adicionar `PodDisruptionBudget` e afinidade/anti-afinidade contra nodes de curta duração do nodepool `default` do Karpenter. Validação: após o ajuste, confirmar por 7 dias que `source:kubernetes status:warn FailedComputeMetricsReplicas` não volta a ocorrer em nenhum namespace na mesma janela em que o `metrics-server` sofre disrupção de node.

### Volume
14 ocorrências entre `window_from` (16:10:56 07/09/2026 BRT · 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z)) e `window_to` (16:10:56 11/09/2026 BRT · 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z)) — igual ao `observed_count` do achado; não foi executada consulta com janela diferente para este total.

### Severidade e criticidade
`severity: medium` do achado não se aplica ao workload `medprev-institucional-cms` em si (nenhum erro de aplicação encontrado). O defeito real — indisponibilidade intermitente do `metrics-server` do cluster — tem criticidade potencialmente maior que a do achado original (inferência): afeta o autoscaling de pelo menos 8 namespaces em produção simultaneamente, incluindo serviços de maior volume de eventos (`medprev-rest-api`, `medprev-face-liveness-app`), o que pode atrasar reação a picos de carga em serviços com tráfego real de usuário — não confirmado impacto de indisponibilidade real ao usuário final nesta investigação.
