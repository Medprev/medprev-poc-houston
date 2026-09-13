---
fingerprint: k8s-eks-medprev-online-prd-Unhealthy-kube-system
source: kubernetes
reason: Unhealthy
novelty: new
service: kube-system
environment: production
window:
  from: 1788808256645
  to: 1789153856645
observed:
  count: 18
  first_seen: 1788840164000
  last_seen: 1789113619000
severity: medium
state: new
cost:
  input_tokens: 334114
  output_tokens: 9035
  cache_read_input_tokens: 238731
  cache_creation_input_tokens: 95375
  duration_s: 92.362
  usd: 0.5242112000000001
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Akube-system%20Unhealthy&from_ts=1788808256645&to_ts=1789153856645&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Akube-system%20Unhealthy&from_ts=1788808256645&to_ts=1789153856645&live=false

## Causa raiz

O achado agrupa 20 eventos `Unhealthy` (falha de readiness/liveness probe) espalhados por 20 pods diferentes do namespace `kube-system` no cluster `eks-medprev-online-prd`, entre 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) e 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z). Não há um workload único falhando repetidamente: os pods afetados são `ebs-csi-node-*`, `efs-csi-node-*`, `argo-rollouts-*`, `sealed-secrets-controller-*`, `metrics-server-*`, `reloader-*` e `aws-node-*`, cada um aparecendo 1 vez (3 nós tiveram 2 ocorrências, o restante 1), em 17 nós distintos.

Consultei os eventos `NetworkNotReady`/`NetworkPluginNotReady` (cni plugin not initialized) no mesmo namespace e janela: 45 ocorrências, e em pelo menos 3 casos o próprio evento agregado do kubelet traz `NetworkNotReady` e `Unhealthy` juntos, no mesmo pod, no mesmo minuto — por exemplo `ebs-csi-node-2crv9` em 22:03:02 09/09/2026 BRT (epoch 1789002182000 · 2026-09-10T01:03:02.000Z) e `ebs-csi-node-tmkmd` em 22:29:15 09/09/2026 BRT (epoch 1789003755000 · 2026-09-10T01:29:15.000Z). Nos demais casos, um evento `NetworkNotReady` no mesmo `kube_node` antecede o `Unhealthy` em segundos a poucos minutos. Isso é o padrão esperado de bootstrap de nó no Karpenter: o nó sobe, o daemonset do CNI (`aws-node`) ainda não terminou de inicializar a rede, e os demais daemonsets agendados no mesmo nó (que também rodam antes do CNI estar pronto) falham suas probes de readiness/liveness por `connection refused` até o CNI ficar pronto — sem repetição no mesmo pod depois disso.

Não consultei logs/spans de aplicação porque `kube-system` é infraestrutura, sem serviço APM associado: `search_datadog_logs` com `kube_namespace:kube-system source:kubernetes status:error` na janela retornou 0 resultados, e `search_datadog_spans` com `env:production kube_namespace:kube-system` também retornou 0 (nenhum span existe para este namespace — resultado válido, não erro de consulta).

Classificação: **ruído operacional esperado**, não bug de aplicação — é o comportamento normal do ciclo de vida de nós gerenciados por Karpenter, sem `@error.handling` para medir (não é um evento de Error Tracking), mas evidenciado por 20 pods distintos com 1 ocorrência isolada cada, sem recorrência, correlacionados a bootstrap de rede. O defeito real a reportar é o "ruído" em si — os probes desses DaemonSets de infraestrutura não toleram a janela de inicialização do CNI, gerando alertas repetidos de baixo valor sempre que o Karpenter escala/substitui nós.

## Linha do tempo

- 01:02:44 08/09/2026 BRT (epoch 1788840164000 · 2026-09-08T04:02:44.000Z) — `first_seen` do achado: `Unhealthy` (readiness, connection refused porta 8090) em `argo-rollouts-54847d6f8d-gkf7q`, nó `ip-10-0-6-170`. Consulta: `source:kubernetes env:production status:warn kube_namespace:kube-system Unhealthy`.
- 01:01:01 08/09/2026 BRT (epoch 1788840061000 · 2026-09-08T04:01:01.000Z)–01:02:25 08/09/2026 BRT (epoch 1788840145000 · 2026-09-08T04:02:25.000Z) — `NetworkNotReady` (cni plugin not initialized) em `ebs-csi-node-k942m` e `ebs-csi-node-tzbzd`, nós distintos, minutos antes do evento acima no mesmo cluster — consulta correlacionada: `source:kubernetes env:production kube_namespace:kube-system (NetworkNotReady OR Starting OR NodeReady)`.
- 00:22:38 09/09/2026 BRT (epoch 1788924158000 · 2026-09-09T03:22:38.000Z) — `Unhealthy` (liveness+readiness, porta 8080) em `sealed-secrets-controller-7c7f98dbd7-z8z86`.
- 00:31:47 09/09/2026 BRT (epoch 1788924707000 · 2026-09-09T03:31:47.000Z)–00:35:43 09/09/2026 BRT (epoch 1788924943000 · 2026-09-09T03:35:43.000Z) — sequência de `NetworkNotReady` em `ebs-csi-node-v62mg`, `ebs-csi-node-j59kz`, `ebs-csi-node-bf4wt`, seguida por `Unhealthy` em `argo-rollouts-54847d6f8d-wqxqw` (00:32:47 09/09/2026 BRT (epoch 1788924767000 · 2026-09-09T03:32:47.000Z)), `ebs-csi-node-j59kz` (00:34:03 09/09/2026 BRT (epoch 1788924843000 · 2026-09-09T03:34:03.000Z)) e `efs-csi-node-hq847` (00:36:57 09/09/2026 BRT (epoch 1788925017000 · 2026-09-09T03:36:57.000Z)) — mesmo padrão de bootstrap de nó.
- 03:45:25 09/09/2026 BRT (epoch 1788936325000 · 2026-09-09T06:45:25.000Z) — `Unhealthy` (readiness, porta 10250/readyz) em `metrics-server-6bcb764664-s4gbm`.
- 07:30:31 09/09/2026 BRT (epoch 1788949831000 · 2026-09-09T10:30:31.000Z)–07:54:53 09/09/2026 BRT (epoch 1788951293000 · 2026-09-09T10:54:53.000Z) — novo lote correlacionado: `NetworkNotReady` em `ebs-csi-node-c5425`, `ebs-csi-node-7wrpb`, `ebs-csi-node-jcsgw`, seguido por `Unhealthy` em `ebs-csi-node-c5425` (07:30:50 09/09/2026 BRT (epoch 1788949850000 · 2026-09-09T10:30:50.000Z)), `efs-csi-node-xtnsp` (07:38:19 09/09/2026 BRT (epoch 1788950299000 · 2026-09-09T10:38:19.000Z)) e `metrics-server-6bcb764664-zjgf5` (07:54:36 09/09/2026 BRT (epoch 1788951276000 · 2026-09-09T10:54:36.000Z)).
- 22:03:02 09/09/2026 BRT (epoch 1789002182000 · 2026-09-10T01:03:02.000Z) — evento único combinando `NetworkNotReady` (34x) e `Unhealthy` (1x) no mesmo pod `ebs-csi-node-2crv9`.
- 22:28:29 09/09/2026 BRT (epoch 1789003709000 · 2026-09-10T01:28:29.000Z) e 22:29:15 09/09/2026 BRT (epoch 1789003755000 · 2026-09-10T01:29:15.000Z) — `Unhealthy` em `sealed-secrets-controller-7c7f98dbd7-qkhwm` e `ebs-csi-node-tmkmd` (este último junto com 21x `NetworkNotReady` no mesmo registro).
- 01:33:52 10/09/2026 BRT (epoch 1789014832000 · 2026-09-10T04:33:52.000Z) — `Unhealthy` (readiness, porta 9090) em `reloader-reloader-7776875fd6-7jc6x`, precedido por `NetworkNotReady` em `ebs-csi-node-hl2lx` (01:33:17 10/09/2026 BRT (epoch 1789014797000 · 2026-09-10T04:33:17.000Z)).
- 01:55:14 10/09/2026 BRT (epoch 1789016114000 · 2026-09-10T04:55:14.000Z) — `Unhealthy` em `argo-rollouts-54847d6f8d-m9wpw`.
- 21:44:23 10/09/2026 BRT (epoch 1789087463000 · 2026-09-11T00:44:23.000Z), 21:45:43 10/09/2026 BRT (epoch 1789087543000 · 2026-09-11T00:45:43.000Z), 21:55:34 10/09/2026 BRT (epoch 1789088134000 · 2026-09-11T00:55:34.000Z), 23:42:00 10/09/2026 BRT (epoch 1789094520000 · 2026-09-11T02:42:00.000Z) — `Unhealthy` em `argo-rollouts-54847d6f8d-vzk7j`, `sealed-secrets-controller-7c7f98dbd7-w4rbb`, `aws-node-x7tbs` e `argo-rollouts-54847d6f8d-nbcjc`, todos em nós/hosts diferentes.
- 05:00:19 11/09/2026 BRT (epoch 1789113619000 · 2026-09-11T08:00:19.000Z) — `last_seen` do achado: `Unhealthy` (liveness, HTTP 500) em `efs-csi-node-wn8bp`, nó `ip-10-0-6-128`.

## Evidência

- 20 eventos `Unhealthy` retornados na janela exata do achado, cada um em pod/nó distinto (3 nós com 2 ocorrências, os demais com 1): [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Akube-system%20Unhealthy&from_ts=1788808256645&to_ts=1789153856645&live=false).
- `observed_count` do achado é 18 na mesma janela — minha consulta com a mesma query e mesma janela retornou 20; a diferença provavelmente vem de deduplicação/coleta interna do houston (ex.: eventos agregados vs. individuais no mesmo minuto), não de janelas diferentes, já que usei exatamente `window_from_ms`/`window_to_ms`. Registro a divergência sem inventar causa.
- Agregação por host: 17 hosts distintos, nenhum concentrando volume (máximo 2 ocorrências) — consulta `aggregate_events` com `group_by: host` na mesma janela.
- Correlação com bootstrap de rede: consulta `source:kubernetes env:production kube_namespace:kube-system (NetworkNotReady OR Starting OR NodeReady)` na mesma janela retornou 45 eventos, vários coincidindo (mesmo pod, mesmo minuto) ou imediatamente antes de eventos `Unhealthy`.
- Logs de aplicação: `search_datadog_logs` com `kube_namespace:kube-system source:kubernetes status:error` na janela — 0 resultados.
- Spans/traces: `search_datadog_spans` com `env:production kube_namespace:kube-system` na janela — 0 resultados (sem spans para este namespace).

## Ação recomendada

Não há bug de código a corrigir (infra, `target_repo: null`); revisar via IaC (`medprev-cloud-iac`) o `initialDelaySeconds`/`failureThreshold` dos probes dos DaemonSets `ebs-csi-node`, `efs-csi-node`, `argo-rollouts` e `sealed-secrets-controller` para tolerar a janela de inicialização do VPC CNI em nós recém-provisionados pelo Karpenter, e considerar suprimir/ajustar o monitor Kubernetes-events para não gerar achado a cada substituição de nó.

## Corpo da issue

### Descrição do incidente
Entre 01:02:44 08/09/2026 BRT (epoch 1788840164000 · 2026-09-08T04:02:44.000Z) e 05:00:19 11/09/2026 BRT (epoch 1789113619000 · 2026-09-11T08:00:19.000Z), o cluster `eks-medprev-online-prd` registrou 18-20 eventos `Unhealthy` (falha de readiness/liveness probe) no namespace `kube-system`, espalhados por 20 pods distintos (DaemonSets `ebs-csi-node`, `efs-csi-node`, `argo-rollouts`, `sealed-secrets-controller`, `metrics-server`, `reloader`, `aws-node`) em 17 nós diferentes. Nenhum pod repete a falha de forma persistente. Impacto observável: nenhum — são falhas transitórias de probe que se autocorrigem, sem indisponibilidade sustentada relatada.

### Causa raiz
Ruído operacional esperado — 20 pods distintos com no máximo 1-2 ocorrências isoladas cada, sem recorrência (não há classificação handled/unhandled aplicável a eventos Kubernetes, mas o padrão de "um único evento por pod, nunca repetido") indica comportamento transitório, não bug. Causa provável (correlacionada, não formalmente confirmada por acesso a logs de nó): bootstrap de novos nós pelo Karpenter — o CNI (`aws-node`) leva alguns segundos para inicializar a rede do nó, e outros DaemonSets agendados no mesmo nó falham suas probes até o CNI ficar pronto. Evidência: 45 eventos `NetworkNotReady`/`cni plugin not initialized` na mesma janela, vários coincidindo com os eventos `Unhealthy` no mesmo pod/minuto.

### Linha do tempo
- 01:01:01 08/09/2026 BRT (epoch 1788840061000 · 2026-09-08T04:01:01.000Z)–01:02:44 08/09/2026 BRT (epoch 1788840164000 · 2026-09-08T04:02:44.000Z): `NetworkNotReady` em nós novos, seguido do primeiro `Unhealthy` (`argo-rollouts-54847d6f8d-gkf7q`).
- 00:22:38 09/09/2026 BRT (epoch 1788924158000 · 2026-09-09T03:22:38.000Z) a 03:45:25 09/09/2026 BRT (epoch 1788936325000 · 2026-09-09T06:45:25.000Z): lote de `NetworkNotReady` + `Unhealthy` correlacionados em `argo-rollouts`, `ebs-csi-node`, `efs-csi-node`, `metrics-server`.
- 07:30:31 09/09/2026 BRT (epoch 1788949831000 · 2026-09-09T10:30:31.000Z)–07:54:53 09/09/2026 BRT (epoch 1788951293000 · 2026-09-09T10:54:53.000Z): segundo lote, mesmo padrão.
- 22:03:02 09/09/2026 BRT (epoch 1789002182000 · 2026-09-10T01:03:02.000Z) e 22:29:15 09/09/2026 BRT (epoch 1789003755000 · 2026-09-10T01:29:15.000Z): eventos combinados `NetworkNotReady`+`Unhealthy` no mesmo registro/pod.
- 01:33:17 10/09/2026 BRT (epoch 1789014797000 · 2026-09-10T04:33:17.000Z)–01:55:14 10/09/2026 BRT (epoch 1789016114000 · 2026-09-10T04:55:14.000Z): `reloader` e `argo-rollouts` afetados.
- 21:44:23 10/09/2026 BRT (epoch 1789087463000 · 2026-09-11T00:44:23.000Z)–23:42:00 10/09/2026 BRT (epoch 1789094520000 · 2026-09-11T02:42:00.000Z): `argo-rollouts`, `sealed-secrets-controller`, `aws-node` afetados.
- 05:00:19 11/09/2026 BRT (epoch 1789113619000 · 2026-09-11T08:00:19.000Z): último evento (`efs-csi-node-wn8bp`, liveness HTTP 500).

### Evidências
- [Events Explorer — Unhealthy kube-system](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Akube-system%20Unhealthy&from_ts=1788808256645&to_ts=1789153856645&live=false)
- Consulta de correlação executada (sem link direto pronto): `source:kubernetes env:production kube_namespace:kube-system (NetworkNotReady OR Starting OR NodeReady)`, janela 1788808256645–1789153856645, 45 resultados.
- `search_datadog_logs`: `kube_namespace:kube-system source:kubernetes status:error`, mesma janela, 0 resultados.
- `search_datadog_spans`: `env:production kube_namespace:kube-system`, mesma janela, 0 resultados.

### Ação recomendada
Infra — sem repositório de código, ação operacional em `Medprev/medprev-cloud-iac` (Terraform/EKS): revisar `readinessProbe.initialDelaySeconds` e `failureThreshold` dos DaemonSets `aws-ebs-csi-driver`, `aws-efs-csi-driver`, `argo-rollouts`, `sealed-secrets-controller` no manifesto/Helm values gerenciado por IaC, aumentando a tolerância à janela de bootstrap do CNI em nós Karpenter recém-provisionados. Validar rodando `houston run` novamente após o ajuste e confirmando queda no volume de eventos `Unhealthy` correlacionados a `NetworkNotReady` na mesma janela de 4 dias.

### Volume
18 ocorrências entre 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) e 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z), segundo o achado (`observed_count`). Minha consulta direta ao Datadog na mesma janela retornou 20 — divergência não explicada por diferença de janela; provavelmente deduplicação na coleta do houston.

### Severidade e criticidade
`severity: medium` no achado, mas não se aplica ao erro em si, já que a classificação é ruído/comportamento esperado de infraestrutura. Criticidade do defeito real (probes mal calibrados para bootstrap de CNI): **baixa** (inferência) — gera ruído recorrente em Error Tracking/monitoramento e pode mascarar problemas reais de rede se o volume aumentar, mas não há evidência de indisponibilidade de workload observada nesta janela.
