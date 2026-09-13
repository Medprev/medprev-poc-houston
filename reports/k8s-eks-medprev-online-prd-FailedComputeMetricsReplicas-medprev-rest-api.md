---
fingerprint: k8s-eks-medprev-online-prd-FailedComputeMetricsReplicas-medprev-rest-api
source: kubernetes
reason: FailedComputeMetricsReplicas
novelty: new
service: medprev-rest-api
environment: production
window:
  from: 1788803749711
  to: 1789149349711
observed:
  count: 75
  first_seen: 1788924171000
  last_seen: 1789086458000
severity: medium
state: new
cost:
  input_tokens: 751103
  output_tokens: 12957
  cache_read_input_tokens: 665506
  cache_creation_input_tokens: 85579
  duration_s: 133.083
  usd: 0.6097542
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20FailedComputeMetricsReplicas&from_ts=1788803749711&to_ts=1789149349711&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20FailedComputeMetricsReplicas&from_ts=1788803749711&to_ts=1789149349711&live=false

## Causa raiz

O `medprev-rest-api` (múltiplos HorizontalPodAutoscalers: `-adm`, `-pp`, `-ag`, `-gama`) tem 75 eventos `FailedComputeMetricsReplicas` entre 00:22:51 09/09/2026 BRT (epoch 1788924171000 · 2026-09-09T03:22:51.000Z) e 21:27:38 10/09/2026 BRT (epoch 1789086458000 · 2026-09-11T00:27:38.000Z) porque o **metrics-server do cluster** (não o `medprev-rest-api`) foi morto e recriado repetidamente pelo Karpenter durante consolidação/substituição de nós, deixando janelas curtas sem `pods.metrics.k8s.io` disponível. Confirmado consultando `kube_namespace:kube-system metrics-server`: a cada ciclo (ex.: 00:22:25 09/09/2026 BRT (epoch 1788924145000 · 2026-09-09T03:22:25.000Z) Karpenter nomeia novo node → 00:22:50 09/09/2026 BRT (epoch 1788924170000 · 2026-09-09T03:22:50.000Z) kubelet mata o container `metrics-server` → pod recriado em outro node), os HPAs do `medprev-rest-api` reportam a falha nos segundos seguintes. Isso não é isolado ao `medprev-rest-api`: a mesma busca sem filtro de namespace (`FailedComputeMetricsReplicas OR FailedGetResourceMetric`, mesma janela) devolveu **1362** ocorrências no cluster inteiro — ou seja, todo HPA do cluster é afetado, não um bug de código deste serviço.

Classificação: **ruído para o Error Tracking/APM do `medprev-rest-api`** — os spans de erro do serviço na mesma janela (`service:medprev-rest-api status:error`) são **100% `handled`** (110 ocorrências, todas HTTP 404), sem nenhum erro `unhandled` correlacionado ao horário das falhas de HPA. O defeito real não é um bug no código do `medprev-rest-api`, e sim na infraestrutura: o Deployment `metrics-server` (namespace `kube-system`) parece rodar com réplica única e sem tolerância à disruption do Karpenter, sofrendo restarts recorrentes que derrubam a métrica de CPU/memória usada por todos os HPAs do cluster durante a troca de pod/nó.

## Linha do tempo

- 00:22:25 09/09/2026 BRT (epoch 1788924145000 · 2026-09-09T03:22:25.000Z) — Karpenter nomeia o pod `metrics-server-6bcb764664-clmwr` para um novo node (`nodeclaim/default-b95t4`), sinal de consolidação/substituição de nó em andamento (consulta: `kube_namespace:kube-system metrics-server`, mesma janela).
- 00:22:50 09/09/2026 BRT (epoch 1788924170000 · 2026-09-09T03:22:50.000Z) — kubelet mata o container `metrics-server` no node antigo (`Killing`); o replicaset cria o pod substituto `metrics-server-6bcb764664-x5tq4`.
- 00:22:51 09/09/2026 BRT (epoch 1788924171000 · 2026-09-09T03:22:51.000Z) — **first_seen do achado**: HPAs `medprev-rest-api-adm`, `-pp`, `-ag`, `-gama` reportam `FailedComputeMetricsReplicas` — "the server is currently unable to handle the request (get pods.metrics.k8s.io)" (evidência: [Events Explorer](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20FailedComputeMetricsReplicas&from_ts=1788803749711&to_ts=1789149349711&live=false)).
- 00:23:06 09/09/2026 BRT (epoch 1788924186000 · 2026-09-09T03:23:06.000Z) — repetição do mesmo erro nos HPAs `-ag` e `-pp`, minutos depois.
- 00:32:00 09/09/2026 BRT (epoch 1788924720000 · 2026-09-09T03:32:00.000Z) a 00:33:12 09/09/2026 BRT (epoch 1788924792000 · 2026-09-09T03:33:12.000Z) — novo ciclo: Karpenter nomeia outro node, kubelet mata o `metrics-server` de novo, novo pod (`s4gbm`) criado e iniciado.
- 03:44:48 09/09/2026 BRT (epoch 1788936288000 · 2026-09-09T06:44:48.000Z) a 03:45:28 09/09/2026 BRT (epoch 1788936328000 · 2026-09-09T06:45:28.000Z) — mais um ciclo de substituição; durante a troca o novo pod do `metrics-server` falha o readiness probe ("connection refused") antes de estabilizar.
- 07:35:16 09/09/2026 BRT (epoch 1788950116000 · 2026-09-09T10:35:16.000Z) a 07:35:41 09/09/2026 BRT (epoch 1788950141000 · 2026-09-09T10:35:41.000Z) — mais um ciclo de substituição de node/pod do `metrics-server`.
- Sem ocorrências do achado entre ~03:45:00 09/09/2026 BRT (epoch 1788936300000 · 2026-09-09T06:45:00.000Z) e 21:27:08 10/09/2026 BRT (epoch 1789086428000 · 2026-09-11T00:27:08.000Z) — a distribuição por 6h (`aggregate_events`, mesma janela) mostra 32 eventos no bucket de 21:00:00 08/09/2026 BRT (epoch 1788912000000 · 2026-09-09T00:00:00.000Z), 32 no de 03:00:00 09/09/2026 BRT (epoch 1788933600000 · 2026-09-09T06:00:00.000Z) e 11 no de 21:00:00 10/09/2026 BRT (epoch 1789084800000 · 2026-09-11T00:00:00.000Z), total 75 — consistente com `observed_count`; o defeito é episódico, atrelado a cada substituição de pod do `metrics-server`, não contínuo.
- 21:27:08 10/09/2026 BRT (epoch 1789086428000 · 2026-09-11T00:27:08.000Z) a **21:27:38 10/09/2026 BRT (epoch 1789086458000 · 2026-09-11T00:27:38.000Z) (last_seen do achado)** — última leva, agora com mensagem "no metrics returned from resource metrics API" (pod do `metrics-server` recém-substituído, ainda sem scrape completo) nos HPAs `-adm`, `-pp`, `-ag`.

## Evidência

- 75 ocorrências de `FailedComputeMetricsReplicas` no namespace `medprev-rest-api` entre `window_from` (14:55:49 07/09/2026 BRT · epoch 1788803749711 · 14:55:49 07/09/2026 BRT (epoch 1788803749711 · 2026-09-07T17:55:49.711Z)) e `window_to` (14:55:49 11/09/2026 BRT · epoch 1789149349711 · 14:55:49 11/09/2026 BRT (epoch 1789149349711 · 2026-09-11T17:55:49.711Z)), confirmado por `aggregate_events` (`count: 75`, mesma query/janela do achado): [Events Explorer](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20FailedComputeMetricsReplicas&from_ts=1788803749711&to_ts=1789149349711&live=false).
- Mesma falha (`FailedComputeMetricsReplicas OR FailedGetResourceMetric`), sem filtro de namespace, mesma janela: **1362** ocorrências no cluster inteiro — query `source:kubernetes env:production kube_cluster_name:eks-medprev-online-prd status:warn (FailedComputeMetricsReplicas OR FailedGetResourceMetric)`, sem link pronto para esse escopo (query executada diretamente).
- Spans de erro do próprio `medprev-rest-api` na mesma janela: 110 ocorrências, **100% `@error.handling:handled`**, todas `@http.status_code:404` — query `service:medprev-rest-api status:error`, agrupada por `@error.handling`/`@http.status_code` (`aggregate_spans`); nenhum erro `unhandled` correlacionado.
- Eventos do pod `metrics-server` em `kube-system` na mesma janela mostram ciclo repetido `Nominated` (Karpenter) → `Killing` (kubelet) → `SuccessfulCreate`/`Scheduled`/`Pulled`/`Started`, em pelo menos 4 nodes diferentes (`ip-10-0-10-50`, `ip-10-0-3-20`, `ip-10-0-0-32`, `ip-10-0-8-247`, `ip-10-0-10-11`...) — query `source:kubernetes env:production kube_cluster_name:eks-medprev-online-prd kube_namespace:kube-system metrics-server`, sem link pronto (executada diretamente); 25 eventos retornados, mostrando o padrão de substituição contínua.

## Ação recomendada

Ação é de infraestrutura (Karpenter + `metrics-server`), não de código do `medprev-rest-api`: aumentar a resiliência do Deployment `metrics-server` (réplicas ≥2 com anti-affinity/topology spread, e um `PodDisruptionBudget` ou anotação para reduzir a prioridade de consolidação do Karpenter sobre esse pod) no repositório de infraestrutura.

## Corpo da issue

### Descrição do incidente
No cluster `eks-medprev-online-prd`, o Deployment `metrics-server` (namespace `kube-system`) é interrompido e recriado repetidamente pelo Karpenter durante consolidação/substituição de nós. A cada substituição, existe uma janela curta sem `pods.metrics.k8s.io` disponível, e todo HorizontalPodAutoscaler do cluster — incluindo os quatro HPAs do `medprev-rest-api` (`-adm`, `-pp`, `-ag`, `-gama`) — falha em calcular réplicas (`FailedComputeMetricsReplicas`/`FailedGetResourceMetric`) até o próximo scrape bem-sucedido. Impacto observável: autoscaling por CPU/memória fica temporariamente inoperante para todos os workloads com HPA durante essas janelas, não apenas para o `medprev-rest-api`.

### Causa raiz
**Ruído** para o `medprev-rest-api` em si — os erros de aplicação (spans, `service:medprev-rest-api status:error`) são 100% `handled` (110/110, todos 404), sem qualquer `unhandled` na janela. A causa raiz real é de infraestrutura: o pod único do `metrics-server` é morto e recriado em nodes diferentes repetidamente (Karpenter consolidando/substituindo nós), deixando o cluster sem métricas de recursos por curtos intervalos a cada ciclo — confirmado por 1362 ocorrências do mesmo tipo de falha em todo o cluster na mesma janela, contra apenas 75 no namespace do achado.

### Linha do tempo
- 00:22:25 09/09/2026 BRT (epoch 1788924145000 · 2026-09-09T03:22:25.000Z) Karpenter nomeia novo node para o pod `metrics-server-6bcb764664-clmwr`.
- 00:22:50 09/09/2026 BRT (epoch 1788924170000 · 2026-09-09T03:22:50.000Z) kubelet mata o container `metrics-server`; replicaset cria pod substituto.
- 00:22:51 09/09/2026 BRT (epoch 1788924171000 · 2026-09-09T03:22:51.000Z) (first_seen do achado) HPAs `medprev-rest-api-adm/pp/ag/gama` falham com "server is currently unable to handle the request (get pods.metrics.k8s.io)".
- 00:23:06 09/09/2026 BRT (epoch 1788924186000 · 2026-09-09T03:23:06.000Z) repetição da falha em `-ag`/`-pp`.
- 00:32:00 09/09/2026 BRT (epoch 1788924720000 · 2026-09-09T03:32:00.000Z)–00:33:12 09/09/2026 BRT (epoch 1788924792000 · 2026-09-09T03:33:12.000Z) novo ciclo de substituição do pod `metrics-server` em outro node.
- 03:44:48 09/09/2026 BRT (epoch 1788936288000 · 2026-09-09T06:44:48.000Z)–03:45:28 09/09/2026 BRT (epoch 1788936328000 · 2026-09-09T06:45:28.000Z) novo ciclo; readiness probe do novo pod falha momentaneamente ("connection refused").
- 07:35:16 09/09/2026 BRT (epoch 1788950116000 · 2026-09-09T10:35:16.000Z)–07:35:41 09/09/2026 BRT (epoch 1788950141000 · 2026-09-09T10:35:41.000Z) mais um ciclo de substituição de node/pod.
- 21:27:08 10/09/2026 BRT (epoch 1789086428000 · 2026-09-11T00:27:08.000Z)–21:27:38 10/09/2026 BRT (epoch 1789086458000 · 2026-09-11T00:27:38.000Z) (last_seen do achado) última leva de falhas, agora "no metrics returned from resource metrics API" (pod do `metrics-server` recém-substituído, sem scrape completo ainda).

### Evidências
- [Events Explorer — FailedComputeMetricsReplicas em medprev-rest-api](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20FailedComputeMetricsReplicas&from_ts=1788803749711&to_ts=1789149349711&live=false) — 75 ocorrências (`aggregate_events`, mesma janela).
- Query `source:kubernetes env:production kube_cluster_name:eks-medprev-online-prd status:warn (FailedComputeMetricsReplicas OR FailedGetResourceMetric)`, mesma janela — 1362 ocorrências no cluster inteiro (sem link pronto, consulta direta).
- Query `service:medprev-rest-api status:error`, agrupada por `@error.handling`/`@http.status_code`, mesma janela — 110 spans, 100% `handled`/404 (`aggregate_spans`, sem link pronto).
- Query `source:kubernetes env:production kube_cluster_name:eks-medprev-online-prd kube_namespace:kube-system metrics-server`, mesma janela — 25 eventos mostrando o ciclo `Nominated`→`Killing`→`SuccessfulCreate`/`Scheduled`/`Started` em nodes diferentes (sem link pronto, consulta direta).

### Ação recomendada
Infra — sem repositório de código do `medprev-rest-api` envolvido; a mudança é no manifesto do `metrics-server` (provavelmente em `Medprev/medprev-cloud-iac`, Terraform/Helm do addon `metrics-server` do EKS): (1) aumentar `replicas` para ≥2 com `podAntiAffinity`/`topologySpreadConstraints` entre nodes/zonas; (2) adicionar um `PodDisruptionBudget` (`minAvailable: 1`) para o Deployment `metrics-server`; (3) avaliar anotação/label para reduzir a prioridade desse pod na consolidação do Karpenter (`karpenter.sh/do-not-disrupt` ou nodepool dedicado para add-ons críticos). Validar monitorando, pelas próximas 2 semanas, se `FailedComputeMetricsReplicas`/`FailedGetResourceMetric` somem do cluster mesmo durante ciclos de consolidação do Karpenter (repetir a query cluster-wide acima).

### Volume
75 ocorrências entre `window_from` (14:55:49 07/09/2026 BRT · epoch 1788803749711 · 14:55:49 07/09/2026 BRT (epoch 1788803749711 · 2026-09-07T17:55:49.711Z)) e `window_to` (14:55:49 11/09/2026 BRT · epoch 1789149349711 · 14:55:49 11/09/2026 BRT (epoch 1789149349711 · 2026-09-11T17:55:49.711Z)) — confirmado (`aggregate_events`, mesma query e janela). Na mesma janela, sem o filtro de namespace, a mesma classe de falha ocorre 1362 vezes em todo o cluster.

### Severidade e criticidade
`severity` do achado é `medium`, mas essa severidade não se aplica ao `medprev-rest-api` em si (o serviço não teve nenhum erro `unhandled` correlacionado). A criticidade real está no defeito de infraestrutura encontrado: **inferência** — a falta de HA no `metrics-server` interrompe o autoscaling de CPU/memória de todos os HPAs do cluster (1362 ocorrências cluster-wide na mesma janela) a cada consolidação de node feita pelo Karpenter, o que é potencialmente mais grave do que a severidade `medium` original sugere, pois afeta a capacidade de resposta a picos de carga de todos os serviços com HPA, não só o `medprev-rest-api`.
