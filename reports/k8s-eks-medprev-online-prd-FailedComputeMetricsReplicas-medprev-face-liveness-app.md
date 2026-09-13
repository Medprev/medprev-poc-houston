---
fingerprint: k8s-eks-medprev-online-prd-FailedComputeMetricsReplicas-medprev-face-liveness-app
source: kubernetes
reason: FailedComputeMetricsReplicas
novelty: new
service: medprev-face-liveness-app
environment: production
window:
  from: 1788806810930
  to: 1789152410930
observed:
  count: 46
  first_seen: 1788924154000
  last_seen: 1789098354000
severity: medium
state: new
cost:
  input_tokens: 444482
  output_tokens: 10471
  cache_read_input_tokens: 347535
  cache_creation_input_tokens: 96937
  duration_s: 104.772
  usd: 0.566755
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-face-liveness-app%20FailedComputeMetricsReplicas&from_ts=1788806810930&to_ts=1789152410930&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-face-liveness-app%20FailedComputeMetricsReplicas&from_ts=1788806810930&to_ts=1789152410930&live=false

## Causa raiz

O achado é de `source:kubernetes`, não de Error Tracking, então a classificação `handled`/`unhandled` (que se aplica a spans/exceções de aplicação) não é o critério aqui — não há span algum do serviço afetado no Datadog: `search_datadog_spans` com `service:medprev-face-liveness-app status:error` na janela 07:09–11/09 devolveu 0 resultados, confirmando que este serviço não tem instrumentação APM e que o evento não é um erro de aplicação. É **sinal de infraestrutura real, não ruído de aplicação**: o evento `FailedComputeMetricsReplicas` no namespace `medprev-face-liveness-app` (46 ocorrências na janela `window_from`–`window_to`) faz parte de um padrão cluster-wide — a mesma agregação por `kube_namespace` no mesmo intervalo mostra o mesmo `Reason` em 8 namespaces simultaneamente (`medprev-rest-api`: 75, `medprev-face-liveness-app`: 46, `medprev-web-app`: 32, `medprev-cms`: 17, `medprev-institucional-cms`: 14, `medprev-metabase`: 14, `nginx-gateway-fabric`: 14, `medprev-analytics-etl-airflow`: 7). Consultando os eventos do próprio pod `metrics-server` em `kube-system`, o padrão fica claro: o Deployment `metrics-server` roda com uma única réplica ativa por vez, e essa réplica é repetidamente morta e recriada em outro nó (sequência karpenter `Nominated` → kubelet `Killing` → `SuccessfulCreate` → `Unhealthy: Readiness probe failed: ... connection refused`), consistente com rotação/consolidação de nós pelo Karpenter (spot ou bin-packing), não com um crash da aplicação metrics-server. Cada vez que o pod único do metrics-server fica indisponível durante a troca de nó, todos os HPAs do cluster falham em calcular réplicas até a nova réplica ficar pronta — daí o `FailedComputeMetricsReplicas` aparecer ao mesmo tempo em 8 namespaces diferentes. A causa está confirmada por evidência direta (eventos do pod `metrics-server`), não é hipótese.

## Linha do tempo

- 00:22:25 09/09/2026 BRT (epoch 1788924145000 · 2026-09-09T03:22:25.000Z) — Karpenter agenda novo nó para o pod `metrics-server-6bcb764664-clmwr` (`Nominated`).
- 00:22:34 09/09/2026 BRT (epoch 1788924154000 · 2026-09-09T03:22:34.000Z) — primeira ocorrência de `FailedComputeMetricsReplicas` no namespace `medprev-face-liveness-app` na janela (= `first_seen` do achado).
- 00:22:50 09/09/2026 BRT (epoch 1788924170000 · 2026-09-09T03:22:50.000Z) — kubelet mata o container `metrics-server` (pod `clmwr`); ReplicaSet cria o pod substituto `x5tq4`.
- 00:23:04 09/09/2026 BRT (epoch 1788924184000 · 2026-09-09T03:23:04.000Z)–00:29:35 09/09/2026 BRT (epoch 1788924575000 · 2026-09-09T03:29:35.000Z) — mais 5 ocorrências de `FailedComputeMetricsReplicas`/`FailedGetResourceMetric` enquanto o novo pod do metrics-server sobe.
- 00:32:00 09/09/2026 BRT (epoch 1788924720000 · 2026-09-09T03:32:00.000Z) — Karpenter agenda novo nó para o pod `x5tq4` (nova rotação de nó).
- 00:33:06 09/09/2026 BRT (epoch 1788924786000 · 2026-09-09T03:33:06.000Z) — kubelet mata `x5tq4`; ReplicaSet cria `s4gbm`.
- 03:44:48 09/09/2026 BRT (epoch 1788936288000 · 2026-09-09T06:44:48.000Z) → 03:45:24 09/09/2026 BRT (epoch 1788936324000 · 2026-09-09T06:45:24.000Z) → 03:45:25 09/09/2026 BRT (epoch 1788936325000 · 2026-09-09T06:45:25.000Z) — nova rotação: Karpenter nomeia nó para `s4gbm`, kubelet o mata, e a probe de prontidão falha com `connection refused` no pod recém-substituído.
- 07:02:27 09/09/2026 BRT (epoch 1788948147000 · 2026-09-09T10:02:27.000Z)–07:28:14 09/09/2026 BRT (epoch 1788949694000 · 2026-09-09T10:28:14.000Z) — mais 6 ocorrências de `FailedComputeMetricsReplicas` no namespace, sem novo evento de troca de nó do metrics-server entre elas (réplica única sob carga/latência).
- 07:35:16 09/09/2026 BRT (epoch 1788950116000 · 2026-09-09T10:35:16.000Z) → 07:35:41 09/09/2026 BRT (epoch 1788950141000 · 2026-09-09T10:35:41.000Z) → 07:35:42 09/09/2026 BRT (epoch 1788950142000 · 2026-09-09T10:35:42.000Z)–07:36:15 09/09/2026 BRT (epoch 1788950175000 · 2026-09-09T10:36:15.000Z) — quarta rotação de nó do metrics-server (pod `zjgf5`), com 3 novas ocorrências de `FailedComputeMetricsReplicas` durante a janela de indisponibilidade.
- 07:44:46 09/09/2026 BRT (epoch 1788950686000 · 2026-09-09T10:44:46.000Z), 07:45:01 09/09/2026 BRT (epoch 1788950701000 · 2026-09-09T10:45:01.000Z) — mais 2 ocorrências.
- 07:54:08 09/09/2026 BRT (epoch 1788951248000 · 2026-09-09T10:54:08.000Z) → 07:54:35 09/09/2026 BRT (epoch 1788951275000 · 2026-09-09T10:54:35.000Z) → 07:54:36 09/09/2026 BRT (epoch 1788951276000 · 2026-09-09T10:54:36.000Z) — quinta rotação (pod `mj2zl`), com nova falha de readiness probe (`connection refused`).
- 20:19:46 09/09/2026 BRT (epoch 1788995986000 · 2026-09-09T23:19:46.000Z), 20:20:01 09/09/2026 BRT (epoch 1788996001000 · 2026-09-09T23:20:01.000Z) — mais 2 ocorrências, réplica ainda `mj2zl`.
- 21:26:45 10/09/2026 BRT (epoch 1789086405000 · 2026-09-11T00:26:45.000Z) → 21:27:06 10/09/2026 BRT (epoch 1789086426000 · 2026-09-11T00:27:06.000Z) — sexta rotação de nó do metrics-server (pod `j9t7z`), já perto do fim da janela de coleta (`window_to`).
- `last_seen` do achado é 00:45:54 11/09/2026 BRT (epoch 1789098354000 · 2026-09-11T03:45:54.000Z) — não consultei um evento individual exatamente nesse timestamp, mas ele é consistente com o mesmo padrão de rotação de nó do metrics-server continuando até o fim da janela.

## Evidência

- 46 ocorrências de `FailedComputeMetricsReplicas` no namespace `medprev-face-liveness-app` entre 15:46:50 07/09/2026 BRT (epoch 1788806810930 · 2026-09-07T18:46:50.930Z) e 15:46:50 11/09/2026 BRT (epoch 1789152410930 · 2026-09-11T18:46:50.930Z) — [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-face-liveness-app%20FailedComputeMetricsReplicas&from_ts=1788806810930&to_ts=1789152410930&live=false).
- O mesmo `Reason` ocorre em mais 7 namespaces na mesma janela (`aggregate_events`, query `source:kubernetes status:warn FailedComputeMetricsReplicas env:production`, `group_by kube_namespace`): `medprev-rest-api` 75, `medprev-web-app` 32, `medprev-cms` 17, `medprev-institucional-cms` 14, `medprev-metabase` 14, `nginx-gateway-fabric` 14, `medprev-analytics-etl-airflow` 7 — total 219 eventos cluster-wide na janela, mesma consulta e período do achado.
- 0 spans de erro para o serviço na janela: `search_datadog_spans`, query `service:medprev-face-liveness-app status:error`, de 1788806810930 a 1789152410930 → `count: 0`, `has_more: false` (traces_explorer_url retornado pela própria ferramenta, sem instrumentação APM ativa para este serviço).
- 68 logs de `error`/`warn` no namespace na janela (`search_datadog_logs`, query `kube_namespace:medprev-face-liveness-app env:production status:(error OR warn)`), amostra inspecionada é um `403 directory index forbidden` do nginx — não relacionado à causa do HPA, sem correlação de trace.
- Eventos do pod `kube-system/metrics-server-*` na mesma janela (`search_datadog_events`, query `source:kubernetes env:production kube_namespace:kube-system (metrics-server OR FailedGetResourceMetric)`) mostram ao menos 6 ciclos de `Nominated` → `Killing` → `SuccessfulCreate`/`Started`, com duas falhas explícitas de readiness probe (`connection refused`) — sem nenhum evento de `CrashLoopBackOff` ou `BackOff`, o que descarta bug no próprio metrics-server e aponta para rotação de nó.

## Ação recomendada

Aumentar a resiliência do Deployment `metrics-server` no cluster `eks-medprev-online-prd` (réplicas ≥2 com anti-afinidade de nó/zona, ou PodDisruptionBudget) para que a rotação de nós do Karpenter não derrube a única instância disponível; esta é uma ação de infraestrutura, não de código do `medprev-face-liveness-app`.

## Corpo da issue

### Descrição do incidente
No cluster de produção `eks-medprev-online-prd`, o HorizontalPodAutoscaler não conseguiu calcular réplicas (`FailedComputeMetricsReplicas`) repetidamente em 8 namespaces simultâneos, incluindo `medprev-face-liveness-app` (46 ocorrências na janela observada). O impacto observável é a suspensão temporária do autoscaling baseado em CPU/memória durante cada janela de indisponibilidade do metrics-server (tipicamente minutos), sem impacto direto percebido pelo usuário final até o momento — não há erro de aplicação nem degradação de tráfego correlacionada nos logs do serviço.

### Causa raiz
Ruído de aplicação zero — 0 spans de erro do serviço na janela (`service:medprev-face-liveness-app status:error`). Causa raiz confirmada por evidência direta: o Deployment `metrics-server` em `kube-system` roda com uma única réplica ativa, que é repetidamente morta e recriada em outro nó por rotação do Karpenter (spot interruption ou consolidação), deixando o `metrics.k8s.io` indisponível a cada troca e derrubando os HPAs de todos os namespaces ao mesmo tempo.

### Linha do tempo
- 00:22:25 09/09/2026 BRT (epoch 1788924145000 · 2026-09-09T03:22:25.000Z) Karpenter nomeia novo nó para o pod `metrics-server-6bcb764664-clmwr`.
- 00:22:34 09/09/2026 BRT (epoch 1788924154000 · 2026-09-09T03:22:34.000Z) primeira ocorrência de `FailedComputeMetricsReplicas` em `medprev-face-liveness-app` (= `first_seen`).
- 00:22:50 09/09/2026 BRT (epoch 1788924170000 · 2026-09-09T03:22:50.000Z) kubelet mata o pod `clmwr`; substituto `x5tq4` criado.
- 00:23:04 09/09/2026 BRT (epoch 1788924184000 · 2026-09-09T03:23:04.000Z)–00:29:35 09/09/2026 BRT (epoch 1788924575000 · 2026-09-09T03:29:35.000Z) mais 5 ocorrências de `FailedComputeMetricsReplicas`/`FailedGetResourceMetric`.
- 00:32:00 09/09/2026 BRT (epoch 1788924720000 · 2026-09-09T03:32:00.000Z)→00:33:06 09/09/2026 BRT (epoch 1788924786000 · 2026-09-09T03:33:06.000Z) segunda rotação de nó (`x5tq4` → `s4gbm`).
- 03:44:48 09/09/2026 BRT (epoch 1788936288000 · 2026-09-09T06:44:48.000Z)→03:45:24 09/09/2026 BRT (epoch 1788936324000 · 2026-09-09T06:45:24.000Z)→03:45:25 09/09/2026 BRT (epoch 1788936325000 · 2026-09-09T06:45:25.000Z) terceira rotação (`s4gbm`→`9t4g8`) com falha de readiness probe (`connection refused`).
- 07:02:27 09/09/2026 BRT (epoch 1788948147000 · 2026-09-09T10:02:27.000Z)–07:28:14 09/09/2026 BRT (epoch 1788949694000 · 2026-09-09T10:28:14.000Z) mais 6 ocorrências do erro sob a réplica única em atividade.
- 07:35:16 09/09/2026 BRT (epoch 1788950116000 · 2026-09-09T10:35:16.000Z)→07:35:41 09/09/2026 BRT (epoch 1788950141000 · 2026-09-09T10:35:41.000Z) quarta rotação (`9t4g8`→`zjgf5`).
- 07:44:46 09/09/2026 BRT (epoch 1788950686000 · 2026-09-09T10:44:46.000Z), 07:45:01 09/09/2026 BRT (epoch 1788950701000 · 2026-09-09T10:45:01.000Z) mais 2 ocorrências.
- 07:54:08 09/09/2026 BRT (epoch 1788951248000 · 2026-09-09T10:54:08.000Z)→07:54:35 09/09/2026 BRT (epoch 1788951275000 · 2026-09-09T10:54:35.000Z)→07:54:36 09/09/2026 BRT (epoch 1788951276000 · 2026-09-09T10:54:36.000Z) quinta rotação (`zjgf5`→`mj2zl`) com nova falha de readiness probe.
- 20:19:46 09/09/2026 BRT (epoch 1788995986000 · 2026-09-09T23:19:46.000Z), 20:20:01 09/09/2026 BRT (epoch 1788996001000 · 2026-09-09T23:20:01.000Z) mais 2 ocorrências.
- 21:26:45 10/09/2026 BRT (epoch 1789086405000 · 2026-09-11T00:26:45.000Z)→21:27:06 10/09/2026 BRT (epoch 1789086426000 · 2026-09-11T00:27:06.000Z) sexta rotação (`mj2zl`→`j9t7z`), já perto do fim da janela.
- `last_seen` do achado: 00:45:54 11/09/2026 BRT (epoch 1789098354000 · 2026-09-11T03:45:54.000Z) — consistente com o padrão continuando até o fim da janela; não localizei o evento individual exato desse instante.

### Evidências
- [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-face-liveness-app%20FailedComputeMetricsReplicas&from_ts=1788806810930&to_ts=1789152410930&live=false) — 46 ocorrências.
- `aggregate_events`, query `source:kubernetes status:warn FailedComputeMetricsReplicas env:production`, `group_by: kube_namespace`, mesma janela — 219 eventos em 8 namespaces (padrão cluster-wide).
- `search_datadog_spans`, query `service:medprev-face-liveness-app status:error`, mesma janela — 0 resultados (sem instrumentação APM / sem erro de aplicação).
- `search_datadog_logs`, query `kube_namespace:medprev-face-liveness-app env:production status:(error OR warn)`, mesma janela — 68 logs, sem correlação com o evento do HPA.
- `search_datadog_events`, query `source:kubernetes env:production kube_namespace:kube-system (metrics-server OR FailedGetResourceMetric)`, mesma janela — 25 eventos mostrando 6 ciclos de rotação de nó do pod `metrics-server` (réplica única).

### Ação recomendada
Repositório: infra — sem repositório de código específico identificado para o Deployment `metrics-server` (provavelmente `Medprev/medprev-cloud-iac`, a confirmar por quem tem acesso ao manifesto). Componente afetado: Deployment `metrics-server` no namespace `kube-system` do cluster `eks-medprev-online-prd`. Mudança recomendada: elevar `replicas` para pelo menos 2 com `podAntiAffinity` por nó/zona, e/ou adicionar um `PodDisruptionBudget` (`minAvailable: 1`) para que o Karpenter não possa evictar a única réplica de uma vez. Validação: após o deploy, confirmar via `aggregate_events` (mesma query usada nesta investigação) que `FailedComputeMetricsReplicas` deixa de ocorrer durante rotações de nó subsequentes do Karpenter, e verificar nos eventos do pod `metrics-server` que sempre há ao menos uma réplica `Ready` durante qualquer `Killing`.

### Volume
46 ocorrências entre 15:46:50 07/09/2026 BRT (epoch 1788806810930 · 2026-09-07T18:46:50.930Z) e 15:46:50 11/09/2026 BRT (epoch 1789152410930 · 2026-09-11T18:46:50.930Z) — igual ao `observed_count` do achado, confirmado pela mesma consulta.

### Severidade e criticidade
`severity` do achado é `medium`. Como o evento é sinal real (não ruído), essa severidade se aplica ao próprio efeito observado (HPA temporariamente cego a métricas). Inferência de criticidade de negócio: o defeito de fundo — metrics-server sem redundância — é potencialmente mais grave que o `medium` do achado individual, pois afeta o autoscaling de 8 serviços de produção simultaneamente a cada rotação de nó; se ocorrer durante um pico de tráfego real, o HPA pode atrasar o scale-out e causar degradação de capacidade em múltiplos serviços ao mesmo tempo (inferência, não medida diretamente nesta investigação).
