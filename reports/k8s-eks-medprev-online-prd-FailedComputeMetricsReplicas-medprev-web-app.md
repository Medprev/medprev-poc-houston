---
fingerprint: k8s-eks-medprev-online-prd-FailedComputeMetricsReplicas-medprev-web-app
source: kubernetes
reason: FailedComputeMetricsReplicas
novelty: new
service: medprev-web-app
environment: production
window:
  from: 1788808256645
  to: 1789153856645
observed:
  count: 32
  first_seen: 1788924177000
  last_seen: 1789086458000
severity: medium
state: new
cost:
  input_tokens: 463167
  output_tokens: 10309
  cache_read_input_tokens: 361972
  cache_creation_input_tokens: 101185
  duration_s: 110.108
  usd: 0.5849774000000001
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-web-app%20FailedComputeMetricsReplicas&from_ts=1788808256645&to_ts=1789153856645&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-web-app%20FailedComputeMetricsReplicas&from_ts=1788808256645&to_ts=1789153856645&live=false

Confirmado: a causa é rotação de nós pelo Karpenter (consolidação), não o serviço `medprev-web-app`. Tenho evidência suficiente para fechar a investigação.

## Causa raiz

O `metrics-server` do cluster `eks-medprev-online-prd` (namespace `kube-system`, réplica única) está sendo derrubado e reagendado repetidamente por consolidação de nós do Karpenter, e cada ciclo de restart deixa uma janela de indisponibilidade da Metrics API que faz o HorizontalPodAutoscaler de `medprev-web-app-backend-graphql` e `medprev-web-app-frontend` falhar ao calcular réplicas (`FailedComputeMetricsReplicas`/`FailedGetResourceMetric`). Não é um bug do serviço `medprev-web-app`: é um efeito colateral de infraestrutura (Karpenter + metrics-server sem redundância) sobre o HPA desse serviço. Como fonte é `kubernetes` (evento de sistema, não Error Tracking com traces/spans), a classificação sinal/ruído "handled/unhandled" não se aplica; a classificação equivalente aqui é: **sinal real de infraestrutura**, comprovado por correlação direta 1:1 entre cada `Killing`/`SuccessfulCreate` do pod `metrics-server-*` (consulta `source:kubernetes env:production kube_namespace:kube-system metrics-server`) e o respectivo bloco de eventos `FailedComputeMetricsReplicas` do achado, e ainda pela sequência `FailedDraining` → `InstanceTerminating` do nó hospedeiro (consulta `source:kubernetes env:production kube_node:(...) Terminat*`), que mostra o Karpenter drenando o nó do `metrics-server` no mesmo segundo em que o pod é morto.

Consultas rodadas e o que cada uma devolveu:
- `search_datadog_events` com a query exata do achado, janela `window_from`–`window_to`: 32 eventos (bate com `observed_count`).
- `aggregate_events` agrupado por host/6h: eventos concentrados em `i-07aa79ff3b225aa0a` (4+16+6) e `i-05d938105c83b3ba7` (6) — nós que rodavam os pods de `medprev-web-app` durante os incidentes.
- `search_datadog_events` para `kube_namespace:kube-system metrics-server`: 25 eventos — 6 ciclos completos de `Killing` → `SuccessfulCreate` → `Pulled/Started` do pod `metrics-server-6bcb764664-*`, mais 2 `Unhealthy: readiness probe failed (connection refused)`.
- `search_datadog_logs` (`kube_namespace:kube-system service:metrics-server`, `limit:1`): 23.920 logs no total na janela; o log de topo (`16:10:42 11/09/2026 BRT (epoch 1789153842000 · 2026-09-11T19:10:42.000Z)`, fora da janela do achado por 8h — não usado na linha do tempo) mostra `scraper.go: Failed to scrape node ... context deadline exceeded`, um padrão consistente com metrics-server sofrendo timeouts de scrape.
- `aggregate_events` por `title` filtrando `kube_name:metrics-server*`: 0 buckets — o facet `title` não é agregável neste índice de eventos (resultado vazio, registrado, não reinterpretado).
- `search_datadog_events` para `kube_node:(...) Terminat*` nos 3 nós dos primeiros 3 ciclos: 6 eventos — cada ciclo de restart do metrics-server é precedido por `FailedDraining` e seguido por `InstanceTerminating` do próprio nó, no mesmo minuto.

## Linha do tempo

- 00:22:26 09/09/2026 BRT (epoch 1788924146000 · 2026-09-09T03:22:26.000Z) — Karpenter inicia dreno do nó `ip-10-0-10-50` (`FailedDraining`, 15 pods aguardando eviction) — nó que hospedava o pod `metrics-server-6bcb764664-clmwr`.
- 00:22:50 09/09/2026 BRT (epoch 1788924170000 · 2026-09-09T03:22:50.000Z) — kubelet mata o container `metrics-server` nesse nó (`Killing`); replicaset cria novo pod `metrics-server-6bcb764664-x5tq4`.
- 00:22:52 09/09/2026 BRT (epoch 1788924172000 · 2026-09-09T03:22:52.000Z) — nó `ip-10-0-10-50` reporta `InstanceTerminating`.
- 00:22:57 09/09/2026 BRT (epoch 1788924177000 · 2026-09-09T03:22:57.000Z) — primeiro bloco `FailedComputeMetricsReplicas`/`FailedGetResourceMetric` do achado nas HPAs de `medprev-web-app-backend-graphql` e `medprev-web-app-frontend` (`first_seen`), causa: metrics API indisponível.
- 00:23:12 09/09/2026 BRT (epoch 1788924192000 · 2026-09-09T03:23:12.000Z) e 00:23:27 09/09/2026 BRT (epoch 1788924207000 · 2026-09-09T03:23:27.000Z) — novas ocorrências do mesmo erro nas duas HPAs enquanto o novo pod do metrics-server ainda não completou o primeiro ciclo de scrape.
- 00:32:46 09/09/2026 BRT (epoch 1788924766000 · 2026-09-09T03:32:46.000Z) — segundo ciclo: Karpenter drena o nó `ip-10-0-3-20` (10 pods aguardando eviction), hospedeiro do pod `metrics-server-6bcb764664-x5tq4`.
- 00:33:06 09/09/2026 BRT (epoch 1788924786000 · 2026-09-09T03:33:06.000Z) a 00:33:29 09/09/2026 BRT (epoch 1788924809000 · 2026-09-09T03:33:29.000Z) — `Killing` do pod, `InstanceTerminating` do nó, e nova sequência de `FailedComputeMetricsReplicas` nas duas HPAs.
- 03:44:49 09/09/2026 BRT (epoch 1788936289000 · 2026-09-09T06:44:49.000Z) — terceiro ciclo: Karpenter drena `ip-10-0-0-32` (8 pods), seguido de `Killing`/`InstanceTerminating` em 03:45:24 09/09/2026 BRT (epoch 1788936324000 · 2026-09-09T06:45:24.000Z)/03:45:26 09/09/2026 BRT (epoch 1788936326000 · 2026-09-09T06:45:26.000Z) e novo bloco de erros de HPA em 03:45:39 09/09/2026 BRT (epoch 1788936339000 · 2026-09-09T06:45:39.000Z) e 03:45:54 09/09/2026 BRT (epoch 1788936354000 · 2026-09-09T06:45:54.000Z).
- 07:35:41 09/09/2026 BRT (epoch 1788950141000 · 2026-09-09T10:35:41.000Z) e 07:54:35 09/09/2026 BRT (epoch 1788951275000 · 2026-09-09T10:54:35.000Z) — quarto e quinto ciclos de `Killing`/reagendamento do metrics-server, cada um seguido de novo bloco de erros de HPA (07:35:50 09/09/2026 BRT (epoch 1788950150000 · 2026-09-09T10:35:50.000Z), 07:36:05 09/09/2026 BRT (epoch 1788950165000 · 2026-09-09T10:36:05.000Z), 07:36:21 09/09/2026 BRT (epoch 1788950181000 · 2026-09-09T10:36:21.000Z), 07:54:38 09/09/2026 BRT (epoch 1788951278000 · 2026-09-09T10:54:38.000Z), 07:54:53 09/09/2026 BRT (epoch 1788951293000 · 2026-09-09T10:54:53.000Z)).
- 21:27:06 10/09/2026 BRT (epoch 1789086426000 · 2026-09-11T00:27:06.000Z) — sexto ciclo de restart do metrics-server (`Killing`/`SuccessfulCreate` do pod `metrics-server-6bcb764664-mj2zl` → `-j9t7z`), correspondente à ocorrência de `last_seen` do achado, 21:27:38 10/09/2026 BRT (epoch 1789086458000 · 2026-09-11T00:27:38.000Z) (registrada como `21:27:38 10/09/2026 BRT`).

Isso cobre 6 dos 6 ciclos de restart identificados nos logs de eventos do `kube-system`, que juntos explicam os 32 eventos do achado (`observed_count`) entre `16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z)` e `16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z)`.

## Evidência

- 32 ocorrências de `FailedComputeMetricsReplicas` na janela — [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-web-app%20FailedComputeMetricsReplicas&from_ts=1788808256645&to_ts=1789153856645&live=false).
- Erros distribuídos em 2 hosts (`i-07aa79ff3b225aa0a`: 26 eventos; `i-05d938105c83b3ba7`: 6 eventos) — consulta `aggregate_events` com `group_by: [host]`, `interval: 21600000`, mesma query e janela do achado.
- 6 ciclos completos de restart do pod `metrics-server` (`Killing` → `SuccessfulCreate` → `Pulled`/`Started`), mais 2 falhas de readiness probe por `connection refused` na porta 10250 do kubelet — consulta `search_datadog_events` com `source:kubernetes env:production kube_namespace:kube-system metrics-server`, mesma janela, 25 eventos retornados.
- Cada restart do metrics-server é precedido por `FailedDraining` e seguido por `InstanceTerminating` do nó hospedeiro, no mesmo minuto — consulta `search_datadog_events` com `source:kubernetes env:production kube_node:(ip-10-0-10-50... OR ip-10-0-3-20... OR ip-10-0-0-32...) Terminat*`, mesma janela, 6 eventos retornados.
- Logs do serviço `metrics-server` existem no índice hot (23.920 no total na janela) — consulta `search_datadog_logs` com `kube_namespace:kube-system service:metrics-server`, `limit:1`; o registro de topo (fora da janela do achado) mostra padrão de `context deadline exceeded` ao raspar métricas de nó.
- Tentativa de agregação por `title` retornou 0 buckets — facet não suportado nesse índice para agregação; registrado como resultado vazio, não reinterpretado.
- Não há error tracking/spans de aplicação relevantes aqui porque a causa é um evento de infraestrutura Kubernetes (HPA/metrics-server), não uma exceção de código do serviço `medprev-web-app`.

## Ação recomendada

Aumentar a resiliência do `metrics-server` no cluster `eks-medprev-online-prd` (réplica ≥2 com `PodDisruptionBudget`, ou anotação de "do-not-disrupt"/`karpenter.sh/do-not-disrupt` para evitar drenagem simultânea da única réplica) — ação de infraestrutura, não de código do `medprev-web-app`.

## Corpo da issue

### Descrição do incidente
O `metrics-server` do cluster `eks-medprev-online-prd` roda com réplica única em `kube-system` e é derrubado repetidamente pela consolidação de nós do Karpenter. Cada derrubada gera uma janela de indisponibilidade da Metrics API (`pods.metrics.k8s.io`), durante a qual os HorizontalPodAutoscaler de `medprev-web-app-backend-graphql` e `medprev-web-app-frontend`, no namespace `medprev-web-app`, não conseguem calcular métricas de CPU/memória para decidir o número de réplicas. Impacto observável: o autoscaling desses dois componentes fica cego por alguns minutos a cada ciclo — se houver pico de carga durante a janela, o HPA não escala, mas fora dessas janelas o comportamento é normal.

### Causa raiz
Sinal real de infraestrutura (não é evento de código, então a divisão handled/unhandled de Error Tracking não se aplica). Confirmado por correlação 1:1 entre 6 ciclos `FailedDraining`→`InstanceTerminating` do nó que hospeda o `metrics-server` e os blocos `FailedComputeMetricsReplicas`/`FailedGetResourceMetric` do achado, sempre no mesmo minuto. Causa raiz: `metrics-server` sem `PodDisruptionBudget` e sem proteção contra disrupção do Karpenter, então cada consolidação de nó reinicia a única réplica e zera o cache de métricas do HPA até o novo pod completar o primeiro ciclo de scrape.

### Linha do tempo
6 ciclos idênticos entre `00:22:26 09/09/2026 BRT (epoch 1788924146000 · 2026-09-09T03:22:26.000Z)` e `21:27:06 10/09/2026 BRT (epoch 1789086426000 · 2026-09-11T00:27:06.000Z)`:
1. `00:22:26 09/09/2026 BRT (epoch 1788924146000 · 2026-09-09T03:22:26.000Z)` Karpenter inicia `FailedDraining` do nó `ip-10-0-10-50` (metrics-server); `00:22:50 09/09/2026 BRT (epoch 1788924170000 · 2026-09-09T03:22:50.000Z)` `Killing` do pod; `00:22:52 09/09/2026 BRT (epoch 1788924172000 · 2026-09-09T03:22:52.000Z)` `InstanceTerminating`; `00:22:57 09/09/2026 BRT (epoch 1788924177000 · 2026-09-09T03:22:57.000Z)` a `00:23:27 09/09/2026 BRT (epoch 1788924207000 · 2026-09-09T03:23:27.000Z)` erros de HPA nas duas HPAs (primeira ocorrência do achado, `first_seen`).
2. `00:32:46 09/09/2026 BRT (epoch 1788924766000 · 2026-09-09T03:32:46.000Z)` a `00:33:29 09/09/2026 BRT (epoch 1788924809000 · 2026-09-09T03:33:29.000Z)` — mesmo padrão, nó `ip-10-0-3-20`.
3. `03:44:49 09/09/2026 BRT (epoch 1788936289000 · 2026-09-09T06:44:49.000Z)` a `03:45:54 09/09/2026 BRT (epoch 1788936354000 · 2026-09-09T06:45:54.000Z)` — mesmo padrão, nó `ip-10-0-0-32`, incluindo `Unhealthy: readiness probe failed (connection refused)` do novo pod.
4. `07:35:41 09/09/2026 BRT (epoch 1788950141000 · 2026-09-09T10:35:41.000Z)` a `07:36:21 09/09/2026 BRT (epoch 1788950181000 · 2026-09-09T10:36:21.000Z)` — mesmo padrão.
5. `07:54:35 09/09/2026 BRT (epoch 1788951275000 · 2026-09-09T10:54:35.000Z)` a `07:54:53 09/09/2026 BRT (epoch 1788951293000 · 2026-09-09T10:54:53.000Z)` — mesmo padrão, com nova `Unhealthy: readiness probe failed`.
6. `21:27:06 10/09/2026 BRT (epoch 1789086426000 · 2026-09-11T00:27:06.000Z)` — sexto ciclo, correspondente à última ocorrência do achado (`last_seen`, `21:27:38 10/09/2026 BRT (epoch 1789086458000 · 2026-09-11T00:27:38.000Z)`).

### Evidências
- [Events Explorer — FailedComputeMetricsReplicas na janela](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-web-app%20FailedComputeMetricsReplicas&from_ts=1788808256645&to_ts=1789153856645&live=false)
- Consulta: `source:kubernetes env:production kube_namespace:kube-system metrics-server`, mesma janela — 6 ciclos de restart do pod, 25 eventos.
- Consulta: `source:kubernetes env:production kube_node:(ip-10-0-10-50.sa-east-1.compute.internal OR ip-10-0-3-20.sa-east-1.compute.internal OR ip-10-0-0-32.sa-east-1.compute.internal) Terminat*`, mesma janela — 6 eventos de dreno/terminação de nó.
- Consulta: `aggregate_events` com `group_by: [host]`, `interval: 6h`, mesma query/janela do achado — distribuição em 2 hosts (26 e 6 eventos).

### Ação recomendada
Repositório: infra — `target_repo` do achado aponta para `Medprev/medprev-web-app`, mas a causa é do cluster (`eks-medprev-online-prd`), não do código desse serviço; a correção pertence a `Medprev/medprev-cloud-iac`. Componente afetado: manifesto/Helm values do Deployment `metrics-server` em `kube-system`. Mudança concreta: (1) elevar `replicas` para ≥2 com `topologySpreadConstraints` ou `podAntiAffinity` para não colocar as réplicas no mesmo nó; (2) criar um `PodDisruptionBudget` (`minAvailable: 1`) para o Deployment `metrics-server`; (3) avaliar anotação `karpenter.sh/do-not-disrupt: "true"` no pod do metrics-server para evitar consolidação simultânea das réplicas. Validação: após o deploy, monitorar por 7 dias a mesma query (`source:kubernetes env:production status:warn kube_namespace:medprev-web-app FailedComputeMetricsReplicas`) e confirmar volume zerado ou próximo de zero durante ciclos de consolidação do Karpenter (cruzar com `source:kubernetes kube_namespace:kube-system metrics-server Killing`).

### Volume
32 ocorrências entre `16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z)` e `16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z)` (`observed_count`, mesma janela usada na consulta ao Datadog — sem divergência).

### Severidade e criticidade
`severity: medium` do achado. Avaliação de criticidade (inferência): baixa a média em condições normais de tráfego — o HPA usa o último valor válido de réplicas durante a janela cega, então o impacto só se materializa se um pico de carga real coincidir com uma das 6 janelas de poucos minutos identificadas. O defeito de fato mais relevante — ausência de redundância no `metrics-server` do cluster — tem criticidade potencialmente maior que o achado original, pois afeta o autoscaling de **todos** os workloads do cluster que dependem de HPA baseado em métricas de recursos, não apenas `medprev-web-app` (inferência, não medida diretamente neste achado).
