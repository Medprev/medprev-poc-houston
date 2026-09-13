---
fingerprint: k8s-eks-medprev-online-prd-FailedUpdateStatus-medprev-rest-api
source: kubernetes
reason: FailedUpdateStatus
novelty: new
service: medprev-rest-api
environment: production
window:
  from: 1788814356569
  to: 1789159956569
observed:
  count: 1
  first_seen: 1789088790000
  last_seen: 1789088790000
severity: medium
state: new
cost:
  input_tokens: 470179
  output_tokens: 8572
  cache_read_input_tokens: 400969
  cache_creation_input_tokens: 69198
  duration_s: 90.012
  usd: 0.4473758
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20FailedUpdateStatus&from_ts=1788814356569&to_ts=1789159956569&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20FailedUpdateStatus&from_ts=1788814356569&to_ts=1789159956569&live=false

Both queries returned empty — no application error logs or error spans for `medprev-rest-api` in the 10-minute window around the conflict. This confirms the event is infra-level (control-plane object contention), not an application fault.

## Causa raiz

O achado é um evento do controlador `horizontal-pod-autoscaler` no namespace `medprev-rest-api` do cluster `eks-medprev-online-prd`, reportando `FailedUpdateStatus` (conflito de escrita otimista: "the object has been modified; please apply your changes to the latest version and try again") ao tentar atualizar o objeto `horizontalpodautoscalers.autoscaling/medprev-rest-api-pp`. Isso é **RUÍDO**: consultei os eventos do mesmo objeto no minuto do incidente e encontrei que, no mesmo segundo (22:06:29 10/09/2026 BRT (epoch 1789088789000 · 2026-09-11T01:06:29.000Z) vs 22:06:30 10/09/2026 BRT (epoch 1789088790000 · 2026-09-11T01:06:30.000Z)), o `deployment-controller` executou `ScalingReplicaSet` (escalou de 0 para 1 réplica) — ou seja, dois controladores do control plane escreveram no mesmo objeto quase simultaneamente, gerando um conflito de versão (`resourceVersion`) que é esperado e transitório no client-go/Kubernetes: o HPA controller reconcilia no próximo ciclo (padrão ~15s) sem intervenção. Não há classificação `handled`/`unhandled` aplicável aqui porque este não é um erro de aplicação rastreado por Error Tracking — é um evento de infraestrutura do Kubernetes; a métrica equivalente que meço é: consultei spans de erro (`service:medprev-rest-api status:error`) e logs de erro (`service:medprev-rest-api status:error`) na janela de 10 minutos ao redor do evento (22:01:30 10/09/2026 BRT (epoch 1789088490000 · 2026-09-11T01:01:30.000Z)–22:11:30 10/09/2026 BRT (epoch 1789089090000 · 2026-09-11T01:11:30.000Z)) e ambas as consultas retornaram **0 resultados** — nenhum impacto observável na aplicação. A escala de fato prosseguiu com sucesso (scale-down de 1→0 em 22:11:52 10/09/2026 BRT (epoch 1789089112000 · 2026-09-11T01:11:52.000Z)), confirmando que o conflito não travou o autoscaling.

Consultas rodadas e retorno:
- `search_datadog_events` com a query do achado (janela completa `window_from`–`window_to`) → 1 evento (o próprio achado).
- `aggregate_events` por `status` no namespace `medprev-rest-api` na mesma janela → `info: 2423`, `warn: 375` (o `FailedUpdateStatus` é 1 entre 375 warns).
- `search_datadog_events` ±1h ao redor do timestamp do mesmo objeto HPA → 4 eventos: três `FailedComputeMetricsReplicas`/`FailedGetResourceMetric` (falha transitória do metrics-server, resolvida em segundos, evento distinto, não correlacionado diretamente) às 21:27:07 10/09/2026 BRT (epoch 1789086427000 · 2026-09-11T00:27:07.000Z), 21:27:23 10/09/2026 BRT (epoch 1789086443000 · 2026-09-11T00:27:23.000Z), 21:27:38 10/09/2026 BRT (epoch 1789086458000 · 2026-09-11T00:27:38.000Z), e o `FailedUpdateStatus` às 22:06:30 10/09/2026 BRT (epoch 1789088790000 · 2026-09-11T01:06:30.000Z).
- `aggregate_events` free-text `FailedUpdateStatus` sobre 30 dias, agrupado por `kube_namespace` → só `medprev-rest-api: 3` ocorrências no período — não é um padrão generalizado no cluster, mas também não se repetiu no mesmo dia após o evento.
- `search_datadog_events` na janela ±7,5 min ao redor do conflito, filtrando `SuccessfulRescale`/`ScalingReplicaSet` → confirma `ScalingReplicaSet` (0→1) em 22:06:29 10/09/2026 BRT (epoch 1789088789000 · 2026-09-11T01:06:29.000Z) e (1→0) em 22:11:52 10/09/2026 BRT (epoch 1789089112000 · 2026-09-11T01:11:52.000Z): o autoscaling funcionou normalmente antes e depois do conflito.
- `search_datadog_logs` (`service:medprev-rest-api status:error`, 22:01:30 10/09/2026 BRT (epoch 1789088490000 · 2026-09-11T01:01:30.000Z)–22:11:30 10/09/2026 BRT (epoch 1789089090000 · 2026-09-11T01:11:30.000Z)) → 0 logs.
- `aggregate_spans` (`service:medprev-rest-api status:error`, mesma janela, agrupado por `@error.handling`/`@http.status_code`) → 0 spans.

## Linha do tempo

1. 21:27:07 10/09/2026 BRT (epoch 1789086427000 · 2026-09-11T00:27:07.000Z) a 21:27:38 10/09/2026 BRT (epoch 1789086458000 · 2026-09-11T00:27:38.000Z) — três eventos separados de `FailedComputeMetricsReplicas`/`FailedGetResourceMetric` no HPA `medprev-rest-api-pp`: o metrics-server ficou temporariamente indisponível ("server is currently unable to handle the request" / "no metrics returned"). Autolimitado, sem evento de recuperação explícito buscado (não é o Reason do achado; citado apenas como contexto de instabilidade do metrics pipeline na mesma hora). Consulta: `search_datadog_events`, `kube_name:medprev-rest-api-pp kube_kind:horizontalpodautoscaler`.
2. 22:06:29 10/09/2026 BRT (epoch 1789088789000 · 2026-09-11T01:06:29.000Z) — `deployment-controller` executa `ScalingReplicaSet`: replica set `medprev-rest-api-pp-5c6b45b948` escalado de 0 para 1. Consulta: `search_datadog_events` com filtro `ScalingReplicaSet`.
3. 22:06:30 10/09/2026 BRT (epoch 1789088790000 · 2026-09-11T01:06:30.000Z) — `horizontal-pod-autoscaler` reporta `FailedUpdateStatus` ao tentar atualizar seu próprio objeto, colidindo com a escrita concorrente do passo anterior (evento do achado, `datadog_url`).
4. 22:11:52 10/09/2026 BRT (epoch 1789089112000 · 2026-09-11T01:11:52.000Z) — `deployment-controller` executa `ScalingReplicaSet`: replica set `medprev-rest-api-pp-67c588bddd` escalado de 1 para 0 — confirma que o ciclo de autoscaling completou normalmente depois do conflito.

`window_from`: 17:52:36 07/09/2026 BRT (epoch 1788814356569 · 2026-09-07T20:52:36.569Z); `window_to`: 17:52:36 11/09/2026 BRT (epoch 1789159956569 · 2026-09-11T20:52:36.569Z). `first_seen` e `last_seen` coincidem em 22:06:30 10/09/2026 BRT (epoch 1789088790000 · 2026-09-11T01:06:30.000Z) — ocorrência única no histórico completo do achado.

## Evidência

- Evento original do achado (Events Explorer, namespace + Reason, janela fixada): https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20FailedUpdateStatus&from_ts=1788814356569&to_ts=1789159956569&live=false
- Conflito de escrita concorrente confirmado: `ScalingReplicaSet` (0→1) e `FailedUpdateStatus` no mesmo objeto ocorreram no mesmo segundo — consulta: `source:kubernetes env:production kube_name:medprev-rest-api-pp (SuccessfulRescale OR ScalingReplicaSet OR HorizontalPodAutoscaler)`, janela 22:01:30 10/09/2026 BRT (epoch 1789088490000 · 2026-09-11T01:01:30.000Z)–22:16:30 10/09/2026 BRT (epoch 1789089390000 · 2026-09-11T01:16:30.000Z), 3 eventos retornados.
- Autoscaling completou sem travar: `ScalingReplicaSet` (1→0) 5min22s depois, mesma consulta acima.
- Frequência do padrão: `aggregate_events` free-text `FailedUpdateStatus` env:production, 30 dias, agrupado por `kube_namespace` → apenas `medprev-rest-api: 3`.
- Namespace geral não é anormalmente ruidoso além disso: `aggregate_events` por `status` no namespace na janela do achado → `info: 2423`, `warn: 375`.
- Sem impacto na aplicação: `search_datadog_logs` `service:medprev-rest-api status:error` na janela ±5min → 0 resultados (https://app.datadoghq.com/logs?from_ts=1789088490000&live=false&query=service%3Amedprev-rest-api+status%3Aerror&stream_sort=desc&to_ts=1789089090000).
- Sem spans de erro correlacionados: `aggregate_spans` `service:medprev-rest-api status:error`, mesma janela → 0 resultados (https://app.datadoghq.com/apm/traces?end=1789089090000&historicalData=true&paused=true&query=service%3Amedprev-rest-api+status%3Aerror&start=1789088490000).

## Ação recomendada

Nenhuma ação de código é necessária — é ruído esperado do control plane do Kubernetes (conflito de `resourceVersion` autolimitado). Recomendo marcar este achado como `discarded`/ruído no fluxo do houston para não competir por vaga de investigação com achados reais.

## Corpo da issue

### Descrição do incidente
Evento único e isolado (`observed_count`: 1) do controlador `horizontal-pod-autoscaler` no cluster `eks-medprev-online-prd`, namespace `medprev-rest-api`, componente `medprev-rest-api-pp`: falha ao atualizar o status do objeto HorizontalPodAutoscaler por conflito de versão (`the object has been modified; please apply your changes to the latest version and try again`). Sem impacto observável no serviço.

### Causa raiz
RUÍDO — 0 spans e 0 logs de erro em `medprev-rest-api` na janela do evento (consultas: `service:medprev-rest-api status:error` em spans e logs, 22:01:30 10/09/2026 BRT (epoch 1789088490000 · 2026-09-11T01:01:30.000Z)–22:11:30 10/09/2026 BRT (epoch 1789089090000 · 2026-09-11T01:11:30.000Z), ambas vazias). Causa confirmada: colisão de escrita otimista entre o `horizontal-pod-autoscaler` e o `deployment-controller` no mesmo objeto, ambos atuando no mesmo segundo (22:06:29 10/09/2026 BRT (epoch 1789088789000 · 2026-09-11T01:06:29.000Z) `ScalingReplicaSet` 0→1, 22:06:30 10/09/2026 BRT (epoch 1789088790000 · 2026-09-11T01:06:30.000Z) `FailedUpdateStatus`). Padrão conhecido e autolimitado do client-go/Kubernetes; o ciclo seguinte do HPA reconcilia sem intervenção, confirmado pelo `ScalingReplicaSet` (1→0) 5min22s depois.

### Linha do tempo
1. 21:27:07 10/09/2026 BRT (epoch 1789086427000 · 2026-09-11T00:27:07.000Z)–21:27:38 10/09/2026 BRT (epoch 1789086458000 · 2026-09-11T00:27:38.000Z) — instabilidade transitória e não relacionada do metrics-server (`FailedComputeMetricsReplicas`/`FailedGetResourceMetric`) no mesmo HPA.
2. 22:06:29 10/09/2026 BRT (epoch 1789088789000 · 2026-09-11T01:06:29.000Z) — `deployment-controller` escala replica set `medprev-rest-api-pp-5c6b45b948` de 0 para 1.
3. 22:06:30 10/09/2026 BRT (epoch 1789088790000 · 2026-09-11T01:06:30.000Z) — `horizontal-pod-autoscaler` reporta `FailedUpdateStatus` no mesmo objeto (evento do achado).
4. 22:11:52 10/09/2026 BRT (epoch 1789089112000 · 2026-09-11T01:11:52.000Z) — `deployment-controller` escala replica set `medprev-rest-api-pp-67c588bddd` de 1 para 0, confirmando reconciliação normal.

### Evidências
- https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20FailedUpdateStatus&from_ts=1788814356569&to_ts=1789159956569&live=false
- https://app.datadoghq.com/logs?from_ts=1789088490000&live=false&query=service%3Amedprev-rest-api+status%3Aerror&stream_sort=desc&to_ts=1789089090000 (0 resultados)
- https://app.datadoghq.com/apm/traces?end=1789089090000&historicalData=true&paused=true&query=service%3Amedprev-rest-api+status%3Aerror&start=1789088490000 (0 resultados)
- Consulta: `aggregate_events` free-text `FailedUpdateStatus` env:production, 30 dias, group by `kube_namespace` → apenas `medprev-rest-api: 3`.

### Ação recomendada
`target_repo`: Medprev/medprev-rest-api. Nenhuma mudança de código é necessária — não há função/arquivo afetado, é comportamento esperado do control plane do Kubernetes. Ação operacional: marcar este fingerprint como ruído/descartado no houston (`state: discarded`) para não consumir slots de investigação em ciclos futuros de dedup/cap. Validação: confirmar que o mesmo fingerprint não reaparece com volume crescente nas próximas janelas de coleta; se `FailedUpdateStatus` passar a ocorrer com alta frequência (dezenas/dia) no mesmo HPA, aí sim investigar contenção real no client-go ou excesso de escritores concorrentes no objeto.

### Volume
`observed_count`: 1, medido na janela `window_from`–`window_to` (17:52:36 07/09/2026 BRT · 17:52:36 07/09/2026 BRT (epoch 1788814356569 · 2026-09-07T20:52:36.569Z) até 17:52:36 11/09/2026 BRT · 17:52:36 11/09/2026 BRT (epoch 1789159956569 · 2026-09-11T20:52:36.569Z)). Consulta adicional em janela de 30 dias (mais ampla) retornou 3 ocorrências no mesmo namespace — divergência explicada pela janela maior, não por inconsistência.

### Severidade e criticidade
`severity` do achado é `medium`, mas não se aplica ao evento em si, que é ruído confirmado. Criticidade real (inferência): baixa — nenhum impacto de usuário, dados ou operação detectado; é o comportamento esperado de controladores concorrentes do Kubernetes, sem correlação de erro de aplicação.
