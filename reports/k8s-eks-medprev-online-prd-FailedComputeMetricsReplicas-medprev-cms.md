---
fingerprint: k8s-eks-medprev-online-prd-FailedComputeMetricsReplicas-medprev-cms
source: kubernetes
reason: FailedComputeMetricsReplicas
novelty: new
service: medprev-cms
environment: production
window:
  from: 1788808256645
  to: 1789153856645
observed:
  count: 17
  first_seen: 1788924171000
  last_seen: 1789086458000
severity: medium
state: new
cost:
  input_tokens: 464207
  output_tokens: 10291
  cache_read_input_tokens: 370988
  cache_creation_input_tokens: 93209
  duration_s: 104.691
  usd: 0.5546686000000001
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-cms%20FailedComputeMetricsReplicas&from_ts=1788808256645&to_ts=1789153856645&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-cms%20FailedComputeMetricsReplicas&from_ts=1788808256645&to_ts=1789153856645&live=false

## Causa raiz

O achado é do namespace `medprev-cms` no cluster `eks-medprev-online-prd`, evento `FailedComputeMetricsReplicas` emitido pelo HorizontalPodAutoscaler (HPA) `medprev-cms/medprev-cms`: o HPA falhou repetidamente ao coletar métricas de CPU/memória via `pods.metrics.k8s.io`, ora com "the server is currently unable to handle the request" (503 da Metrics API), ora com "no metrics returned from resource metrics API".

Isto é **ruído no nível do achado individual, mas sinal real no nível do cluster**: agregando o mesmo Reason (`FailedComputeMetricsReplicas`, `status:warn`) por `kube_namespace` na mesma janela do achado, encontrei **219 ocorrências em 8 namespaces** — `medprev-rest-api` (75), `medprev-face-liveness-app` (46), `medprev-web-app` (32), `medprev-cms` (17, o achado em análise), `medprev-institucional-cms` (14), `medprev-metabase` (14), `nginx-gateway-fabric` (14), `medprev-analytics-etl-airflow` (7). O problema não é do código ou da carga de `medprev-cms`: é uma degradação intermitente do pipeline de métricas do cluster (Metrics API/metrics-server) que afeta todos os HPAs simultaneamente. Confirmando que é transitório e auto-recuperável: em cada rajada de falhas do dia 09/09, o HPA de `medprev-cms` conseguiu completar um `SuccessfulRescale` minutos depois (ex.: rajada às 00:22:51 09/09/2026 BRT (epoch 1788924171000 · 2026-09-09T03:22:51.000Z)–00:33:38 09/09/2026 BRT (epoch 1788924818000 · 2026-09-09T03:33:38.000Z), seguida de rescale bem-sucedido em 00:34:53 09/09/2026 BRT (epoch 1788924893000 · 2026-09-09T03:34:53.000Z)).

Não determinei a causa raiz da instabilidade da própria Metrics API: busquei eventos de instabilidade do pod `metrics-server` (`BackOff`, `Unhealthy`, `Killing`, `FailedScheduling`, `NodeNotReady`) no namespace `kube-system` na mesma janela e a consulta **voltou vazia** — ou seja, não há evento de restart/crash do pod do metrics-server registrado no Datadog para essa janela, o que aponta mais para throttling/latência da API server-side do que para uma falha de pod, mas isso não está confirmado pelas evidências consultadas.

## Linha do tempo

- 00:22:51 09/09/2026 BRT (epoch 1788924171000 · 2026-09-09T03:22:51.000Z) — 1ª falha da rajada: `FailedComputeMetricsReplicas` (503 da Metrics API), medprev-cms.
- 00:23:06 09/09/2026 BRT (epoch 1788924186000 · 2026-09-09T03:23:06.000Z) — 2ª falha, mesma causa (503), 15s depois.
- 00:23:22 09/09/2026 BRT (epoch 1788924202000 · 2026-09-09T03:23:22.000Z) — 3ª falha, variante "no metrics returned".
- 00:33:08 09/09/2026 BRT (epoch 1788924788000 · 2026-09-09T03:33:08.000Z) — 4ª falha (503).
- 00:33:23 09/09/2026 BRT (epoch 1788924803000 · 2026-09-09T03:33:23.000Z) — 5ª falha (503).
- 00:33:38 09/09/2026 BRT (epoch 1788924818000 · 2026-09-09T03:33:38.000Z) — 6ª falha ("no metrics returned").
- 00:34:53 09/09/2026 BRT (epoch 1788924893000 · 2026-09-09T03:34:53.000Z) — HPA recupera: `SuccessfulRescale` para tamanho 3 (CPU acima do alvo) — confirma que a Metrics API voltou a responder.
- 00:44:10 09/09/2026 BRT (epoch 1788925450000 · 2026-09-09T03:44:10.000Z) — `SuccessfulRescale` para tamanho 2 (métricas abaixo do alvo) — ciclo normal de scale-down.
- 03:45:36 09/09/2026 BRT (epoch 1788936336000 · 2026-09-09T06:45:36.000Z) — nova rajada: falha (503).
- 03:45:52 09/09/2026 BRT (epoch 1788936352000 · 2026-09-09T06:45:52.000Z) — falha ("no metrics returned").
- 07:35:49 09/09/2026 BRT (epoch 1788950149000 · 2026-09-09T10:35:49.000Z) — falha (503).
- 07:36:04 09/09/2026 BRT (epoch 1788950164000 · 2026-09-09T10:36:04.000Z) — falha (503).
- 07:36:19 09/09/2026 BRT (epoch 1788950179000 · 2026-09-09T10:36:19.000Z) — falha ("no metrics returned").
- 07:54:36 09/09/2026 BRT (epoch 1788951276000 · 2026-09-09T10:54:36.000Z) — falha (503).
- 07:54:51 09/09/2026 BRT (epoch 1788951291000 · 2026-09-09T10:54:51.000Z) — falha (503).
- 07:55:06 09/09/2026 BRT (epoch 1788951306000 · 2026-09-09T10:55:06.000Z) — falha ("no metrics returned").
- 21:27:08 10/09/2026 BRT (epoch 1789086428000 · 2026-09-11T00:27:08.000Z) — falha (503), início da última rajada dentro da janela.
- 21:27:23 10/09/2026 BRT (epoch 1789086443000 · 2026-09-11T00:27:23.000Z) — falha (503).
- 21:27:38 10/09/2026 BRT (epoch 1789086458000 · 2026-09-11T00:27:38.000Z) — falha ("no metrics returned") — coincide com `last_seen` do achado: 21:27:38 10/09/2026 BRT (epoch 1789086458000 · 2026-09-11T00:27:38.000Z).

## Evidência

- 17 ocorrências de `FailedComputeMetricsReplicas` em `medprev-cms` dentro da janela `window_from`–`window_to` do achado: [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-cms%20FailedComputeMetricsReplicas&from_ts=1788808256645&to_ts=1789153856645&live=false).
- Confirmação de que o mesmo Reason ocorre em 8 namespaces do cluster na mesma janela (219 eventos no total, 17 de `medprev-cms`): consulta `aggregate_events` com `source:kubernetes status:warn FailedComputeMetricsReplicas kube_cluster_name:eks-medprev-online-prd`, agrupada por `kube_namespace`, de `1788808256645` a `1789153856645` — sem link de evidência pronto para esta consulta agregada, pois não há um `evidence_link` correspondente no achado.
- Confirmação de que o HPA se recupera sozinho: eventos `SuccessfulRescale` de `medprev-cms/medprev-cms` minutos após cada rajada de falha — consulta `search_datadog_events` com `source:kubernetes kube_namespace:medprev-cms (Reason:ScalingReplicaSet OR Reason:FailedGetResourceMetric OR HorizontalPodAutoscaler)`, mesma janela, 25 eventos retornados.
- Ausência de evento de instabilidade do pod `metrics-server` em `kube-system` na mesma janela: consulta `source:kubernetes kube_namespace:kube-system (metrics-server) (Reason:BackOff OR Reason:Unhealthy OR Reason:Killing OR Reason:Started OR Reason:FailedScheduling OR Reason:NodeNotReady)` — **0 resultados**.

## Ação recomendada

Não abrir/tratar isto como bug de `medprev-cms`: consolidar como um único problema de infraestrutura (degradação intermitente da Metrics API/metrics-server do cluster `eks-medprev-online-prd`) e investigar capacidade/throttling do metrics-server ou da API Priority & Fairness do control plane do EKS, em vez de repetir a investigação por namespace.

## Corpo da issue

### Descrição do incidente
O HPA do namespace `medprev-cms` no cluster `eks-medprev-online-prd` falhou repetidamente ao calcular réplicas por indisponibilidade intermitente da Metrics API (`pods.metrics.k8s.io`), com 17 ocorrências entre 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) e 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z). O mesmo problema ocorreu simultaneamente em 8 namespaces do cluster (219 ocorrências no total), indicando causa compartilhada de infraestrutura, não de `medprev-cms`. Impacto observável: nenhum, no sentido de indisponibilidade — o HPA sempre conseguiu completar um rescale minutos depois de cada rajada de falhas.

### Causa raiz
**Ruído no nível deste achado** (0 de 17 ocorrências representam falha real de scaling — todas foram seguidas de `SuccessfulRescale`), mas **sinal real no nível do cluster**: 219 ocorrências do mesmo Reason em 8 namespaces na mesma janela apontam para degradação compartilhada da Metrics API/metrics-server. Causa raiz da própria degradação: não determinada — não há evento de restart/unhealthy do pod `metrics-server` em `kube-system` na janela investigada (consulta retornou vazia), o que sugere throttling ou latência do control plane em vez de crash de pod, mas isso é inferência, não evidência direta.

### Linha do tempo
- 00:22:51 09/09/2026 BRT (epoch 1788924171000 · 2026-09-09T03:22:51.000Z) a 00:23:22 09/09/2026 BRT (epoch 1788924202000 · 2026-09-09T03:23:22.000Z): 1ª rajada de falhas (503 / "no metrics returned").
- 00:33:08 09/09/2026 BRT (epoch 1788924788000 · 2026-09-09T03:33:08.000Z) a 00:33:38 09/09/2026 BRT (epoch 1788924818000 · 2026-09-09T03:33:38.000Z): 2ª rajada.
- 00:34:53 09/09/2026 BRT (epoch 1788924893000 · 2026-09-09T03:34:53.000Z): `SuccessfulRescale` (tamanho 3) — recuperação confirmada.
- 00:44:10 09/09/2026 BRT (epoch 1788925450000 · 2026-09-09T03:44:10.000Z): `SuccessfulRescale` (tamanho 2) — ciclo normal.
- 03:45:36 09/09/2026 BRT (epoch 1788936336000 · 2026-09-09T06:45:36.000Z) a 03:45:52 09/09/2026 BRT (epoch 1788936352000 · 2026-09-09T06:45:52.000Z): 3ª rajada.
- 07:35:49 09/09/2026 BRT (epoch 1788950149000 · 2026-09-09T10:35:49.000Z) a 07:36:19 09/09/2026 BRT (epoch 1788950179000 · 2026-09-09T10:36:19.000Z): 4ª rajada.
- 07:54:36 09/09/2026 BRT (epoch 1788951276000 · 2026-09-09T10:54:36.000Z) a 07:55:06 09/09/2026 BRT (epoch 1788951306000 · 2026-09-09T10:55:06.000Z): 5ª rajada.
- 21:27:08 10/09/2026 BRT (epoch 1789086428000 · 2026-09-11T00:27:08.000Z) a 21:27:38 10/09/2026 BRT (epoch 1789086458000 · 2026-09-11T00:27:38.000Z): 6ª e última rajada dentro da janela (coincide com `last_seen` do achado).
- Correlação: as mesmas rajadas de horário (madrugada de 09/09 e 11/09) aparecem no mesmo Reason em `medprev-rest-api`, `medprev-face-liveness-app`, `medprev-web-app`, `medprev-institucional-cms`, `medprev-metabase`, `nginx-gateway-fabric` e `medprev-analytics-etl-airflow` — indício forte de causa compartilhada de cluster, não de aplicação.

### Evidências
- [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-cms%20FailedComputeMetricsReplicas&from_ts=1788808256645&to_ts=1789153856645&live=false)
- Consulta `aggregate_events`: `source:kubernetes status:warn FailedComputeMetricsReplicas kube_cluster_name:eks-medprev-online-prd`, agrupada por `kube_namespace`, `1788808256645`–`1789153856645` → 219 eventos em 8 namespaces.
- Consulta `search_datadog_events`: `source:kubernetes kube_namespace:medprev-cms (Reason:ScalingReplicaSet OR Reason:FailedGetResourceMetric OR HorizontalPodAutoscaler)`, mesma janela → 25 eventos, incluindo `SuccessfulRescale` correlacionados.
- Consulta `search_datadog_events`: `source:kubernetes kube_namespace:kube-system (metrics-server) (Reason:BackOff OR Reason:Unhealthy OR Reason:Killing OR Reason:Started OR Reason:FailedScheduling OR Reason:NodeNotReady)`, mesma janela → 0 eventos.

### Ação recomendada
`target_repo` do achado é `Medprev/medprev-cms`, mas a causa está fora desse repositório: nenhuma mudança de código ou manifesto de `medprev-cms` resolve isto, pois o mesmo Reason atinge 8 namespaces simultaneamente. Ação: abrir/atualizar um item único de infraestrutura (não por namespace) para o time responsável pelo cluster `eks-medprev-online-prd`, cobrindo: (1) verificar métricas de latência/erro do add-on `metrics-server` (CPU/memória do pod, réplicas, HPA do próprio metrics-server) durante as janelas listadas na linha do tempo; (2) verificar throttling da API Priority & Fairness do control plane EKS nesses horários; (3) considerar aumentar réplicas/recursos do `metrics-server` ou ajustar `--metric-resolution` se a causa for capacidade. Validação: após a mudança, confirmar por 7 dias que `FailedComputeMetricsReplicas` não reaparece agregado por `kube_cluster_name:eks-medprev-online-prd` (consulta usada nesta investigação).

### Volume
17 ocorrências entre 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) e 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z), conforme `observed_count` do achado. Consulta adicional no Datadog (mesma janela, mesmo Reason, sem filtro de namespace, agrupada por `kube_namespace`) retornou 219 ocorrências no cluster inteiro — mesma janela, escopo mais amplo.

### Severidade e criticidade
`severity: medium` do achado não se aplica ao evento em si, já que ele é ruído (autorrecuperável, sem falha real de scaling em `medprev-cms`). O defeito real — degradação intermitente da Metrics API do cluster — tem criticidade potencialmente maior que o achado original **(inferência)**: se a degradação se agravar, o autoscaling de 8 serviços de produção simultaneamente pode ficar comprometido, incluindo serviços voltados ao usuário final (`medprev-rest-api`, `medprev-web-app`, `medprev-face-liveness-app`).
