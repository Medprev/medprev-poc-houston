---
fingerprint: k8s-eks-medprev-online-prd-Unhealthy-medprev-web-app
source: kubernetes
reason: Unhealthy
novelty: new
service: medprev-web-app
environment: production
window:
  from: 1788803749711
  to: 1789149349711
observed:
  count: 140
  first_seen: 1788840117000
  last_seen: 1789147502000
severity: medium
state: promoted
cost:
  input_tokens: 305418
  output_tokens: 9717
  cache_read_input_tokens: 235183
  cache_creation_input_tokens: 70227
  duration_s: 101.547
  usd: 0.4297816
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: https://github.com/Medprev/medprev-product-backlog/issues/6439
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-web-app%20Unhealthy&from_ts=1788803749711&to_ts=1789149349711&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-web-app%20Unhealthy&from_ts=1788803749711&to_ts=1789149349711&live=false

## Causa raiz

O achado é 100% de infraestrutura Kubernetes (namespace `medprev-web-app`, cluster `eks-medprev-online-prd`), não um erro de aplicação: consultei spans (`service:medprev-web-app status:error`) e logs (`service:medprev-web-app status:(error OR warn) kube_namespace:medprev-web-app`) na mesma janela e ambas as consultas retornaram **0 resultados** — não há span de erro nem log de aplicação correlacionado. Isso significa que não é possível classificar por `@error.handling` (handled/unhandled), pois esse campo não existe para eventos Kubernetes — a classificação sinal/ruído aqui é feita pelo padrão dos próprios eventos `Unhealthy`, não por spans de erro.

Os 140 eventos da janela são probes de **readiness/liveness/startup falhando** em dois padrões recorrentes: `connect: connection refused` (processo ainda não abriu a porta) e `context deadline exceeded` (endpoint de health respondeu lento demais para o timeout do probe). Isso ocorre em pods de **dois workloads diferentes** no mesmo namespace — `medprev-web-app-frontend` e `medprev-web-app-backend-graphql` — e em **múltiplos ReplicaSets diferentes** (`68bbd8d888`, `8596c6bd4c`, `6f8c5b84f`, `588dc84fbf` no backend-graphql), o que indica vários rollouts durante a janela, cada um recriando pods que falham brevemente o probe até ficarem prontos.

Isso é **sinal, não ruído**: falhas de probe durante rollout repetidas em workloads e ReplicaSets diferentes apontam para um probe mal calibrado (sem `startupProbe`, ou `initialDelaySeconds`/`timeoutSeconds` curtos demais para o tempo real de boot/aquecimento do processo), não para uma degradação pontual. A causa exata (por que o processo demora a responder/abrir a porta) **não está determinada** pelas evidências consultadas — as consultas de log e span do próprio serviço, que poderiam confirmar isso, voltaram vazias. Consultas efetivamente rodadas:
- `service:medprev-web-app status:error` (spans, agrupado por `@error.handling`/`@http.status_code`/`resource_name`) → 0 buckets.
- `service:medprev-web-app status:(error OR warn) kube_namespace:medprev-web-app` (logs) → 0 registros.
- `source:kubernetes env:production status:warn kube_namespace:medprev-web-app Unhealthy` (eventos) → 140 registros, usada para a linha do tempo abaixo.
- `source:kubernetes env:production kube_namespace:medprev-web-app (OOMKilled OR BackOff OR CrashLoopBackOff OR Killing OR Started)` agrupado por `kube_name` → 20 pods distintos retornados, 2 eventos cada (padrão de ciclo de vida normal de rollout, não crash loop).

## Linha do tempo

- 01:01:57 08/09/2026 BRT (epoch 1788840117000 · 2026-09-08T04:01:57.000Z) — Readiness probe falha por `connection refused` no pod `medprev-web-app-frontend-68bbd8d888-8kzt2` (primeira ocorrência do achado). Consulta: evento Kubernetes, `source:kubernetes ... Unhealthy`.
- 07:50:44 08/09/2026 BRT (epoch 1788864644000 · 2026-09-08T10:50:44.000Z) — Liveness probe falha por `context deadline exceeded` no pod `medprev-web-app-frontend-68bbd8d888-qn8lg`.
- 09:29:15 08/09/2026 BRT (epoch 1788870555000 · 2026-09-08T12:29:15.000Z) — Readiness probe falha (2x) por `context deadline exceeded`, mesmo pod `qn8lg`.
- 10:24:44 08/09/2026 BRT (epoch 1788873884000 · 2026-09-08T13:24:44.000Z) a 10:25:08 08/09/2026 BRT (epoch 1788873908000 · 2026-09-08T13:25:08.000Z) — Rajada de falhas de liveness/readiness por `context deadline exceeded` em três pods frontend diferentes (`lmxzt`, `qn8lg`, `xxmw9`, em nós distintos) num intervalo de ~24s — indica evento correlacionado (rollout ou instabilidade de rede/nó), não pod isolado.
- 22:29:29 08/09/2026 BRT (epoch 1788917369000 · 2026-09-09T01:29:29.000Z) — Readiness falha por `connection refused`, pod `zx4kf`.
- 00:20:12 09/09/2026 BRT (epoch 1788924012000 · 2026-09-09T03:20:12.000Z) — Readiness falha por `connection refused`, pod `9cf5t` (mesmo host/nó do evento anterior).
- 00:23:18 09/09/2026 BRT (epoch 1788924198000 · 2026-09-09T03:23:18.000Z) — Startup probe falha por `connection refused` no workload **backend-graphql**, pod `76g8j` — primeira ocorrência do outro workload afetado.
- 00:31:49 09/09/2026 BRT (epoch 1788924709000 · 2026-09-09T03:31:49.000Z) — Liveness+readiness falham por `context deadline exceeded`, pod frontend `cfwp8`.
- A busca retornou 140 eventos no total (window_from–window_to abaixo); os 12 primeiros (ordem cronológica) estão listados acima — o restante segue o mesmo padrão (`connection refused` / `context deadline exceeded`) alternando entre os dois workloads e vários ReplicaSets.
- Janela de coleta do achado: 14:55:49 07/09/2026 BRT (epoch 1788803749711 · 2026-09-07T17:55:49.711Z) até 14:55:49 11/09/2026 BRT (epoch 1789149349711 · 2026-09-11T17:55:49.711Z).
- Primeira ocorrência do histórico completo do achado: 01:01:57 08/09/2026 BRT (epoch 1788840117000 · 2026-09-08T04:01:57.000Z). Última ocorrência do histórico completo: 14:25:02 11/09/2026 BRT (epoch 1789147502000 · 2026-09-11T17:25:02.000Z).

## Evidência

- 140 ocorrências de `Unhealthy` (readiness/liveness/startup) no namespace no período da janela — [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-web-app%20Unhealthy&from_ts=1788803749711&to_ts=1789149349711&live=false).
- 0 spans de erro para `service:medprev-web-app status:error` na mesma janela, agrupado por `@error.handling`/`@http.status_code`/`resource_name` — consulta rodada via `aggregate_spans`, sem link pronto disponível (`traces_explorer_url` retornado pela ferramenta: https://app.datadoghq.com/apm/traces?end=1789149349711&historicalData=true&paused=true&query=service%3Amedprev-web-app+status%3Aerror&start=1788803749711).
- 0 logs de aplicação para `service:medprev-web-app status:(error OR warn) kube_namespace:medprev-web-app` na mesma janela — consulta `search_datadog_logs` (URL retornada pela ferramenta: https://app.datadoghq.com/logs?from_ts=1788803749711&live=false&query=service%3Amedprev-web-app+status%3A%28error+OR+warn%29+kube_namespace%3Amedprev-web-app&stream_sort=desc&to_ts=1789149349711).
- 20 pods distintos (frontend e backend-graphql, 4 ReplicaSets diferentes no backend-graphql) com 2 eventos de ciclo de vida cada (`Started`/`Killing`/etc.) na mesma janela — consulta `aggregate_events` com `source:kubernetes env:production kube_namespace:medprev-web-app (OOMKilled OR BackOff OR CrashLoopBackOff OR Killing OR Started)`, agrupado por `kube_name`; padrão consistente com rollouts normais, não crash loop.

## Ação recomendada

Revisar e ajustar os probes (`readinessProbe`/`livenessProbe`/`startupProbe`) do Deployment `medprev-web-app-frontend` (e do `medprev-web-app-backend-graphql`, que também apresentou o mesmo padrão) no repositório `Medprev/medprev-web-app`, adicionando `startupProbe` com folga suficiente e revendo `initialDelaySeconds`/`timeoutSeconds` para acomodar o tempo real de boot/resposta do endpoint `/api/health`.

## Corpo da issue

### Descrição do incidente
O namespace `medprev-web-app` (cluster `eks-medprev-online-prd`) registrou 140 eventos `Unhealthy` de readiness/liveness/startup probe entre 14:55:49 07/09/2026 BRT (epoch 1788803749711 · 2026-09-07T17:55:49.711Z) e 14:55:49 11/09/2026 BRT (epoch 1789149349711 · 2026-09-11T17:55:49.711Z), afetando tanto o workload `medprev-web-app-frontend` quanto `medprev-web-app-backend-graphql`. Impacto observável: pods brevemente marcados como não-prontos/reiniciados durante rollouts, podendo causar indisponibilidade momentânea de réplicas atrás do serviço durante deploys.

### Causa raiz
Sinal, não ruído: 140 ocorrências reais de falha de probe em múltiplos pods e ReplicaSets distintos (não um único pod isolado), com 0 spans de erro e 0 logs de aplicação correlacionados nas mesmas consultas. Causa raiz específica **não determinada** pelas evidências consultadas — os dois padrões observados (`connection refused` e `context deadline exceeded`) são consistentes com probes mal calibrados (ausência de `startupProbe` ou `timeoutSeconds`/`initialDelaySeconds` curtos para o tempo real de boot), mas isso é inferência, não confirmado por log/span de aplicação.

### Linha do tempo
- 01:01:57 08/09/2026 BRT (epoch 1788840117000 · 2026-09-08T04:01:57.000Z) readiness `connection refused`, frontend `8kzt2` (primeira ocorrência do achado).
- 07:50:44 08/09/2026 BRT (epoch 1788864644000 · 2026-09-08T10:50:44.000Z) liveness `context deadline exceeded`, frontend `qn8lg`.
- 09:29:15 08/09/2026 BRT (epoch 1788870555000 · 2026-09-08T12:29:15.000Z) readiness `context deadline exceeded` (2x), frontend `qn8lg`.
- 10:24:44 08/09/2026 BRT (epoch 1788873884000 · 2026-09-08T13:24:44.000Z)–10:25:08 08/09/2026 BRT (epoch 1788873908000 · 2026-09-08T13:25:08.000Z) rajada correlacionada em 3 pods frontend diferentes (`lmxzt`, `qn8lg`, `xxmw9`), nós distintos.
- 22:29:29 08/09/2026 BRT (epoch 1788917369000 · 2026-09-09T01:29:29.000Z) e 00:20:12 09/09/2026 BRT (epoch 1788924012000 · 2026-09-09T03:20:12.000Z) readiness `connection refused`, frontend `zx4kf`/`9cf5t`.
- 00:23:18 09/09/2026 BRT (epoch 1788924198000 · 2026-09-09T03:23:18.000Z) startup probe `connection refused`, backend-graphql `76g8j` — primeira ocorrência no segundo workload.
- 00:31:49 09/09/2026 BRT (epoch 1788924709000 · 2026-09-09T03:31:49.000Z) liveness+readiness `context deadline exceeded`, frontend `cfwp8`.
- Últimos 128 eventos do total de 140 seguem o mesmo padrão até a última ocorrência do achado, 14:25:02 11/09/2026 BRT (epoch 1789147502000 · 2026-09-11T17:25:02.000Z).
- Correlação: `aggregate_events` mostrou 4 ReplicaSets diferentes no backend-graphql ativos na janela, indicando múltiplos rollouts — cada um introduzindo nova janela de instabilidade de probe.

### Evidências
- [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-web-app%20Unhealthy&from_ts=1788803749711&to_ts=1789149349711&live=false) — 140 eventos.
- Spans de erro (`service:medprev-web-app status:error`, agrupado por `@error.handling`/`@http.status_code`): 0 buckets — https://app.datadoghq.com/apm/traces?end=1789149349711&historicalData=true&paused=true&query=service%3Amedprev-web-app+status%3Aerror&start=1788803749711
- Logs de aplicação (`service:medprev-web-app status:(error OR warn) kube_namespace:medprev-web-app`): 0 registros — https://app.datadoghq.com/logs?from_ts=1788803749711&live=false&query=service%3Amedprev-web-app+status%3A%28error+OR+warn%29+kube_namespace%3Amedprev-web-app&stream_sort=desc&to_ts=1789149349711
- Eventos de ciclo de vida (`OOMKilled OR BackOff OR CrashLoopBackOff OR Killing OR Started`) agrupados por `kube_name`: 20 pods, 2 eventos cada, sem sinal de `CrashLoopBackOff` recorrente isolado.

### Ação recomendada
Repositório `Medprev/medprev-web-app`: revisar a definição de probes nos manifests/Helm chart dos Deployments `medprev-web-app-frontend` e `medprev-web-app-backend-graphql` (readinessProbe/livenessProbe apontando para `/api/health` e `/health` respectivamente). Adicionar `startupProbe` dedicado com `failureThreshold`/`periodSeconds` suficientes para cobrir o tempo real de boot, e aumentar `timeoutSeconds` do readiness/liveness caso o endpoint de health leve mais que o timeout atual para responder sob cold start. Validar monitorando o mesmo Events Explorer acima após o próximo deploy: sucesso é zero ou near-zero eventos `Unhealthy` durante o rollout subsequente.

### Volume
140 ocorrências entre 14:55:49 07/09/2026 BRT (epoch 1788803749711 · 2026-09-07T17:55:49.711Z) e 14:55:49 11/09/2026 BRT (epoch 1789149349711 · 2026-09-11T17:55:49.711Z) — igual ao `observed_count` do achado; não consultei uma janela alternativa para este número.

### Severidade e criticidade
`severity` do achado: `medium`. Avaliação de criticidade (inferência): baixa a moderada — os eventos são de curta duração e ligados a ciclo de rollout, sem evidência de indisponibilidade sustentada (0 logs/spans de erro de aplicação), mas a recorrência em dois workloads e múltiplos ReplicaSets sugere risco real de blips de disponibilidade a cada deploy, o que justifica correção antes que vire um SLO-impacting incident em um rollout maior.
