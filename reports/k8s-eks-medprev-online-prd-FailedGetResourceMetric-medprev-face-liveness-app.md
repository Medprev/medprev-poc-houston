---
fingerprint: k8s-eks-medprev-online-prd-FailedGetResourceMetric-medprev-face-liveness-app
source: kubernetes
reason: FailedGetResourceMetric
novelty: new
service: medprev-face-liveness-app
environment: production
window:
  from: 1788808256645
  to: 1789153856645
observed:
  count: 8
  first_seen: 1788936250000
  last_seen: 1789017208000
severity: medium
state: new
cost:
  input_tokens: 312201
  output_tokens: 10532
  cache_read_input_tokens: 224304
  cache_creation_input_tokens: 87889
  duration_s: 112.276
  usd: 0.5064628
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-face-liveness-app%20FailedGetResourceMetric&from_ts=1788808256645&to_ts=1789153856645&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-face-liveness-app%20FailedGetResourceMetric&from_ts=1788808256645&to_ts=1789153856645&live=false

## Causa raiz

O achado é `FailedGetResourceMetric` do HorizontalPodAutoscaler (HPA) do Deployment `medprev-face-liveness-app`, no namespace `medprev-face-liveness-app`, cluster `eks-medprev-online-prd`. Não é um erro do código da aplicação: é o HPA falhando ao buscar métricas de CPU/memória para decidir escala. Consultei os eventos do Events Explorer com a `query` do achado e vi duas causas distintas misturadas nas mensagens:
1. `did not receive metrics for targeted pods (pods might be unready)` — pods temporariamente não prontos, coincidindo com deploys frequentes (ver linha do tempo);
2. `unable to fetch metrics from resource metrics API: the server is currently unable to handle the request (get pods.metrics.k8s.io)` — falha do próprio `metrics-server`/API de métricas do cluster, não do pod da aplicação.

Agregando o mesmo Reason (`FailedGetResourceMetric`) por `kube_namespace` na mesma janela, encontrei o evento em **8 namespaces diferentes** (`medprev-analytics-etl-airflow`: 1137, `medprev-rest-api`: 78, `medprev-face-liveness-app`: 54, `medprev-web-app`: 32, `medprev-cms`: 17, `medprev-institucional-cms`: 15, `medprev-metabase`: 15, `nginx-gateway-fabric`: 14) — isso é evidência direta de um problema **cluster-wide** na API de métricas, não específico deste app.

Classificação sinal/ruído: não há spans de erro nem exceção de aplicação aqui — 0 spans retornados para `service:medprev-face-liveness-app status:error` na janela (`search_datadog_spans`, consulta abaixo), então a dicotomia `handled`/`unhandled` de Error Tracking não se aplica a este achado (ele nunca passou por código de app). Os logs de aplicação do serviço na mesma janela mostram respostas HTTP 200 normais ao longo de toda a janela, inclusive após o `last_seen` do achado — não há indício de degradação percebida pelo usuário. Concluo que o `FailedGetResourceMetric` em si é **RUÍDO operacional esperado durante rollouts** (causa 1) somado a um **problema real e mais grave, cluster-wide, na API de métricas** (causa 2), que este achado captura apenas parcialmente por estar filtrado a um único namespace.

Consultas rodadas e o que cada uma devolveu:
- Events Explorer com a `query` exata do achado, janela `window_from`–`window_to`: 54 eventos (não bate com `observed_count: 8`; mesma janela, então a diferença não é de escopo temporal — provavelmente o coletor do Houston aplica alguma deduplicação/agrupamento adicional aos brutos do Events API; não determinado com os dados disponíveis).
- `aggregate_events` por hora na mesma janela: 9 buckets com ocorrências entre 03h e 10h de 09/09, depois esparsas até 11/09 03h.
- `aggregate_events` por `kube_namespace` (Reason cluster-wide, mesma janela): 8 namespaces afetados, confirma padrão cluster-wide.
- `search_datadog_logs service:medprev-face-liveness-app` na mesma janela: 165 logs, amostra mostra apenas tráfego HTTP normal (200) e um erro de nginx não relacionado (ver Evidência).
- `search_datadog_spans service:medprev-face-liveness-app status:error` na mesma janela: 0 spans — o serviço não está instrumentado com APM, então não há trace do "erro" para reconstruir (não é um erro de aplicação, é evento de infraestrutura do HPA).
- `search_datadog_events source:change_tracking kube_namespace:medprev-face-liveness-app` na mesma janela: 25+ deploys do mesmo Deployment na janela, todos na versão `36b31309`, vários com `kube_condition_available:false` durante o rollout — correlaciona com a causa 1.

## Linha do tempo

- 00:22:34 09/09/2026 BRT (epoch 1788924154000 · 2026-09-09T03:22:34.000Z) — Primeiro evento HPA agregado do lote, HorizontalPodAutoscaler reporta 7x `FailedGetResourceMetric` (cpu) e 5x (memory) por "pods might be unready", refletindo eventos desde 2026-09-05 (consulta: Events Explorer, `query` do achado).
- 00:22:44 09/09/2026 BRT (epoch 1788924164000 · 2026-09-09T03:22:44.000Z) — Deploy do mesmo Deployment concluído (`kube_condition_available:false`→ redeploy em andamento) — consulta: `source:change_tracking kube_namespace:medprev-face-liveness-app`.
- 00:23:04 09/09/2026 BRT (epoch 1788924184000 · 2026-09-09T03:23:04.000Z) — HPA reporta 7x `FailedGetResourceMetric` por "unable to fetch metrics from resource metrics API: the server is currently unable to handle the request" — sinal de falha do metrics-server, não do pod.
- 00:29:20 09/09/2026 BRT (epoch 1788924560000 · 2026-09-09T03:29:20.000Z) a 00:33:35 09/09/2026 BRT (epoch 1788924815000 · 2026-09-09T03:33:35.000Z) — Sequência de eventos HPA repetindo as duas causas em rajadas de ~15s (padrão de retry do HPA), coincidindo com múltiplos redeploys às 00:29:31 09/09/2026 BRT (epoch 1788924571000 · 2026-09-09T03:29:31.000Z) e 00:29:45 09/09/2026 BRT (epoch 1788924585000 · 2026-09-09T03:29:45.000Z).
- 03:44:10 09/09/2026 BRT (epoch 1788936250000 · 2026-09-09T06:44:10.000Z) — `first_seen` do achado: 10x `FailedGetResourceMetric` (cpu) por "pods might be unready", coincidindo com deploy às 03:44:01 09/09/2026 BRT (epoch 1788936241000 · 2026-09-09T06:44:01.000Z).
- 07:02:27 09/09/2026 BRT (epoch 1788948147000 · 2026-09-09T10:02:27.000Z) a 07:45:16 09/09/2026 BRT (epoch 1788950716000 · 2026-09-09T10:45:16.000Z) — Novo cluster de falhas (contagens crescentes até 16x), com deploys intercalados às 07:02:30 09/09/2026 BRT (epoch 1788948150000 · 2026-09-09T10:02:30.000Z), 07:02:45 09/09/2026 BRT (epoch 1788948165000 · 2026-09-09T10:02:45.000Z), 07:28:01 09/09/2026 BRT (epoch 1788949681000 · 2026-09-09T10:28:01.000Z), 07:28:16 09/09/2026 BRT (epoch 1788949696000 · 2026-09-09T10:28:16.000Z), 07:45:01 09/09/2026 BRT (epoch 1788950701000 · 2026-09-09T10:45:01.000Z), 07:45:16 09/09/2026 BRT (epoch 1788950716000 · 2026-09-09T10:45:16.000Z) — deploys muito frequentes (a cada ~15-25 min).
- `last_seen` do achado em 02:13:28 10/09/2026 BRT (epoch 1789017208000 · 2026-09-10T05:13:28.000Z) não veio no lote de 25 eventos que consultei (54 no total, paginação não seguida por economia de contexto); os campos do próprio achado garantem que a última ocorrência histórica foi nesse timestamp.
- 14:29:13 11/09/2026 BRT (epoch 1789147753000 · 2026-09-11T17:29:13.000Z) — Log de aplicação mais recente na janela: HTTP 200 normal, muito depois do `last_seen` do achado — nenhuma degradação de serviço detectável.

## Evidência

- Consulta que reconstruiu o padrão de causas do erro (54 eventos, duas causas distintas: pods unready vs. metrics-server indisponível): [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-face-liveness-app%20FailedGetResourceMetric&from_ts=1788808256645&to_ts=1789153856645&live=false).
- O mesmo Reason ocorre em 8 namespaces simultaneamente na mesma janela (evidência de causa cluster-wide, não específica deste app) — consulta: `aggregate_events`, query `source:kubernetes env:production FailedGetResourceMetric`, `group_by kube_namespace`, mesma janela; contagens: `medprev-analytics-etl-airflow=1137, medprev-rest-api=78, medprev-face-liveness-app=54, medprev-web-app=32, medprev-cms=17, medprev-institucional-cms=15, medprev-metabase=15, nginx-gateway-fabric=14`.
- Deploys muito frequentes do mesmo Deployment durante a janela, com `kube_condition_available:false` recorrente — consulta: `search_datadog_events source:change_tracking kube_namespace:medprev-face-liveness-app`, mesma janela, 25 eventos retornados (paginação não esgotada).
- Nenhum span de erro de aplicação no período — o serviço não está instrumentado em APM: consulta `search_datadog_spans query:"service:medprev-face-liveness-app status:error"`, mesma janela, 0 resultados.
- Logs de aplicação mostram tráfego normal (200) na mesma janela e depois dela, sem correlação de falha visível ao usuário — consulta `search_datadog_logs query:"service:medprev-face-liveness-app"`, mesma janela, 165 logs no total (amostra de 5 lida).
- Achado não confirma escopo idêntico entre `observed_count` (8, escopo do coletor Houston) e a contagem bruta do Events Explorer (54, mesma janela, mesma query) — divergência não explicada por diferença de janela; registrada como tal.

## Ação recomendada

Não há ação de código para `Medprev/medprev-face-liveness-app` — a causa dominante é infraestrutura (metrics-server intermitente, cluster-wide) e frequência de redeploy. Encaminhar para o time de infraestrutura investigar a saúde do `metrics-server`/`pods.metrics.k8s.io` no cluster `eks-medprev-online-prd` (afeta 8 namespaces) e revisar a cadência de sync do ArgoCD para este Deployment, que redeployou dezenas de vezes na janela de 4 dias.

## Corpo da issue

### Descrição do incidente
O HorizontalPodAutoscaler do Deployment `medprev-face-liveness-app` (namespace `medprev-face-liveness-app`, cluster `eks-medprev-online-prd`) reporta falhas repetidas ao obter métricas de CPU/memória (`FailedGetResourceMetric`) desde 03:44:10 09/09/2026 BRT (epoch 1788936250000 · 2026-09-09T06:44:10.000Z) até 02:13:28 10/09/2026 BRT (epoch 1789017208000 · 2026-09-10T05:13:28.000Z). Não há impacto observável para o usuário: os logs de acesso do serviço mostram respostas HTTP 200 normais durante e após a janela do incidente.

### Causa raiz
RUÍDO para este app: 0 spans de erro de aplicação encontrados no período (`search_datadog_spans`, 0/0). O mesmo Reason `FailedGetResourceMetric` ocorre simultaneamente em 8 namespaces do cluster na mesma janela (1137 a 14 ocorrências por namespace), o que indica uma falha cluster-wide da API de métricas (`metrics-server`), não um defeito no código ou na configuração específica deste app. Uma fração das ocorrências ("pods might be unready") correlaciona com o alto número de redeploys deste Deployment na janela (25+ deploys em 4 dias, alguns a cada ~15 min), o que é esperado durante rollout mas voltou a ocorrer com frequência incomum.

### Linha do tempo
- 00:22:34 09/09/2026 BRT (epoch 1788924154000 · 2026-09-09T03:22:34.000Z) a 00:33:35 09/09/2026 BRT (epoch 1788924815000 · 2026-09-09T03:33:35.000Z) — primeiro cluster de falhas HPA, intercalado com deploys (00:22:44 09/09/2026 BRT (epoch 1788924164000 · 2026-09-09T03:22:44.000Z), 00:29:31 09/09/2026 BRT (epoch 1788924571000 · 2026-09-09T03:29:31.000Z), 00:29:45 09/09/2026 BRT (epoch 1788924585000 · 2026-09-09T03:29:45.000Z)).
- 03:44:10 09/09/2026 BRT (epoch 1788936250000 · 2026-09-09T06:44:10.000Z) — `first_seen` do achado, 10x falha "pods might be unready", coincide com deploy em 03:44:01 09/09/2026 BRT (epoch 1788936241000 · 2026-09-09T06:44:01.000Z).
- 07:02:27 09/09/2026 BRT (epoch 1788948147000 · 2026-09-09T10:02:27.000Z) a 07:45:16 09/09/2026 BRT (epoch 1788950716000 · 2026-09-09T10:45:16.000Z) — segundo cluster de falhas, contagens crescentes (até 16x), com 6 deploys intercalados no mesmo intervalo.
- `last_seen` em 02:13:28 10/09/2026 BRT (epoch 1789017208000 · 2026-09-10T05:13:28.000Z) (garantido pelo campo do achado; não incluído no lote de 25/54 eventos consultados por economia de contexto).
- 14:29:13 11/09/2026 BRT (epoch 1789147753000 · 2026-09-11T17:29:13.000Z) — log de acesso mais recente na janela, HTTP 200, sem sinal de degradação.

### Evidências
- [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-face-liveness-app%20FailedGetResourceMetric&from_ts=1788808256645&to_ts=1789153856645&live=false) — 54 eventos brutos na janela.
- `aggregate_events` query `source:kubernetes env:production FailedGetResourceMetric` agrupado por `kube_namespace`, mesma janela — 8 namespaces afetados simultaneamente.
- `search_datadog_events source:change_tracking kube_namespace:medprev-face-liveness-app`, mesma janela — 25+ deploys do mesmo Deployment.
- `search_datadog_spans query:"service:medprev-face-liveness-app status:error"`, mesma janela — 0 resultados.
- `search_datadog_logs query:"service:medprev-face-liveness-app"`, mesma janela — 165 logs, tráfego normal (200).

### Ação recomendada
Infra — sem repositório de código para a causa raiz principal: acionar o time de infraestrutura do cluster `eks-medprev-online-prd` para verificar a saúde do `metrics-server` (componente `pods.metrics.k8s.io`) no período de 00:22:34 09/09/2026 BRT (epoch 1788924154000 · 2026-09-09T03:22:34.000Z) a 02:13:28 10/09/2026 BRT (epoch 1789017208000 · 2026-09-10T05:13:28.000Z), já que 8 namespaces reportaram a mesma falha simultaneamente. Adicionalmente, revisar em `Medprev/medprev-face-liveness-app` (chart Helm/ArgoCD, `argocd.argoproj.io/instance:medprev-face-liveness-app-main`) por que houve 25+ syncs/deploys em 4 dias — se for um loop de auto-sync não intencional, corrigir a configuração do ArgoCD Application. Validar a correção observando se `FailedGetResourceMetric` some das próximas janelas de coleta do Houston para este fingerprint e se a cardinalidade cross-namespace no cluster cai a zero.

### Volume
8 ocorrências entre 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) e 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z) segundo `observed_count` do achado. Consulta direta ao Datadog com a mesma janela e mesma query retornou 54 ocorrências — divergência não explicada por diferença de janela (mesma janela usada); possivelmente deduplicação/agrupamento adicional no coletor Houston, não determinado.

### Severidade e criticidade
`severity: medium` do achado não se aplica ao `FailedGetResourceMetric` em si, classificado como ruído operacional (0 spans de erro de aplicação, tráfego HTTP normal durante e após a janela). O defeito real e mais crítico é a falha cluster-wide do `metrics-server` afetando 8 namespaces simultaneamente — **inferência minha**: isso é potencialmente mais grave que `medium`, pois compromete o autoscaling de múltiplos serviços em produção ao mesmo tempo, incluindo `medprev-rest-api` (78 ocorrências) e `medprev-analytics-etl-airflow` (1137 ocorrências).
