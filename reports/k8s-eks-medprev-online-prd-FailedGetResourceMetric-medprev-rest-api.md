---
fingerprint: k8s-eks-medprev-online-prd-FailedGetResourceMetric-medprev-rest-api
source: kubernetes
reason: FailedGetResourceMetric
novelty: new
service: medprev-rest-api
environment: production
window:
  from: 1788808256645
  to: 1789153856645
observed:
  count: 3
  first_seen: 1788924893000
  last_seen: 1789086458000
severity: medium
state: new
cost:
  input_tokens: 327409
  output_tokens: 9804
  cache_read_input_tokens: 245704
  cache_creation_input_tokens: 81697
  duration_s: 109.749
  usd: 0.47865579999999996
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20FailedGetResourceMetric&from_ts=1788808256645&to_ts=1789153856645&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20FailedGetResourceMetric&from_ts=1788808256645&to_ts=1789153856645&live=false

## Causa raiz

O `medprev-rest-api-gama` (e outros HPAs do namespace `medprev-rest-api`: `-adm`, `-pp`, `-ag`) sofreu uma falha transitória de coleta de métricas de recursos (`FailedGetResourceMetric`/`FailedComputeMetricsReplicas`) vinda do `horizontal-pod-autoscaler`, não da aplicação — a mensagem de erro (`unable to fetch metrics from resource metrics API: the server is currently unable to handle the request (get pods.metrics.k8s.io)`) indica indisponibilidade momentânea do `metrics-server` do cluster `eks-medprev-online-prd`, componente de controle do Kubernetes, não código da API. Isso é **RUÍDO em relação à aplicação**: consultei `aggregate_spans` para `service:medprev-rest-api env:production status:error` na janela do episódio (00:15:00 09/09/2026 BRT (epoch 1788923700000 · 2026-09-09T03:15:00.000Z)–00:45:00 09/09/2026 BRT (epoch 1788925500000 · 2026-09-09T03:45:00.000Z)) e o resultado foi **0 spans de erro** (`n=0`, `total_buckets=0`) — ou seja, nenhuma requisição da aplicação falhou por causa disso, e não há `trace_id` de erro para seguir (não determinado por ausência de dados, não por hipótese). A consulta a `search_datadog_logs` na mesma janela retornou **40 logs `status:error`**, mas o único registro amostrado é um warning do SDK AWS (`@smithy/node-http-handler` excedendo `requestTimeout` de 1000ms) — um problema de timeout de cliente HTTP para um serviço AWS downstream, sem ligação evidente com o `metrics-server`; trato isso como correlação temporal não confirmada como causal, não como causa do achado original.

Consultas efetivamente rodadas e o que cada uma devolveu:
- `search_datadog_events` com a query exata do achado, janela `window_from`–`window_to`: **78 eventos** (eu vi os 24 mais antigos, todos concentrados entre 00:22:51 09/09/2026 BRT (epoch 1788924171000 · 2026-09-09T03:22:51.000Z) e 00:33:38 09/09/2026 BRT (epoch 1788924818000 · 2026-09-09T03:33:38.000Z)).
- `aggregate_spans` (`service:medprev-rest-api env:production status:error`, 00:15:00 09/09/2026 BRT (epoch 1788923700000 · 2026-09-09T03:15:00.000Z)–00:45:00 09/09/2026 BRT (epoch 1788925500000 · 2026-09-09T03:45:00.000Z)): 0 resultados.
- `search_datadog_logs` (mesmo filtro/janela): 40 logs `status:error`, 1 amostrado (SDK AWS timeout).

## Linha do tempo

1. 00:22:51 09/09/2026 BRT (epoch 1788924171000 · 2026-09-09T03:22:51.000Z) — Primeiro conjunto de eventos do HPA (4 HorizontalPodAutoscalers do namespace: `-adm`, `-pp`, `-ag`, `-gama`) reporta `FailedGetResourceMetric`/`FailedComputeMetricsReplicas` para CPU e memória, causa: `the server is currently unable to handle the request (get pods.metrics.k8s.io)`. Fonte: Events Explorer, query `source:kubernetes env:production status:warn kube_namespace:medprev-rest-api FailedGetResourceMetric`.
2. 00:23:06 09/09/2026 BRT (epoch 1788924186000 · 2026-09-09T03:23:06.000Z) a 00:33:23 09/09/2026 BRT (epoch 1788924803000 · 2026-09-09T03:33:23.000Z) — Repetição do mesmo padrão de erro (mesma mensagem "server is currently unable to handle the request") a cada ~15s, nos mesmos 4 HPAs — indica indisponibilidade sustentada do `metrics-server`, não um evento isolado.
3. 00:23:21 09/09/2026 BRT (epoch 1788924201000 · 2026-09-09T03:23:21.000Z) — Mudança de causa: passa a `no metrics returned from resource metrics API` (metrics-server responde, mas sem dado do pod).
4. 00:30:23 09/09/2026 BRT (epoch 1788924623000 · 2026-09-09T03:30:23.000Z) a 00:30:53 09/09/2026 BRT (epoch 1788924653000 · 2026-09-09T03:30:53.000Z) — Nova variação: `did not receive metrics for targeted pods (pods might be unready)`, isolada no HPA `-gama` — sugere rollout/restart de pod concorrente com a falta de métricas.
5. 00:33:08 09/09/2026 BRT (epoch 1788924788000 · 2026-09-09T03:33:08.000Z) a 00:33:38 09/09/2026 BRT (epoch 1788924818000 · 2026-09-09T03:33:38.000Z) — Volta ao padrão "server is currently unable to handle the request" nos 4 HPAs; esse é o último lote que consultei (query retornou 78 no total, exibi os 24 mais antigos — não paginei o restante para conter custo).
6. Segundo o achado: `first_seen` **00:34:53 09/09/2026 BRT (epoch 1788924893000 · 2026-09-09T03:34:53.000Z)** — cerca de 12 minutos depois do primeiro evento que encontrei na minha consulta, e `last_seen` **21:27:38 10/09/2026 BRT (epoch 1789086458000 · 2026-09-11T00:27:38.000Z)** — quase 2 dias depois, indicando que o problema se repetiu em pelo menos uma outra ocasião dentro do histórico do achado (não investigada aqui por orçamento).

Divergência de contagem: minha consulta ao Datadog devolveu 78 eventos na mesma janela em que o achado registra `observed_count: 3` ("3 ocorrências entre 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) e 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z)"). A explicação mais provável, dada a lógica de fingerprint por namespace deste pipeline (não por workload), é que o coletor agrupa múltiplos eventos brutos do Datadog num único "achado novo" por execução/rodada de coleta — os 78 eventos brutos e os 3 "observed" medem coisas diferentes (evento individual do Datadog vs. detecção do coletor), não uma divergência inexplicada.

## Evidência

- 78 eventos `FailedGetResourceMetric`/`FailedComputeMetricsReplicas` na janela do achado, concentrados num episódio de ~11 min em 00:22:51 09/09/2026 BRT (epoch 1788924171000 · 2026-09-09T03:22:51.000Z)–00:33:38 09/09/2026 BRT (epoch 1788924818000 · 2026-09-09T03:33:38.000Z), afetando 4 HPAs do namespace: [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20FailedGetResourceMetric&from_ts=1788808256645&to_ts=1789153856645&live=false).
- 0 spans de erro da aplicação (`service:medprev-rest-api env:production status:error`) na janela 00:15:00 09/09/2026 BRT (epoch 1788923700000 · 2026-09-09T03:15:00.000Z)–00:45:00 09/09/2026 BRT (epoch 1788925500000 · 2026-09-09T03:45:00.000Z) — consulta `aggregate_spans`, contagem `n=0`.
- 40 logs `status:error` de `medprev-rest-api` na mesma janela — consulta `search_datadog_logs` (`service:medprev-rest-api env:production status:error`, mesma janela), campo de contagem `count:40`; amostra única inspecionada é um warning de timeout do SDK AWS (`@smithy/node-http-handler`), não confirmado como relacionado à falha de métricas.
- Causa raiz do lado do Kubernetes (mensagem literal do evento): "the server is currently unable to handle the request (get pods.metrics.k8s.io)" — mesmo link do Events Explorer acima.

## Ação recomendada

Ação operacional de infraestrutura: verificar a saúde/recursos do `metrics-server` no cluster `eks-medprev-online-prd` no horário do episódio (00:22:51 09/09/2026 BRT (epoch 1788924171000 · 2026-09-09T03:22:51.000Z)–00:33:38 09/09/2026 BRT (epoch 1788924818000 · 2026-09-09T03:33:38.000Z)) e, se recorrente, aumentar réplicas/`resources` do `metrics-server` ou investigar pressão de API server; não há ação de código no repositório `medprev-rest-api` a fazer para este achado.

## Corpo da issue

### Descrição do incidente
Entre 00:22:51 09/09/2026 BRT (epoch 1788924171000 · 2026-09-09T03:22:51.000Z) e 00:33:38 09/09/2026 BRT (epoch 1788924818000 · 2026-09-09T03:33:38.000Z), os 4 HorizontalPodAutoscalers do namespace `medprev-rest-api` no cluster `eks-medprev-online-prd` (`-adm`, `-pp`, `-ag`, `-gama`) reportaram falha repetida ao obter métricas de CPU/memória via `pods.metrics.k8s.io`, com a causa "the server is currently unable to handle the request". Durante esse período o HPA não pôde recalcular réplicas com base em uso real de recursos. O achado também tem `first_seen`/`last_seen` que sugerem recorrência do mesmo padrão em pelo menos uma outra janela até 2026-09-11, não investigada aqui.

### Causa raiz
RUÍDO em relação à aplicação: 0 spans de erro (`n=0`) em `service:medprev-rest-api` na janela do episódio. A causa é indisponibilidade transitória do `metrics-server` do cluster (mensagem "server is currently unable to handle the request"), componente de infraestrutura Kubernetes — não um bug no código do `medprev-rest-api`. Não determinei a causa raiz do `metrics-server` em si (saúde/recursos do próprio componente não foram consultados por estarem fora do escopo de dados deste achado).

### Linha do tempo
1. 00:22:51 09/09/2026 BRT (epoch 1788924171000 · 2026-09-09T03:22:51.000Z) — Início do episódio: 4 HPAs reportam `FailedGetResourceMetric` (CPU e memória), causa "server is currently unable to handle the request".
2. 00:23:06 09/09/2026 BRT (epoch 1788924186000 · 2026-09-09T03:23:06.000Z)–00:33:23 09/09/2026 BRT (epoch 1788924803000 · 2026-09-09T03:33:23.000Z) — Repetição do mesmo erro a cada ~15s nos 4 HPAs.
3. 00:23:21 09/09/2026 BRT (epoch 1788924201000 · 2026-09-09T03:23:21.000Z) — Mensagem muda para "no metrics returned from resource metrics API".
4. 00:30:23 09/09/2026 BRT (epoch 1788924623000 · 2026-09-09T03:30:23.000Z)–00:30:53 09/09/2026 BRT (epoch 1788924653000 · 2026-09-09T03:30:53.000Z) — HPA `-gama` isoladamente reporta "did not receive metrics for targeted pods (pods might be unready)", possível rollout concorrente.
5. 00:33:08 09/09/2026 BRT (epoch 1788924788000 · 2026-09-09T03:33:08.000Z)–00:33:38 09/09/2026 BRT (epoch 1788924818000 · 2026-09-09T03:33:38.000Z) — Volta ao padrão "server unable to handle the request"; consulta cortada aqui (24 de 78 eventos revisados).
6. `first_seen` do achado: 00:34:53 09/09/2026 BRT (epoch 1788924893000 · 2026-09-09T03:34:53.000Z); `last_seen`: 21:27:38 10/09/2026 BRT (epoch 1789086458000 · 2026-09-11T00:27:38.000Z) — indica recorrência não detalhada aqui.

### Evidências
- [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20FailedGetResourceMetric&from_ts=1788808256645&to_ts=1789153856645&live=false) — 78 eventos na janela.
- `aggregate_spans` `service:medprev-rest-api env:production status:error`, 00:15:00 09/09/2026 BRT (epoch 1788923700000 · 2026-09-09T03:15:00.000Z)–00:45:00 09/09/2026 BRT (epoch 1788925500000 · 2026-09-09T03:45:00.000Z) — 0 spans de erro.
- `search_datadog_logs` `service:medprev-rest-api env:production status:error`, mesma janela — 40 logs (não causalmente ligados ao evento de métricas).

### Ação recomendada
Infra — sem repositório de código específico da aplicação a alterar; ação operacional no cluster `eks-medprev-online-prd`: revisar `resources`/réplicas do Deployment `metrics-server` (namespace `kube-system`) e checar eventos de `OOMKilled`/restart do próprio `metrics-server` no horário 00:22:51 09/09/2026 BRT (epoch 1788924171000 · 2026-09-09T03:22:51.000Z)–00:33:38 09/09/2026 BRT (epoch 1788924818000 · 2026-09-09T03:33:38.000Z). Validar a correção monitorando a mesma query de eventos (`source:kubernetes env:production status:warn kube_namespace:medprev-rest-api FailedGetResourceMetric`) e confirmando ausência de novas ocorrências por pelo menos um ciclo de 96h.

### Volume
3 ocorrências entre 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) e 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z) (`observed_count` do achado); minha própria consulta idêntica, mesma janela, retornou 78 eventos brutos do Datadog — divergência provavelmente explicada pela granularidade de fingerprint por namespace do coletor (agrega múltiplos eventos brutos por rodada), não por erro na contagem.

### Severidade e criticidade
`severity: medium` no achado, mas essa severidade não se aplica ao erro em si, já classificado como ruído (0 impacto observado na aplicação). Criticidade real (inferência): baixa a moderada — o HPA ficou sem recalcular réplicas por ~11 minutos, o que só teria impacto se houvesse pico de carga simultâneo (não observado, 0 spans de erro na janela); o achado correlacionado mais relevante — os 40 logs de erro com timeout de SDK AWS a 1000ms — não foi confirmado como causalmente ligado e merece investigação própria separada se recorrente.
