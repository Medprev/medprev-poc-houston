---
fingerprint: k8s-eks-medprev-online-prd-NetworkNotReady-kube-system
source: kubernetes
reason: NetworkNotReady
novelty: new
service: kube-system
environment: production
window:
  from: 1788808256645
  to: 1789153856645
observed:
  count: 45
  first_seen: 1788822616000
  last_seen: 1789120203000
severity: medium
state: discarded
cost:
  input_tokens: 454606
  output_tokens: 7677
  cache_read_input_tokens: 361471
  cache_creation_input_tokens: 93125
  duration_s: 85.135
  usd: 0.5261712000000001
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Akube-system%20NetworkNotReady&from_ts=1788808256645&to_ts=1789153856645&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Akube-system%20NetworkNotReady&from_ts=1788808256645&to_ts=1789153856645&live=false

Consulta vazia: nenhum monitor (`source:alert`) disparou para `kube_namespace:kube-system` nessa janela — confirma que isso nunca virou página/alerta real. Tenho evidência suficiente para fechar a investigação.

## Causa raiz

O evento é do componente de infraestrutura `kube-system` do cluster `eks-medprev-online-prd` (Kubernetes, sem serviço de aplicação associado — `target_repo: null`). O padrão **é ruído**, não bug: consultando os 45 eventos da janela (`source:kubernetes env:production status:warn kube_namespace:kube-system NetworkNotReady`, `from_ts=1788808256645`, `to_ts=1789153856645`), eles se distribuem por 22 nós distintos (`kube_node`), cada um com 1 a 3 ocorrências (a maioria 2) concentradas em uma janela de 10 a 45 segundos — nunca uma ocorrência isolada e recorrente no mesmo nó ao longo de dias. Reconstruí o trace completo do primeiro nó (`ip-10-0-2-20.sa-east-1.compute.internal`, evento às 23:10:16 UTC de 07/09): o pod é agendado (`Scheduled`) às 20:10:08 07/09/2026 BRT (epoch 1788822608000 · 2026-09-07T23:10:08.000Z), o daemonset `ebs-csi-node` sobe antes do `aws-node` (VPC CNI) terminar de puxar imagem e iniciar container (`aws-node-vnppc` só reporta `Started` às 20:10:26 07/09/2026 BRT (epoch 1788822626000 · 2026-09-07T23:10:26.000Z)); o kubelet emite `NetworkNotReady` (`cni plugin not initialized`) exatamente nesse intervalo e nunca mais depois que o CNI termina de subir. Esse é o comportamento documentado de bootstrap de nó novo em EKS com Karpenter (VPC CNI ainda inicializando quando o kubelet já tenta rodar os daemonsets) — autolimitado, sem persistir. Nenhum monitor (`source:alert`) disparou para `kube-system` na mesma janela (consulta vazia), confirmando que isso nunca gerou página real.

## Linha do tempo

Passo a passo do primeiro ciclo completo (nó `ip-10-0-2-20`, evento âncora do achado):
- 20:10:08 07/09/2026 BRT (epoch 1788822608000 · 2026-09-07T23:10:08.000Z) — `Scheduled`: pod `ebs-csi-node-xxtf6` designado ao nó recém-provisionado. (`search_datadog_events`, `kube_node:ip-10-0-2-20...`)
- 20:10:09 07/09/2026 BRT (epoch 1788822609000 · 2026-09-07T23:10:09.000Z) — `Pulling`/`Scheduled`: `efs-csi-node-qvfvq` também agendado no mesmo nó.
- 20:10:15 07/09/2026 BRT (epoch 1788822615000 · 2026-09-07T23:10:15.000Z) — `eks-pod-identity-agent` criado/iniciado no nó.
- 20:10:16 07/09/2026 BRT (epoch 1788822616000 · 2026-09-07T23:10:16.000Z) — **1ª ocorrência do achado**: kubelet emite `NetworkNotReady` (cni plugin not initialized) — mesmo timestamp em que `kube-proxy` e `aws-node` (VPC CNI) ainda estão sendo agendados/criados no nó.
- 20:10:26 07/09/2026 BRT (epoch 1788822626000 · 2026-09-07T23:10:26.000Z) — `aws-node-vnppc` (VPC CNI) reporta `Started`, e simultaneamente ocorre a **2ª e última** `NetworkNotReady` desse nó nesta janela.
- Após 20:10:26 07/09/2026 BRT (epoch 1788822626000 · 2026-09-07T23:10:26.000Z) — nenhuma nova ocorrência de `NetworkNotReady` para esse nó pelo resto da janela: o CNI ficou pronto e o sintoma cessou.

O mesmo padrão (1–3 ocorrências, sempre nos primeiros segundos após o nó entrar no cluster, nunca depois) se repete nos outros 21 nós ao longo da janela — 08/09 04:01–13:26, 09/09 03:31–14:05, 10/09 00:10–04:33, e a última em 21:27:17 10/09/2026 BRT (epoch 1789086437000 · 2026-09-11T00:27:17.000Z) (nó `ip-10-0-4-152`). `first_seen` do achado é 20:10:16 07/09/2026 BRT (epoch 1788822616000 · 2026-09-07T23:10:16.000Z) e `last_seen` é 06:50:03 11/09/2026 BRT (epoch 1789120203000 · 2026-09-11T09:50:03.000Z) — ambos do histórico completo do achado, fora do escopo do `observed_count`.

## Evidência

- 45 ocorrências entre 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) e 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z), confirmadas por `search_datadog_events` com a query exata do achado (`count: 45` no metadado). https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Akube-system%20NetworkNotReady&from_ts=1788808256645&to_ts=1789153856645&live=false
- Distribuição por nó: 22 `kube_node` distintos, 1 a 3 eventos cada — `aggregate_events` agrupado por `kube_node`, mesma query/janela (nenhum nó concentra volume anômalo).
- Correlação de bootstrap: `search_datadog_events` em `kube_namespace:kube-system kube_node:ip-10-0-2-20...` na janela 22:50–23:20 UTC de 07/09 retornou 11 eventos — `Scheduled`, `Pulling`/`Pulled`/`Started` dos pods `ebs-csi-node`, `efs-csi-node`, `eks-pod-identity-agent`, `kube-proxy` e `aws-node` (VPC CNI), intercalados com as 2 ocorrências de `NetworkNotReady` daquele nó, mostrando que o alerta cai exatamente no intervalo em que o CNI ainda está subindo.
- Ausência de alerta real: `aggregate_events` para `source:alert env:production kube_namespace:kube-system` na mesma janela retornou 0 buckets — nenhum monitor disparou.
- Não consultei logs de aplicação nem spans porque `kube-system`/`ebs-csi-node` é infraestrutura sem instrumentação APM (`target_repo: null`) — não há serviço aplicacional com logs/traces associado a este achado; a evidência primária aqui é o próprio Events Explorer do Kubernetes.

## Ação recomendada
Nenhuma correção de código: este é ruído esperado de bootstrap de nó (CNI ainda inicializando) em escala normal de Karpenter. Se o volume incomodar o Error Tracking/triagem, a ação é ajustar a regra de dedup/severidade desse `reason` no houston (ou suprimir monitor, se algum vier a existir) para não tratar `NetworkNotReady` transitório de `kube-system` como achado acionável por padrão.

## Corpo da issue

### Descrição do incidente
O evento `NetworkNotReady` (kubelet, motivo `NetworkPluginNotReady: cni plugin not initialized`) aparece recorrentemente em pods do DaemonSet `ebs-csi-node` no namespace `kube-system` do cluster `eks-medprev-online-prd`, produção. Não há impacto observável: nenhum monitor disparou e o sintoma cessa sozinho segundos depois de cada ocorrência.

### Causa raiz
Ruído — 45/45 ocorrências (100%) na janela analisada ocorrem em nós recém-provisionados (Karpenter), sempre nos primeiros ~10–45 segundos após o `Scheduled` do pod, e cessam assim que o pod `aws-node` (VPC CNI) termina de subir no mesmo nó (confirmado no trace do nó `ip-10-0-2-20`, evento âncora 20:10:16 07/09/2026 BRT (epoch 1788822616000 · 2026-09-07T23:10:16.000Z)). É o comportamento normal e documentado de bootstrap de nó em EKS/Karpenter: o daemonset `ebs-csi-node` inicia antes do CNI concluir a inicialização.

### Linha do tempo
- 20:10:08 07/09/2026 BRT (epoch 1788822608000 · 2026-09-07T23:10:08.000Z) `Scheduled` do pod `ebs-csi-node-xxtf6` no nó recém-criado `ip-10-0-2-20`.
- 20:10:16 07/09/2026 BRT (epoch 1788822616000 · 2026-09-07T23:10:16.000Z) 1ª `NetworkNotReady` do achado, coincidindo com `kube-proxy`/`aws-node` ainda em criação no mesmo nó.
- 20:10:26 07/09/2026 BRT (epoch 1788822626000 · 2026-09-07T23:10:26.000Z) `aws-node` (VPC CNI) reporta `Started`; 2ª e última `NetworkNotReady` desse nó.
- Padrão idêntico se repete em mais 21 nós ao longo da janela, com a última ocorrência registrada em 21:27:17 10/09/2026 BRT (epoch 1789086437000 · 2026-09-11T00:27:17.000Z) (nó `ip-10-0-4-152`).
- Nenhum evento `source:alert` correlacionado no mesmo namespace/janela (0 resultados).

### Evidências
- Events Explorer, query completa da janela: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Akube-system%20NetworkNotReady&from_ts=1788808256645&to_ts=1789153856645&live=false
- Consulta `aggregate_events` (mesma query/janela, `group_by: kube_node`): 22 nós, 1–3 eventos cada, sem concentração anômala.
- Consulta `search_datadog_events` (`kube_namespace:kube-system kube_node:ip-10-0-2-20...`, 22:50–23:20 UTC 07/09): 11 eventos mostrando o ciclo completo de bootstrap do nó.
- Consulta `aggregate_events` (`source:alert env:production kube_namespace:kube-system`, mesma janela): 0 resultados.

### Ação recomendada
Infra — sem repositório de código, ação operacional: nenhuma mudança em `medprev-cloud-iac` ou em manifests do EKS é necessária, pois o comportamento é esperado do ciclo de vida de nó com Karpenter + VPC CNI. Se o ruído continuar poluindo a fila de achados do houston, a mudança fica no lado do coletor (`houston/collector.py`/fingerprinting): considerar excluir ou rebaixar a severidade do `reason:NetworkNotReady` em `kube_namespace:kube-system` quando as ocorrências se concentram em uma janela curta (<60s) após um evento `Scheduled` do mesmo `kube_node`, evitando gastar orçamento de investigação nele. Validar checando que, após a mudança, uma nova coleta na mesma query não gera mais um achado `new` para este fingerprint enquanto o padrão de bootstrap se mantiver.

### Volume
45 ocorrências entre 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) e 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z) — número confirmado pela consulta direta ao Datadog (mesma janela do achado, sem divergência).

### Severidade e criticidade
`severity` do achado é `medium`, mas essa classificação não se aplica ao evento em si, já que ele foi identificado como ruído. Avaliação de criticidade do defeito real encontrado (inferência): baixa — é rotatividade normal de infraestrutura elástica (Karpenter), sem qualquer alerta disparado e sem persistência por nó; o único ganho de agir é reduzir gasto de investigação/triagem em achados repetidos, não mitigar risco operacional.
