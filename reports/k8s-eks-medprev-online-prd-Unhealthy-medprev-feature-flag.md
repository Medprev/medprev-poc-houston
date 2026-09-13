---
fingerprint: k8s-eks-medprev-online-prd-Unhealthy-medprev-feature-flag
source: kubernetes
reason: Unhealthy
novelty: new
service: medprev-feature-flag
environment: production
window:
  from: 1788814356569
  to: 1789159956569
observed:
  count: 1
  first_seen: 1789016113000
  last_seen: 1789016113000
severity: medium
state: new
cost:
  input_tokens: 434742
  output_tokens: 9212
  cache_read_input_tokens: 347780
  cache_creation_input_tokens: 86950
  duration_s: 93.575
  usd: 0.514147
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-feature-flag%20Unhealthy&from_ts=1788814356569&to_ts=1789159956569&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-feature-flag%20Unhealthy&from_ts=1788814356569&to_ts=1789159956569&live=false

## Causa raiz

O achado é sobre o serviço `medprev-feature-flag` (pod `flipt`, imagem `docker.flipt.io/flipt/flipt:v1.50.0`) no cluster `eks-medprev-online-prd`. O evento `Unhealthy` isolado (falha do readiness probe, `connection refused` na porta 8080) é sintoma, não causa: ele coincide, no mesmo segundo, com um evento `Killing`/`Nominated` do Karpenter para o mesmo pod — ou seja, o probe falhou porque o Karpenter já estava terminando o container, não porque a aplicação quebrou sozinha. Investigando o namespace inteiro na janela de coleta e depois numa janela mais ampla (`source:kubernetes kube_namespace:medprev-feature-flag Killing`, `00:22:26 09/09/2026 BRT (epoch 1788924146000 · 2026-09-09T03:22:26.000Z)` a `00:45:33 11/09/2026 BRT (epoch 1789098333000 · 2026-09-11T03:45:33.000Z)`), encontrei **12 ciclos de kill/recreate** do mesmo Deployment (réplica única, mesmo `kube_replica_set:medprev-feature-flag-flipt-5bcdcc6946`), todos disparados pelo Karpenter fazendo consolidação/rotação de nós, cada um seguido de `FailedScheduling` transitório por `Insufficient cpu`/`Insufficient memory` antes do pod conseguir subir em outro nó. Isso é **SINAL**, não ruído: é indisponibilidade real e recorrente de um serviço que roda com 1 réplica e sem proteção de disrupção, não uma classificação de erro de negócio — a métrica `handled`/`unhandled` de Error Tracking não se aplica aqui porque a fonte é Kubernetes, não Error Tracking (não há spans de APM: `aggregate_spans` para `service:medprev-feature-flag OR service:flipt` devolveu 0 buckets nessa janela, e `search_datadog_logs` para o mesmo serviço/pod devolveu 0 registros — este serviço não está instrumentado com logs/traces ligados ao Datadog).

## Linha do tempo

Eventos dentro do ciclo do pod `q9wx6`, que é o pod citado no achado (consulta: `source:kubernetes kube_namespace:medprev-feature-flag`, janela 01:33:00 10/09/2026 BRT (epoch 1789014780000 · 2026-09-10T04:33:00.000Z)–02:13:00 10/09/2026 BRT (epoch 1789017180000 · 2026-09-10T05:13:00.000Z)):

1. 01:33:51 10/09/2026 BRT (epoch 1789014831000 · 2026-09-10T04:33:51.000Z) — Karpenter mata o container `flipt` do pod anterior (`l7c64`) e nomeia o pod `q9wx6` para um novo nó (`Killing`/`Nominated`).
2. 01:33:52 10/09/2026 BRT (epoch 1789014832000 · 2026-09-10T04:33:52.000Z) — `FailedScheduling`: 0/12 nós disponíveis (`Insufficient memory`, `Insufficient cpu`, taints); no mesmo instante, `SuccessfulCreate` cria o pod `q9wx6`.
3. 01:33:53 10/09/2026 BRT (epoch 1789014833000 · 2026-09-10T04:33:53.000Z) — Karpenter nomeia novo nodeclaim (`default-8tfmv`) para o pod `q9wx6`.
4. 01:34:17 10/09/2026 BRT (epoch 1789014857000 · 2026-09-10T04:34:17.000Z) — segunda tentativa de agendamento falha (`FailedScheduling`, 0/13 nós, mesmas causas).
5. 01:34:35 10/09/2026 BRT (epoch 1789014875000 · 2026-09-10T04:34:35.000Z) — `TaintManagerEviction` cancela uma remoção pendente do pod `q9wx6`.
6. 01:34:42 10/09/2026 BRT (epoch 1789014882000 · 2026-09-10T04:34:42.000Z) — pod `q9wx6` finalmente agendado, imagem puxada (5,9s) e container iniciado.
7. 01:55:13 10/09/2026 BRT (epoch 1789016113000 · 2026-09-10T04:55:13.000Z) — **evento do achado**: Karpenter mata `q9wx6` de novo (`Killing`/`Nominated` para outro nó) e, no mesmo segundo, o kubelet reporta `Unhealthy` (readiness probe `connection refused`) — sintoma da terminação, não causa independente; `SuccessfulCreate` cria o pod seguinte, `wt9kb`.
8. 01:55:14 10/09/2026 BRT (epoch 1789016114000 · 2026-09-10T04:55:14.000Z) — `wt9kb` agendado e imagem sendo puxada.
9. 01:55:40 10/09/2026 BRT (epoch 1789016140000 · 2026-09-10T04:55:40.000Z) — `wt9kb` iniciado (pull levou 25,3s).
10. 02:12:39 10/09/2026 BRT (epoch 1789017159000 · 2026-09-10T05:12:39.000Z) — Karpenter mata `wt9kb` e cria `bhvt6` — o ciclo se repete.

Esse padrão de kill/recreate pelo Karpenter já vinha ocorrendo desde antes da janela do achado (primeiro evento `Killing` registrado em 00:22:26 09/09/2026 BRT (epoch 1788924146000 · 2026-09-09T03:22:26.000Z)) e continuou depois dela (último evento `Killing` visto em 00:45:33 11/09/2026 BRT (epoch 1789098333000 · 2026-09-11T03:45:33.000Z)), com pelo menos 12 ciclos nesse intervalo — consulta `source:kubernetes kube_namespace:medprev-feature-flag Killing` entre 00:22:26 09/09/2026 BRT (epoch 1788924146000 · 2026-09-09T03:22:26.000Z) e 00:45:33 11/09/2026 BRT (epoch 1789098333000 · 2026-09-11T03:45:33.000Z).

## Evidência

- Evento de origem do achado (readiness probe falhou por `connection refused` no exato segundo em que o Karpenter iniciou a terminação do pod): [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-feature-flag%20Unhealthy&from_ts=1788814356569&to_ts=1789159956569&live=false) (`datadog_url` do achado).
- 1 ocorrência do Reason `Unhealthy` entre 17:52:36 07/09/2026 BRT (epoch 1788814356569 · 2026-09-07T20:52:36.569Z) e 17:52:36 11/09/2026 BRT (epoch 1789159956569 · 2026-09-11T20:52:36.569Z) — mesma consulta acima, campo `observed_count` do achado.
- 17 eventos Kubernetes (`Killing`, `FailedScheduling`, `SuccessfulCreate`, `Pulling`/`Pulled`/`Started`, `TaintManagerEviction`) para o namespace `medprev-feature-flag` na janela 01:33:00 10/09/2026 BRT (epoch 1789014780000 · 2026-09-10T04:33:00.000Z)–02:13:00 10/09/2026 BRT (epoch 1789017180000 · 2026-09-10T05:13:00.000Z): consulta `source:kubernetes kube_namespace:medprev-feature-flag` rodada via ferramenta de eventos (sem link pronto para essa consulta específica).
- 12 eventos `Killing` do mesmo ReplicaSet (`medprev-feature-flag-flipt-5bcdcc6946`) entre 00:22:26 09/09/2026 BRT (epoch 1788924146000 · 2026-09-09T03:22:26.000Z) e 00:45:33 11/09/2026 BRT (epoch 1789098333000 · 2026-09-11T03:45:33.000Z): consulta `source:kubernetes kube_namespace:medprev-feature-flag Killing` (sem link pronto).
- 0 spans de APM para `service:medprev-feature-flag OR service:flipt` na janela do achado: `aggregate_spans` retornou `total_buckets: 0` (consulta acima).
- 0 logs de aplicação para `service:medprev-feature-flag` nem para `kube_namespace:medprev-feature-flag pod_name:medprev-feature-flag-flipt-5bcdcc6946-q9wx6` na janela em torno do evento: `search_datadog_logs` retornou `count: 0` em ambas as tentativas.

## Ação recomendada

Adicionar `replicas >= 2` com anti-afinidade de pod e um `PodDisruptionBudget` (`minAvailable: 1`) ao Deployment `medprev-feature-flag-flipt` para que a consolidação de nós do Karpenter não derrube a única réplica em produção.

## Corpo da issue

### Descrição do incidente
O Deployment `medprev-feature-flag-flipt` (namespace `medprev-feature-flag`, cluster `eks-medprev-online-prd`) roda com uma única réplica. Sempre que o Karpenter consolida ou rotaciona nós, esse pod é terminado e recriado, ficando indisponível por dezenas de segundos a cada ciclo — o serviço de feature flags fica sem readiness durante a janela de restart. Impacto observável: qualquer consumidor do Flipt sofre falhas/timeouts de leitura de flags durante cada ciclo de recriação.

### Causa raiz
SINAL, não ruído: 12 ciclos de kill/recreate do mesmo pod entre 00:22:26 09/09/2026 BRT (epoch 1788924146000 · 2026-09-09T03:22:26.000Z) e 00:45:33 11/09/2026 BRT (epoch 1789098333000 · 2026-09-11T03:45:33.000Z) (consulta `source:kubernetes kube_namespace:medprev-feature-flag Killing`), todos por ação do Karpenter, não por falha de aplicação. O evento `Unhealthy` do achado (01:55:13 10/09/2026 BRT (epoch 1789016113000 · 2026-09-10T04:55:13.000Z)) é sintoma da terminação do pod pelo Karpenter no mesmo segundo, não uma falha de saúde independente da aplicação. Cada recriação passa por `FailedScheduling` transitório (`Insufficient cpu`/`Insufficient memory`) antes de conseguir subir em outro nó. Causa raiz confirmada: ausência de réplicas redundantes e de `PodDisruptionBudget` para este Deployment, expondo cada rotação de nó do Karpenter como indisponibilidade do serviço.

### Linha do tempo
1. 01:33:51 10/09/2026 BRT (epoch 1789014831000 · 2026-09-10T04:33:51.000Z) Karpenter mata pod anterior (`l7c64`), nomeia `q9wx6`.
2. 01:33:52 10/09/2026 BRT (epoch 1789014832000 · 2026-09-10T04:33:52.000Z) `FailedScheduling` (0/12 nós) + `SuccessfulCreate` de `q9wx6`.
3. 01:34:17 10/09/2026 BRT (epoch 1789014857000 · 2026-09-10T04:34:17.000Z) segunda `FailedScheduling` (0/13 nós).
4. 01:34:42 10/09/2026 BRT (epoch 1789014882000 · 2026-09-10T04:34:42.000Z) `q9wx6` agendado e iniciado.
5. 01:55:13 10/09/2026 BRT (epoch 1789016113000 · 2026-09-10T04:55:13.000Z) Karpenter mata `q9wx6`; kubelet reporta `Unhealthy` (readiness `connection refused`) no mesmo segundo — este é o evento do achado; `SuccessfulCreate` de `wt9kb`.
6. 01:55:40 10/09/2026 BRT (epoch 1789016140000 · 2026-09-10T04:55:40.000Z) `wt9kb` iniciado.
7. 02:12:39 10/09/2026 BRT (epoch 1789017159000 · 2026-09-10T05:12:39.000Z) Karpenter mata `wt9kb`, cria `bhvt6` — ciclo se repete.
8. Padrão confirmado recorrente desde 00:22:26 09/09/2026 BRT (epoch 1788924146000 · 2026-09-09T03:22:26.000Z) até 00:45:33 11/09/2026 BRT (epoch 1789098333000 · 2026-09-11T03:45:33.000Z) (12 ocorrências de `Killing` no mesmo ReplicaSet).

### Evidências
- https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-feature-flag%20Unhealthy&from_ts=1788814356569&to_ts=1789159956569&live=false
- Consulta `source:kubernetes kube_namespace:medprev-feature-flag` (janela 01:33:00 10/09/2026 BRT (epoch 1789014780000 · 2026-09-10T04:33:00.000Z)–02:13:00 10/09/2026 BRT (epoch 1789017180000 · 2026-09-10T05:13:00.000Z)): 17 eventos de kill/reschedule/pull/start.
- Consulta `source:kubernetes kube_namespace:medprev-feature-flag Killing` (janela 00:22:26 09/09/2026 BRT (epoch 1788924146000 · 2026-09-09T03:22:26.000Z)–00:45:33 11/09/2026 BRT (epoch 1789098333000 · 2026-09-11T03:45:33.000Z)): 12 eventos.
- `aggregate_spans` `service:medprev-feature-flag OR service:flipt`: 0 spans na janela do achado.
- `search_datadog_logs` `service:medprev-feature-flag` e `kube_namespace:medprev-feature-flag pod_name:...-q9wx6`: 0 logs.

### Ação recomendada
Repositório: `Medprev/medprev-feature-flag`. No manifesto/Helm chart do Deployment `medprev-feature-flag-flipt`, alterar `spec.replicas` de 1 para pelo menos 2, adicionar `podAntiAffinity` (nós distintos) e criar um `PodDisruptionBudget` com `minAvailable: 1` para esse Deployment. Validar rodando `mise run run` (leitura, sem custo) e confirmando via `source:kubernetes kube_namespace:medprev-feature-flag Killing` que uma rotação subsequente do Karpenter não gera mais evento `Unhealthy` — deve haver sempre pelo menos uma réplica `Ready` durante a substituição.

### Volume
1 ocorrência do Reason `Unhealthy` entre 17:52:36 07/09/2026 BRT (epoch 1788814356569 · 2026-09-07T20:52:36.569Z) e 17:52:36 11/09/2026 BRT (epoch 1789159956569 · 2026-09-11T20:52:36.569Z) (`observed_count` do achado). Consulta adicional própria (`Killing`, janela mais ampla 00:22:26 09/09/2026 BRT (epoch 1788924146000 · 2026-09-09T03:22:26.000Z)–00:45:33 11/09/2026 BRT (epoch 1789098333000 · 2026-09-11T03:45:33.000Z)): 12 ciclos de recriação do pod.

### Severidade e criticidade
`severity: medium` do achado não se aplica ao erro `Unhealthy` isolado em si, que é apenas sintoma de terminação. O defeito real — ausência de réplica redundante/PDB causando indisponibilidade recorrente do serviço de feature flags a cada rotação de nó do Karpenter — é, por inferência (não é campo direto do achado), de criticidade **alta**: qualquer serviço dependente de Flipt para decisões de feature flag fica sujeito a falhas de leitura durante cada um dos ciclos observados (12 em ~2 dias), com potencial de causar comportamento incorreto ou timeouts em cascata nos consumidores.
