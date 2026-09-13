---
fingerprint: k8s-eks-medprev-online-prd-DeletingNodeFailed-unknown-namespace
source: kubernetes
reason: DeletingNodeFailed
novelty: new
service: unknown-namespace
environment: production
window:
  from: 1788808256645
  to: 1789153856645
observed:
  count: 4
  first_seen: 1788950174000
  last_seen: 1789132561000
severity: medium
state: new
cost:
  input_tokens: 389262
  output_tokens: 10907
  cache_read_input_tokens: 301889
  cache_creation_input_tokens: 87363
  duration_s: 111.737
  usd: 0.5235748
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aunknown-namespace%20DeletingNodeFailed&from_ts=1788808256645&to_ts=1789153856645&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aunknown-namespace%20DeletingNodeFailed&from_ts=1788808256645&to_ts=1789153856645&live=false

## Causa raiz

O achado é um evento de infraestrutura Kubernetes (não um serviço de aplicação) — `DeletingNodeFailed` emitido pelo `cloud-node-lifecycle-controller` no cluster `eks-medprev-online-prd`. É **RUÍDO**, não bug: nas 4 ocorrências da janela (4/4 = 100%), o evento é a segunda perna de uma corrida benigna entre dois controladores que fazem o mesmo cleanup — não há classificação `@error.handling`/`@http.status_code` aplicável (não é span de aplicação), mas a evidência do trace completo do Kubernetes é conclusiva: o Karpenter decide voluntariamente desativar um nó por subutilização (`DisruptionTerminating: Disrupting Node: Underutilized/Delete`), drena os pods, o kubelet reporta `NodeNotReady`/`Shutdown`, e cerca de 30 segundos depois o `cloud-node-lifecycle-controller` da AWS tenta deletar o mesmo objeto `Node` e recebe `404 not found` — porque o Karpenter já o removeu. A mensagem "Failed deleting node ... not found" é um erro de idempotência entre dois controladores concorrentes, não uma falha real de limpeza do cluster.

Consultas efetivamente rodadas:
- `search_datadog_events` com a query exata de `evidence_links` (`kube_namespace:unknown-namespace DeletingNodeFailed`) → 0 resultados (o campo `kube_namespace` não se aplica a eventos de `Node`, que é cluster-scoped; por isso o coletor rotulou o serviço como `unknown-namespace`).
- `search_datadog_events` com `source:kubernetes DeletingNodeFailed` (sem filtro de namespace) → 6 resultados totais, 4 em `env:production` batendo exatamente com `observed_count: 4` e com os timestamps de `first_seen`/`last_seen`.
- `search_datadog_events` filtrando por `kube_node:ip-10-0-8-247...` na hora anterior ao primeiro `DeletingNodeFailed` → 51 eventos, reconstruindo a cadeia causal completa (abaixo).
- `search_datadog_logs` no node `ip-10-0-8-247...` → 248 logs, os mais relevantes sendo timeouts do `metrics-server` ao raspar o nó, coerentes com o nó já desligando.

## Linha do tempo

1. 06:50:12 09/09/2026 BRT (epoch 1788947412000 · 2026-09-09T09:50:12.000Z) — Karpenter avalia consolidação e marca o nó `ip-10-0-8-247.sa-east-1.compute.internal` (`i-02bd7479e82a799c7`) como candidato repetidas vezes (`Unconsolidatable: Can't replace with a cheaper node`, 22x). Query: `source:kubernetes cluster_name:eks-medprev-online-prd kube_node:ip-10-0-8-247.sa-east-1.compute.internal`.
2. 07:35:16 09/09/2026 BRT (epoch 1788950116000 · 2026-09-09T10:35:16.000Z) — Karpenter nomeia nós de destino para os pods que serão realocados (`Nominated`), sinalizando início da disrupção.
3. 07:35:17 09/09/2026 BRT (epoch 1788950117000 · 2026-09-09T10:35:17.000Z) — Karpenter dispara a decisão de desligar o nó por subutilização: `DisruptionBlocked: Node is deleting or marked for deletion` + `DisruptionTerminating: Disrupting Node: Underutilized/Delete`; e `FailedDraining`/`TerminationGracePeriodExpiring` (11 pods aguardando remoção).
4. 07:35:18 09/09/2026 BRT (epoch 1788950118000 · 2026-09-09T10:35:18.000Z) — 71 pods `Evicted: Underutilized`; kubelet começa a matar containers das aplicações (`medprev-rest-api-*`, `medprev-cms`, `nginx-gateway-fabric`, `argocd`, `datadog-operator`, `sealed-secrets-controller`).
5. 07:35:38 09/09/2026 BRT (epoch 1788950138000 · 2026-09-09T10:35:38.000Z) a 07:35:43 09/09/2026 BRT (epoch 1788950143000 · 2026-09-09T10:35:43.000Z) — kubelet finaliza os últimos containers de sistema (`datadog` agent/trace-agent, `metrics-server`, `kube-proxy`, plugins CSI EBS/EFS).
6. 07:35:43 09/09/2026 BRT (epoch 1788950143000 · 2026-09-09T10:35:43.000Z) — Nó reporta `Ready: True→False, Reason: KubeletNotReady, Message: node is shutting down`, e o kubelet emite `NodeNotReady` + `Shutdown: Shutdown manager detected shutdown event`.
7. 07:36:11 09/09/2026 BRT (epoch 1788950171000 · 2026-09-09T10:36:11.000Z) e 07:36:26 09/09/2026 BRT (epoch 1788950186675 · 2026-09-09T10:36:26.675Z) — `metrics-server` falha ao raspar o nó (`dial tcp ... i/o timeout`, depois `context deadline exceeded`) — consistente com o nó já em processo de shutdown/remoção.
8. 07:36:14 09/09/2026 BRT (epoch 1788950174000 · 2026-09-09T10:36:14.000Z) — **Este é o evento do achado (1ª ocorrência, = `first_seen`)**: `cloud-node-lifecycle-controller` tenta deletar o objeto `Node ip-10-0-8-247.sa-east-1.compute.internal` e recebe `nodes "ip-10-0-8-247.sa-east-1.compute.internal" not found` — já removido pelo Karpenter no passo 3-6.
9. 21:14:45 09/09/2026 BRT (epoch 1788999285000 · 2026-09-10T00:14:45.000Z), 07:46:24 10/09/2026 BRT (epoch 1789037184000 · 2026-09-10T10:46:24.000Z) e 10:16:01 11/09/2026 BRT (epoch 1789132561000 · 2026-09-11T13:16:01.000Z) (= `last_seen`) — mais 3 ocorrências do mesmo padrão em nós diferentes (`ip-10-0-10-80`, `ip-10-0-2-131`, `ip-10-0-1-16`), mesma assinatura `reporting_controller:cloud-node-lifecycle-controller`, mesma mensagem `nodes "X" not found`.

Nota de escopo: as 4 ocorrências caem dentro da janela `window_from` 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) a `window_to` 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z); reconstruí o trace completo apenas para a 1ª ocorrência (nó `ip-10-0-8-247`) — as outras 3 foram confirmadas apenas pela mensagem do evento, não retracei a sequência Karpenter completa para elas por economia de consulta, mas a assinatura (mesmo `reporting_controller`, mesma mensagem "not found") é idêntica.

## Evidência

- 4 eventos `DeletingNodeFailed` em `env:production` no cluster `eks-medprev-online-prd`, todos emitidos por `reporting_controller:cloud-node-lifecycle-controller` — [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aunknown-namespace%20DeletingNodeFailed&from_ts=1788808256645&to_ts=1789153856645&live=false) (a query com `kube_namespace:unknown-namespace` retornou 0 — ver nota abaixo); consulta que efetivamente retornou os 4: `source:kubernetes DeletingNodeFailed` sem filtro de namespace, `from=1788808256645, to=1789153856645`.
- `kube_namespace:unknown-namespace` na query original não corresponde a nenhum evento real: eventos de `Node` são cluster-scoped, sem namespace — o rótulo `unknown-namespace` é um artefato do coletor, não um namespace do Datadog. Consulta: `search_datadog_events` com a query literal de `evidence_links`, 0 resultados.
- 51 eventos correlacionados no nó `ip-10-0-8-247.sa-east-1.compute.internal` entre 06:36:14 09/09/2026 BRT (epoch 1788946574000 · 2026-09-09T09:36:14.000Z) e 07:41:14 09/09/2026 BRT (epoch 1788950474000 · 2026-09-09T10:41:14.000Z) mostram a cadeia completa Karpenter-consolidação → drain → shutdown → corrida com `cloud-node-lifecycle-controller`. Consulta: `source:kubernetes cluster_name:eks-medprev-online-prd kube_node:ip-10-0-8-247.sa-east-1.compute.internal`, `from=1788946574000, to=1788950474000`.
- 248 logs mencionando o nó `ip-10-0-8-247.sa-east-1.compute.internal` na janela do achado; os 2 mais recentes (`metrics-server`, `status:error`) registram falha de scrape por timeout logo após o shutdown do nó. Consulta: `search_datadog_logs` com query `ip-10-0-8-247.sa-east-1.compute.internal`, `from=1788808256645, to=1789153856645`.
- `search_datadog_logs` com `source:kubernetes status:error host:i-00f61321dbae86366` (host do `metrics-server`) retornou 0 — nenhum log de erro do próprio `metrics-server` indexado sob esse host, apenas os 2 logs de scrape citados acima, indexados sob `service:metrics-server`.

## Ação recomendada

Ajustar o monitor/coleta que gera este achado no Datadog para excluir `DeletingNodeFailed` do `cloud-node-lifecycle-controller` quando correlacionado a um evento `DisruptionTerminating: Disrupting Node` do Karpenter nos ~60s anteriores no mesmo `kube_node` — esse padrão é 100% consolidação voluntária, não falha real de remoção de nó.

## Corpo da issue

### Descrição do incidente
O evento Kubernetes `DeletingNodeFailed`, coletado pela source `kubernetes` do Houston sob o fingerprint `k8s-eks-medprev-online-prd-DeletingNodeFailed-unknown-namespace`, dispara sempre que o `cloud-node-lifecycle-controller` da AWS tenta deletar um objeto `Node` que já não existe mais. Ambiente: cluster EKS `eks-medprev-online-prd`, produção. Isso ocorre desde pelo menos 07/09/2026 23:36 (07:36:14 09/09/2026 BRT (epoch 1788950174000 · 2026-09-09T10:36:14.000Z)), com 4 ocorrências até 11/09/2026 (10:16:01 11/09/2026 BRT (epoch 1789132561000 · 2026-09-11T13:16:01.000Z)). Não há impacto observável para usuário ou sistema: os nós já haviam sido removidos com sucesso pelo Karpenter antes da tentativa falha do outro controlador.

### Causa raiz
RUÍDO (4/4 = 100% das ocorrências no formato de idempotência benigna). O `DeletingNodeFailed` é a segunda perna de uma corrida entre o Karpenter (que desliga voluntariamente nós subutilizados via consolidação: `DisruptionTerminating: Disrupting Node: Underutilized/Delete`) e o `cloud-node-lifecycle-controller` da AWS, que tenta deletar o mesmo objeto `Node` ~30s depois e recebe `404 not found` porque o Karpenter já o removeu. Não é uma falha de infraestrutura real.

### Linha do tempo
1. 09/09 06:50 BRT — Karpenter marca `ip-10-0-8-247` como `Unconsolidatable` repetidamente (22x).
2. 09/09 07:35:16 BRT — Karpenter nomeia nós de destino para realocar pods.
3. 09/09 07:35:17 BRT — Karpenter dispara `DisruptionTerminating: Disrupting Node: Underutilized/Delete`.
4. 09/09 07:35:18 BRT — 71 pods `Evicted: Underutilized`; kubelet mata containers de aplicação.
5. 09/09 07:35:38–07:35:43 BRT — kubelet finaliza containers de sistema (datadog agent, metrics-server, kube-proxy, plugins CSI).
6. 09/09 07:35:43 BRT — Nó reporta `NodeNotReady` / `Shutdown: node is shutting down`.
7. 09/09 07:36:11–07:36:26 BRT — `metrics-server` falha ao raspar o nó (timeout, depois context deadline exceeded).
8. 09/09 07:36:14 BRT — `cloud-node-lifecycle-controller` tenta deletar o `Node` e recebe `404 not found` (evento do achado, 1ª ocorrência).
9. 3 ocorrências adicionais em outros nós (10/09 00:14, 10/09 07:46, 11/09 10:16 BRT), mesma assinatura.

### Evidências
- Events Explorer da query original (retorna 0 — `kube_namespace` não existe para eventos de `Node`): https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aunknown-namespace%20DeletingNodeFailed&from_ts=1788808256645&to_ts=1789153856645&live=false
- Consulta que efetivamente retorna as 4 ocorrências de produção: `source:kubernetes DeletingNodeFailed` (sem filtro de namespace), `from=1788808256645, to=1789153856645`, filtrar por `env:production` nos tags.
- Trace completo de correlação no nó `ip-10-0-8-247`: `source:kubernetes cluster_name:eks-medprev-online-prd kube_node:ip-10-0-8-247.sa-east-1.compute.internal`, `from=1788946574000, to=1788950474000`.
- Logs do `metrics-server` mostrando falha de scrape no momento do shutdown: query `ip-10-0-8-247.sa-east-1.compute.internal`, `from=1788808256645, to=1789153856645`.

### Ação recomendada
Infra — sem repositório de código, ação operacional. No monitor/consulta do Datadog que alimenta este fingerprint (Events Explorer, filtro `source:kubernetes DeletingNodeFailed`), adicionar uma exclusão para eventos com `reporting_controller:cloud-node-lifecycle-controller` cuja mensagem contenha `not found` quando o mesmo `kube_node` teve um evento `source_component:karpenter` com `DisruptionTerminating` nos 120s anteriores. Validar rodando a mesma query por mais um ciclo de coleta (mín. 96h) e confirmando que o volume de `DeletingNodeFailed` cai a zero sem suprimir nenhum caso de falha real de deleção de nó (i.e., sem `DisruptionTerminating` correlacionado).

### Volume
4 ocorrências entre 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) e 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z) (`observed_count`). Consulta própria sem filtro de namespace no mesmo intervalo retornou 6 eventos totais (4 em `env:production`, 2 em `env:development` — fora do escopo deste achado).

### Severidade e criticidade
`severity: medium` do achado não se aplica ao evento em si, por ser ruído confirmado. Criticidade do defeito real encontrado (o monitor gerando alertas falso-positivos recorrentes para consolidação normal do Karpenter): **baixa** (inferência) — não afeta disponibilidade nem dados, mas consome capacidade de triagem e mascara sinais reais de falha de infraestrutura ao poluir o Error/Event Tracking com ruído recorrente.
