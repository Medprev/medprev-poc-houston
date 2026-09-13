---
fingerprint: k8s-eks-medprev-online-prd-FailedGetResourceMetric-medprev-metabase
source: kubernetes
reason: FailedGetResourceMetric
novelty: new
service: medprev-metabase
environment: production
window:
  from: 1788814356569
  to: 1789159956569
observed:
  count: 1
  first_seen: 1788924793000
  last_seen: 1788924793000
severity: medium
state: new
cost:
  input_tokens: 472859
  output_tokens: 10461
  cache_read_input_tokens: 364593
  cache_creation_input_tokens: 108256
  duration_s: 108.771
  usd: 0.6152336
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-metabase%20FailedGetResourceMetric&from_ts=1788814356569&to_ts=1789159956569&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-metabase%20FailedGetResourceMetric&from_ts=1788814356569&to_ts=1789159956569&live=false

## Causa raiz

O `HorizontalPodAutoscaler` do serviço `medprev-metabase` (cluster `eks-medprev-online-prd`) ficou repetidamente incapaz de obter métricas de CPU/memória via `metrics.k8s.io` durante a janela investigada — não foi uma ocorrência isolada: contei **15 eventos** desse HPA com razão `FailedGetResourceMetric`/`FailedComputeMetricsReplicas` entre 07/09 e 11/09/2026, agrupados em rajadas (03:22–03:33, 06:45, 10:35–10:55 em 09/09, e novamente 00:27 em 11/09), alternando entre duas causas: "the server is currently unable to handle the request (get pods.metrics.k8s.io)" e "no metrics returned from resource metrics API". Isso é **sinal, não ruído**: um HPA que perde visibilidade de métricas de forma recorrente fica cego para decidir escalonamento durante os minutos em que o erro persiste, o que é um problema operacional real, mesmo que nenhuma indisponibilidade de usuário final tenha sido capturada nesta janela (não há spans/logs de aplicação indexados para `medprev-metabase` — 0 resultados em ambas as consultas, ver Evidência).

Não há classificação `handled`/`unhandled` aplicável aqui porque este não é um erro de aplicação com spans — é um evento de infraestrutura Kubernetes (HPA vs. metrics-server), então a divisão `@error.handling` do protocolo de Error Tracking não se aplica.

Causa raiz da instabilidade do próprio `metrics-server` (por que ele fica intermitentemente indisponível) **não foi determinada** com as evidências consultadas: as consultas rodadas foram limitadas ao namespace `medprev-metabase`, e o `metrics-server` normalmente vive em `kube-system`, fora do escopo desta busca. Consultas que rodei e resultado de cada uma:
- Eventos `source:kubernetes` no namespace `medprev-metabase` com a query exata do achado → 15 eventos retornados (não 1, ver "Volume").
- `get_change_stories` para `medprev-metabase` (deployment/kubernetes/scale/crashloopbackoff/configuration) na janela → vazio, nenhum deploy ou mudança de manifesto correlacionada.
- Logs de aplicação (`kube_namespace:medprev-metabase status:(error OR warn)`) na janela do primeiro cluster de falhas → 0 logs.
- Spans APM (`service:medprev-metabase`) na janela inteira do achado → 0 spans (serviço não instrumentado com APM).
- Eventos de pod (`Killing`, `BackOff`, `Unhealthy`, `Scheduled`) na mesma janela → 2 eventos, ambos `Unhealthy: Startup probe failed (503)` num pod específico (`medprev-metabase-57bdcc4cdd-29t7t`), coincidindo em horário com o primeiro cluster de falhas do HPA — indício de churn de pod/nó nesse intervalo, mas não prova de causalidade sobre o metrics-server.

## Linha do tempo

- 00:22:57 09/09/2026 BRT (epoch 1788924177000 · 2026-09-09T03:22:57.000Z) — 1º evento do HPA: `FailedGetResourceMetric` (cpu e memory) por "server is currently unable to handle the request".
- 00:23:12 09/09/2026 BRT (epoch 1788924192000 · 2026-09-09T03:23:12.000Z) — repetição do mesmo erro, 15s depois.
- 00:23:27 09/09/2026 BRT (epoch 1788924207000 · 2026-09-09T03:23:27.000Z) — erro muda de causa: "no metrics returned from resource metrics API" (cpu e memory).
- 00:25:09 09/09/2026 BRT (epoch 1788924309000 · 2026-09-09T03:25:09.000Z) — Karpenter nomeia um novo pod (`medprev-metabase-57bdcc4cdd-dl8b9`) para agendamento em `nodeclaim/default-mz7js` — indício de scale/reagendamento de nó em curso.
- 00:29:16 09/09/2026 BRT (epoch 1788924556000 · 2026-09-09T03:29:16.000Z) e 00:29:26 09/09/2026 BRT (epoch 1788924566000 · 2026-09-09T03:29:26.000Z) — pod `medprev-metabase-57bdcc4cdd-29t7t` reporta `Unhealthy: Startup probe failed (HTTP 503)`.
- 00:33:13 09/09/2026 BRT (epoch 1788924793000 · 2026-09-09T03:33:13.000Z) — evento `first_seen`/`last_seen` do achado original: `FailedGetResourceMetric` (cpu), "server is currently unable to handle the request" — este é o evento que gerou o fingerprint, mas não é o único da janela.
- 03:45:39 09/09/2026 BRT (epoch 1788936339000 · 2026-09-09T06:45:39.000Z) e 03:45:54 09/09/2026 BRT (epoch 1788936354000 · 2026-09-09T06:45:54.000Z) — 2º cluster de falhas, mesmas duas causas alternadas.
- 07:35:50 09/09/2026 BRT (epoch 1788950150000 · 2026-09-09T10:35:50.000Z), 07:36:05 09/09/2026 BRT (epoch 1788950165000 · 2026-09-09T10:36:05.000Z), 07:36:20 09/09/2026 BRT (epoch 1788950180000 · 2026-09-09T10:36:20.000Z) — 3º cluster.
- 07:54:37 09/09/2026 BRT (epoch 1788951277000 · 2026-09-09T10:54:37.000Z), 07:54:52 09/09/2026 BRT (epoch 1788951292000 · 2026-09-09T10:54:52.000Z), 07:55:07 09/09/2026 BRT (epoch 1788951307000 · 2026-09-09T10:55:07.000Z) — 4º cluster, ~20min depois do anterior.
- 21:27:07 10/09/2026 BRT (epoch 1789086427000 · 2026-09-11T00:27:07.000Z), 21:27:22 10/09/2026 BRT (epoch 1789086442000 · 2026-09-11T00:27:22.000Z), 21:27:37 10/09/2026 BRT (epoch 1789086457000 · 2026-09-11T00:27:37.000Z) — 5º cluster, quase 38h depois do anterior, mesma assinatura de erro.

Nenhum deploy, mudança de manifesto Kubernetes ou scale event rastreado para `medprev-metabase` apareceu em `get_change_stories` na janela — a recorrência não está associada a uma mudança de versão do serviço.

## Evidência

- 15 eventos de `FailedGetResourceMetric`/`FailedComputeMetricsReplicas` do HPA `medprev-metabase` entre 17:52:36 07/09/2026 BRT (epoch 1788814356569 · 2026-09-07T20:52:36.569Z) e 17:52:36 11/09/2026 BRT (epoch 1789159956569 · 2026-09-11T20:52:36.569Z) — [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-metabase%20FailedGetResourceMetric&from_ts=1788814356569&to_ts=1789159956569&live=false).
- `get_change_stories(service_name=medprev-metabase, 17:52:36 07/09/2026 BRT (epoch 1788814356000 · 2026-09-07T20:52:36.000Z)–17:52:36 11/09/2026 BRT (epoch 1789159956000 · 2026-09-11T20:52:36.000Z), types=[kubernetes,scale,crashloopbackoff,configuration,deployment])` → 0 resultados.
- `search_datadog_logs(query="kube_namespace:medprev-metabase (status:error OR status:warn)", from=00:20:00 09/09/2026 BRT (epoch 1788924000000 · 2026-09-09T03:20:00.000Z), to=05:20:00 09/09/2026 BRT (epoch 1788942000000 · 2026-09-09T08:20:00.000Z))` → 0 logs.
- `aggregate_spans(query="service:medprev-metabase", group_by=[@http.status_code])` na janela inteira do achado → 0 spans (`traces_explorer_url`: https://app.datadoghq.com/apm/traces?end=1789159956569&historicalData=true&paused=true&query=service%3Amedprev-metabase&start=1788814356569).
- 2 eventos `Unhealthy: Startup probe failed (503)` no pod `medprev-metabase-57bdcc4cdd-29t7t`, coincidindo em janela com o primeiro cluster de falhas do HPA — mesma consulta de eventos acima, filtrada por `(Killing OR BackOff OR Unhealthy OR Scheduled)`.
- Link legado do achado: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-metabase%20FailedGetResourceMetric&from_ts=1788814356569&to_ts=1789159956569&live=false

## Ação recomendada

Infra — sem repositório de código para `medprev-metabase` (`target_repo: null`): investigar a saúde/recursos do `metrics-server` no cluster `eks-medprev-online-prd` (namespace `kube-system`, fora do escopo desta consulta) durante os 5 clusters de falha listados, e correlacionar com atividade do Karpenter (provisionamento/rotação de nós) no mesmo intervalo.

## Corpo da issue

### Descrição do incidente
O HorizontalPodAutoscaler do serviço `medprev-metabase`, no cluster `eks-medprev-online-prd`, falhou repetidamente ao buscar métricas de CPU e memória via `metrics.k8s.io` entre 07/09 e 11/09/2026. Isso significa que, durante essas janelas (minutos por ocorrência), o HPA não pôde decidir escalonamento — se houvesse pico de carga simultâneo, o serviço não escalaria a tempo. Nenhum impacto direto de usuário foi confirmado nesta investigação (sem logs de erro de aplicação, sem spans APM indexados para o serviço).

### Causa raiz
Sinal, não ruído: 15 ocorrências reais de `FailedGetResourceMetric` no HPA dentro da janela investigada, não um evento único. A causa raiz da instabilidade do `metrics-server` em si **não foi determinada** — as consultas rodadas (eventos, logs, spans, change stories) ficaram restritas ao namespace `medprev-metabase` e não alcançaram o `metrics-server`, que roda em `kube-system`. Há indício temporal (não prova) de correlação com atividade do Karpenter (nomeação de pod para novo nó em 00:25:09 09/09/2026 BRT (epoch 1788924309000 · 2026-09-09T03:25:09.000Z)) próximo ao primeiro cluster de falhas.

### Linha do tempo
- 00:22:57 09/09/2026 BRT (epoch 1788924177000 · 2026-09-09T03:22:57.000Z) a 00:23:27 09/09/2026 BRT (epoch 1788924207000 · 2026-09-09T03:23:27.000Z): 1º cluster de falhas do HPA (3 eventos, duas causas alternadas).
- 00:25:09 09/09/2026 BRT (epoch 1788924309000 · 2026-09-09T03:25:09.000Z): Karpenter nomeia novo pod `medprev-metabase-57bdcc4cdd-dl8b9` para `nodeclaim/default-mz7js`.
- 00:29:16 09/09/2026 BRT (epoch 1788924556000 · 2026-09-09T03:29:16.000Z) / 00:29:26 09/09/2026 BRT (epoch 1788924566000 · 2026-09-09T03:29:26.000Z): pod `medprev-metabase-57bdcc4cdd-29t7t` com `Unhealthy: Startup probe failed (503)`.
- 00:33:13 09/09/2026 BRT (epoch 1788924793000 · 2026-09-09T03:33:13.000Z): evento que originou este achado (fingerprint).
- 03:45:39 09/09/2026 BRT (epoch 1788936339000 · 2026-09-09T06:45:39.000Z) / 03:45:54 09/09/2026 BRT (epoch 1788936354000 · 2026-09-09T06:45:54.000Z): 2º cluster.
- 07:35:50 09/09/2026 BRT (epoch 1788950150000 · 2026-09-09T10:35:50.000Z) a 07:36:20 09/09/2026 BRT (epoch 1788950180000 · 2026-09-09T10:36:20.000Z): 3º cluster.
- 07:54:37 09/09/2026 BRT (epoch 1788951277000 · 2026-09-09T10:54:37.000Z) a 07:55:07 09/09/2026 BRT (epoch 1788951307000 · 2026-09-09T10:55:07.000Z): 4º cluster.
- 21:27:07 10/09/2026 BRT (epoch 1789086427000 · 2026-09-11T00:27:07.000Z) a 21:27:37 10/09/2026 BRT (epoch 1789086457000 · 2026-09-11T00:27:37.000Z): 5º cluster, ~38h depois do anterior.
- Nenhum deploy/mudança de manifesto do serviço correlacionado (`get_change_stories` vazio na janela).

### Evidências
- [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-metabase%20FailedGetResourceMetric&from_ts=1788814356569&to_ts=1789159956569&live=false) — 15 eventos.
- Query rodada: `get_change_stories(service_name=medprev-metabase, 17:52:36 07/09/2026 BRT (epoch 1788814356000 · 2026-09-07T20:52:36.000Z)–17:52:36 11/09/2026 BRT (epoch 1789159956000 · 2026-09-11T20:52:36.000Z))` → 0 resultados.
- Query rodada: `search_datadog_logs("kube_namespace:medprev-metabase (status:error OR status:warn)", 2026-09-09T03:20–08:20Z)` → 0 logs.
- Query rodada: `aggregate_spans("service:medprev-metabase", group_by=[@http.status_code])` na janela inteira → 0 spans ([Traces Explorer](https://app.datadoghq.com/apm/traces?end=1789159956569&historicalData=true&paused=true&query=service%3Amedprev-metabase&start=1788814356569)).
- Query rodada: eventos de pod `(Killing OR BackOff OR Unhealthy OR Scheduled)` no namespace, mesma janela do 1º cluster → 2 eventos `Unhealthy` (probe 503).

### Ação recomendada
Infra — sem repositório de código (`target_repo: null`), ação operacional: (1) verificar métricas de saúde/CPU/memória e reinícios do `metrics-server` em `kube-system` do cluster `eks-medprev-online-prd` nos 5 intervalos listados na linha do tempo; (2) correlacionar com eventos do Karpenter (provisionamento/terminação de nós) na mesma janela para confirmar ou descartar a hipótese de churn de nó como gatilho; (3) validar a correção observando se novas ocorrências de `FailedGetResourceMetric` neste namespace cessam nas próximas 96h após qualquer ajuste de recursos/HA do `metrics-server`.

### Volume
`observed_count` do achado original: 1 ocorrência, medida na janela `17:52:36 07/09/2026 BRT (epoch 1788814356569 · 2026-09-07T20:52:36.569Z)` a `17:52:36 11/09/2026 BRT (epoch 1789159956569 · 2026-09-11T20:52:36.569Z)`. Ao rodar a mesma query e mesma janela via ferramenta de leitura, obtive **15 eventos**, não 1 — a divergência não é explicada por diferença de janela (usei os mesmos limites em epoch ms); a hipótese mais provável é que o mecanismo de coleta do achado registra apenas o evento fundador do fingerprint (`first_seen`=`last_seen`=00:33:13 09/09/2026 BRT (epoch 1788924793000 · 2026-09-09T03:33:13.000Z)) em vez do total de eventos daquele Reason na janela — mas isso é inferência, não confirmado no código desta investigação.

### Severidade e criticidade
`severity` do achado: `medium`. Avaliação de criticidade (inferência): risco operacional moderado — o HPA ficando cego a métricas de forma recorrente (5 clusters em ~4 dias) pode atrasar autoscaling de `medprev-metabase` sob carga, mas não há evidência nesta janela de indisponibilidade de usuário (0 logs de erro de app, 0 spans com falha). A ausência de causa raiz confirmada do lado do `metrics-server` é o maior risco: sem ela, não é possível descartar recorrência crescente.
