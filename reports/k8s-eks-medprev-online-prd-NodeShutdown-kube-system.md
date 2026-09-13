---
fingerprint: k8s-eks-medprev-online-prd-NodeShutdown-kube-system
source: kubernetes
reason: NodeShutdown
novelty: new
service: kube-system
environment: production
window:
  from: 1788785777322
  to: 1789131377322
observed:
  count: 352
  first_seen: 1788821631000
  last_seen: 1789123851000
severity: medium
state: new
cost:
  input_tokens: 526298
  output_tokens: 8384
  cache_read_input_tokens: 440348
  cache_creation_input_tokens: 85938
  duration_s: 94.336
  usd: 0.5202686
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Akube-system%20NodeShutdown&from_ts=1788785777322&to_ts=1789131377322&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Akube-system%20NodeShutdown&from_ts=1788785777322&to_ts=1789131377322&live=false

## Causa raiz

O achado é do namespace de infraestrutura `kube-system` no cluster EKS `eks-medprev-online-prd` — não há um serviço de aplicação nem repositório de código associado (`target_repo: null`). O evento `NodeShutdown` é emitido pelo kubelet quando um Pod é rejeitado porque o nó em que ele rodava está sendo desligado. Consultei `search_datadog_events` com a query exata do achado na janela de coleta e depois agreguei por `kube_node`: são **352 ocorrências entre 09:56:17 07/09/2026 BRT (epoch 1788785777322 · 2026-09-07T12:56:17.322Z) e 09:56:17 11/09/2026 BRT (epoch 1789131377322 · 2026-09-11T12:56:17.322Z)**, distribuídas por **84 nós distintos**, com 2 a 7 ocorrências por nó — exatamente o número de DaemonSets do `kube-system` (`aws-node`, `kube-proxy`, `eks-pod-identity-agent`, `efs-csi-node`, `ebs-csi-node`) que rodam em cada nó. Todos os eventos carregam a tag `karpenter_nodepool:default`.

Isso é **RUÍDO**: é o padrão esperado de rotação de nós gerenciada pelo Karpenter (consolidação/substituição de nós spot ou por bin-packing) — cada substituição de nó dispara de 2 a 7 eventos `NodeShutdown` (um por Pod de DaemonSet no nó que está saindo), e o volume de 352 eventos em 84 nós ao longo de 4 dias é consistente com esse ciclo de vida normal, não com uma falha. Não existe aqui a divisão `handled`/`unhandled` (esse atributo é de spans de APM, não se aplica a eventos Kubernetes) — a classificação está baseada no padrão de agrupamento por `kube_node` e na tag `karpenter_nodepool`.

Consultas efetivamente rodadas e o que cada uma devolveu:
- `search_datadog_events` (query do achado, janela fixada): 352 eventos, confirmando `observed_count`.
- `aggregate_events` agrupado por `kube_node` na mesma janela: 84 buckets, 2–7 eventos por nó.
- `search_datadog_logs` (`service:kube-system OR kube_namespace:kube-system karpenter`, mesma janela): **0 logs**.
- `search_datadog_spans` (`kube_namespace:kube-system OR service:kube-system`, mesma janela): **0 spans** — `kube-system` não emite APM, então não há `trace_id` para reconstruir um trace completo neste achado.

O que **não** foi possível determinar diretamente: não localizei um evento Karpenter/`change_tracking` explícito de "node terminated for consolidation" (a busca de logs por "karpenter" voltou vazia) — a atribuição à rotação do Karpenter é uma inferência a partir da tag `karpenter_nodepool:default` e do padrão de agrupamento, não uma confirmação por log de causa direta do scale-down.

## Linha do tempo

Passo a passo dentro da janela de coleta (352 eventos totais; lista abaixo é uma amostra representativa dos primeiros ciclos de substituição de nó, obtida via `search_datadog_events` ordenado por timestamp):

1. 19:53:51 07/09/2026 BRT (epoch 1788821631000 · 2026-09-07T22:53:51.000Z) — nó `ip-10-0-1-180.sa-east-1.compute.internal` desligando: `aws-node-wglkj`, `eks-pod-identity-agent-vw4tj` e `kube-proxy-m8qqc` rejeitados (3 eventos), tag `karpenter_nodepool:default`.
2. 20:59:47 07/09/2026 BRT (epoch 1788825587000 · 2026-09-07T23:59:47.000Z)–20:59:48 07/09/2026 BRT (epoch 1788825588000 · 2026-09-07T23:59:48.000Z) — nó `ip-10-0-2-20.sa-east-1.compute.internal` desligando: `efs-csi-node-dwbpb`, `kube-proxy-8ndrd`, `eks-pod-identity-agent-qkw98`.
3. 01:02:06 08/09/2026 BRT (epoch 1788840126000 · 2026-09-08T04:02:06.000Z) — nó `ip-10-0-7-226.sa-east-1.compute.internal` desligando: `eks-pod-identity-agent-dt9ng`, `eks-pod-identity-agent-c75nw`, `efs-csi-node-n8662`, `kube-proxy-rw476`, `aws-node-g6hxg`, `ebs-csi-node-rcwv7` (6 eventos — ciclo completo dos 5 DaemonSets do namespace).
4. 01:03:20 08/09/2026 BRT (epoch 1788840200000 · 2026-09-08T04:03:20.000Z) — nó `ip-10-0-6-170.sa-east-1.compute.internal` desligando: `eks-pod-identity-agent-6g6lr`, `kube-proxy-tjhk5`, `aws-node-dgtmd`, `efs-csi-node-r26n7`, `eks-pod-identity-agent-lbd2b`.
5. 05:20:39 08/09/2026 BRT (epoch 1788855639000 · 2026-09-08T08:20:39.000Z)–05:20:40 08/09/2026 BRT (epoch 1788855640000 · 2026-09-08T08:20:40.000Z) — nó `ip-10-0-2-247.sa-east-1.compute.internal` desligando: `eks-pod-identity-agent-dbp6p`, `aws-node-z2bd7`, `eks-pod-identity-agent-ld4m8`, `kube-proxy-klvg4`.
6. 07:02:14 08/09/2026 BRT (epoch 1788861734000 · 2026-09-08T10:02:14.000Z) — nó `ip-10-0-10-33.sa-east-1.compute.internal` desligando: `efs-csi-node-9k966`, `eks-pod-identity-agent-sxkp6`.

Esse ciclo (5–7 nós substituídos por dia, sempre os mesmos 5 DaemonSets rejeitados por nó) se repete ao longo dos 84 nós até `last_seen`: 07:50:51 11/09/2026 BRT (epoch 1789123851000 · 2026-09-11T10:50:51.000Z). `first_seen` do achado, no histórico completo (não da janela): 19:53:51 07/09/2026 BRT (epoch 1788821631000 · 2026-09-07T22:53:51.000Z).

## Evidência

- 352 ocorrências de `NodeShutdown` na janela de coleta: [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Akube-system%20NodeShutdown&from_ts=1788785777322&to_ts=1789131377322&live=false).
- 84 nós distintos afetados, 2–7 eventos por nó — consulta: `aggregate_events` com a mesma query, agrupado por `kube_node`, janela `1788785777322`–`1789131377322`.
- Todos os eventos carregam `karpenter_nodepool:default`, indicando gerenciamento por Karpenter — visível nas tags dos eventos individuais retornados pela mesma busca acima.
- Nenhum log de Karpenter/kube-system na mesma janela — consulta `search_datadog_logs` com `service:kube-system OR kube_namespace:kube-system karpenter`, 0 resultados.
- Nenhum span de APM para `kube-system` na mesma janela (não há `trace_id` disponível para este achado) — consulta `search_datadog_spans` com `kube_namespace:kube-system OR service:kube-system`, 0 resultados.

## Ação recomendada

Nenhuma ação de código: reclassificar este fingerprint como ruído esperado (rotação de nós do Karpenter) e, se o objetivo for reduzir volume no Error Tracking/Events, ajustar o monitor/filtro para não tratar `NodeShutdown` de pods de DaemonSet como sinal, em vez de investigar como bug de aplicação.

## Corpo da issue

### Descrição do incidente
O evento `NodeShutdown` do namespace `kube-system` no cluster `eks-medprev-online-prd` está sendo capturado como achado de observabilidade, mas corresponde à rejeição esperada de Pods de DaemonSet (`aws-node`, `kube-proxy`, `eks-pod-identity-agent`, `efs-csi-node`, `ebs-csi-node`) durante o desligamento normal de nós geridos pelo Karpenter (`karpenter_nodepool:default`). Não há impacto observável para usuários nem para o sistema: os Pods de DaemonSet são automaticamente reagendados no novo nó pelo próprio Kubernetes.

### Causa raiz
RUÍDO — 352 ocorrências agrupadas em 84 nós distintos, com 2 a 7 eventos por nó (um por DaemonSet local), todos com a tag `karpenter_nodepool:default`, é o padrão de rotação/consolidação de nós do Karpenter, não uma falha de aplicação. Não foi encontrado um log explícito de "consolidação Karpenter" que confirme a causa direta do desligamento de cada nó (busca por `karpenter` nos logs de `kube-system` voltou vazia) — a atribuição à rotação do Karpenter é inferência a partir do padrão de agrupamento e da tag do nodepool, não uma causa confirmada por log direto.

### Linha do tempo
- 19:53:51 07/09/2026 BRT (epoch 1788821631000 · 2026-09-07T22:53:51.000Z) — nó `ip-10-0-1-180...` desligando, 3 Pods de DaemonSet rejeitados.
- 20:59:47 07/09/2026 BRT (epoch 1788825587000 · 2026-09-07T23:59:47.000Z) — nó `ip-10-0-2-20...` desligando, 3 Pods rejeitados.
- 01:02:06 08/09/2026 BRT (epoch 1788840126000 · 2026-09-08T04:02:06.000Z) — nó `ip-10-0-7-226...` desligando, 6 Pods rejeitados (ciclo completo dos 5 DaemonSets).
- 01:03:20 08/09/2026 BRT (epoch 1788840200000 · 2026-09-08T04:03:20.000Z) — nó `ip-10-0-6-170...` desligando, 5 Pods rejeitados.
- 05:20:39 08/09/2026 BRT (epoch 1788855639000 · 2026-09-08T08:20:39.000Z) — nó `ip-10-0-2-247...` desligando, 4 Pods rejeitados.
- 07:02:14 08/09/2026 BRT (epoch 1788861734000 · 2026-09-08T10:02:14.000Z) — nó `ip-10-0-10-33...` desligando, 2 Pods rejeitados.
- Padrão repetido em 84 nós até 07:50:51 11/09/2026 BRT (epoch 1789123851000 · 2026-09-11T10:50:51.000Z) (`last_seen`).
- Sem logs de Karpenter/kube-system e sem spans de APM na mesma janela (ambas as consultas retornaram 0), então não há correlação de causa direta de scale-down além da tag `karpenter_nodepool`.

### Evidências
- [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Akube-system%20NodeShutdown&from_ts=1788785777322&to_ts=1789131377322&live=false)
- `aggregate_events` agrupado por `kube_node`, mesma query/janela: 84 nós, 2–7 eventos cada.
- `search_datadog_logs` (`service:kube-system OR kube_namespace:kube-system karpenter`), mesma janela: 0 resultados.
- `search_datadog_spans` (`kube_namespace:kube-system OR service:kube-system`), mesma janela: 0 resultados.

### Ação recomendada
Infra — sem repositório de código, ação operacional: no componente de configuração de detecção do Datadog (monitor/regra de Events Explorer que gera este fingerprint), excluir ou reclassificar como esperado o `Reason:NodeShutdown` quando o Pod pertence a um DaemonSet do `kube-system` em nó com tag `karpenter_nodepool:*` — por exemplo, adicionando um filtro de exclusão por `pod_name:(aws-node* OR kube-proxy* OR eks-pod-identity-agent* OR efs-csi-node* OR ebs-csi-node*)` na regra de coleta. Validar rodando a mesma query do achado por 7 dias após a mudança e confirmando que o volume cai a zero (ou que os eventos restantes, se houver, são de Pods não pertencentes a DaemonSets de infraestrutura, o que indicaria um caso real a investigar).

### Volume
352 ocorrências na janela `window_from`–`window_to` (09:56:17 07/09/2026 BRT · epoch 1788785777322 a 09:56:17 11/09/2026 BRT · epoch 1789131377322), confirmado por consulta direta ao Datadog na mesma janela (`aggregate_events`, total consistente com `observed_count`).

### Severidade e criticidade
`severity` do achado é `medium`, mas essa severidade não se aplica ao evento em si, já que ele foi classificado como ruído (rotação normal de nós Karpenter). O defeito real encontrado — ausência de um filtro de exclusão para `NodeShutdown` de DaemonSets de infraestrutura na regra de detecção — tem criticidade **baixa** (inferência): não afeta usuários ou dados, mas consome capacidade de triagem e cota de investigação (cada achado novo gera uma chamada `claude -p` paga) sempre que o Karpenter rotaciona um nó.
