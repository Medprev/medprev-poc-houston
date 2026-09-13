---
fingerprint: k8s-eks-medprev-online-prd-InvalidDiskCapacity-unknown-namespace
source: kubernetes
reason: InvalidDiskCapacity
novelty: new
service: unknown-namespace
environment: production
window:
  from: 1788808256645
  to: 1789153856645
observed:
  count: 21
  first_seen: 1788822605000
  last_seen: 1789120180000
severity: medium
state: new
cost:
  input_tokens: 675053
  output_tokens: 9777
  cache_read_input_tokens: 564487
  cache_creation_input_tokens: 110552
  duration_s: 107.493
  usd: 0.6575014
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aunknown-namespace%20InvalidDiskCapacity&from_ts=1788808256645&to_ts=1789153856645&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aunknown-namespace%20InvalidDiskCapacity&from_ts=1788808256645&to_ts=1789153856645&live=false

## Causa raiz

O achado é um evento de infraestrutura Kubernetes (`InvalidDiskCapacity`, cluster `eks-medprev-online-prd`) e **não pertence a nenhuma namespace real**: `unknown-namespace` é o valor-sentinela que o coletor usa quando o evento do Kubernetes não carrega `kube_namespace` — e de fato, ao consultar os eventos reais (`search_datadog_events`, texto livre `InvalidDiskCapacity`, janela 16:10:56 07/09/2026 BRT (epoch 1788808256000 · 2026-09-07T19:10:56.000Z)–16:10:56 11/09/2026 BRT (epoch 1789153856000 · 2026-09-11T19:10:56.000Z)), nenhum dos 124 eventos retornados carrega a tag `kube_namespace`: são eventos emitidos pelo `kubelet` sobre o próprio **nó** (`kubernetes_kind:node`), não sobre um workload namespaced. Isso é consequência direta: a query construída pelo achado (`kube_namespace:unknown-namespace`) nunca pode casar com um evento real no Datadog, porque a tag `kube_namespace` simplesmente não existe nesses eventos — confirmei isso rodando a query exata do achado (`source:kubernetes env:production status:warn kube_namespace:unknown-namespace InvalidDiskCapacity`), que devolveu **0** eventos tanto via `search_datadog_events` quanto via `aggregate_events`.

Classificação: **RUÍDO quanto ao texto do achado, mas SINAL real e volumoso quanto ao evento subjacente**. O evento real (`invalid capacity 0 on image filesystem`, emitido pelo `kubelet`) ocorre **81 vezes** no cluster `eks-medprev-online-prd` dentro da mesma janela (`aggregate_events`, `source:kubernetes InvalidDiskCapacity kube_cluster_name:eks-medprev-online-prd`, 16:10:56 07/09/2026 BRT (epoch 1788808256000 · 2026-09-07T19:10:56.000Z)–16:10:56 11/09/2026 BRT (epoch 1789153856000 · 2026-09-11T19:10:56.000Z)), além de 32 no `eks-medprev-online-dev` e 11 no `eks-medprev-tools` — ou seja, acontece em praticamente todos os nós novos provisionados pelo Karpenter (`karpenter_nodepool:default`), em todos os ambientes, não é isolado a um workload. Esse padrão (nó novo → kubelet reporta capacidade 0 no filesystem de imagens momentos após o boot) é consistente com uma condição transitória de inicialização do containerd/kubelet em nós recém-criados, não com um problema de negócio.

Não determinei com certeza que a condição se autorresolve sem impacto (não consultei o ciclo de vida completo de cada nó individualmente) — isso fica marcado como não verificado. O que consultei e o resultado de cada consulta:
- `search_datadog_events` com a query exata do achado → 0 eventos.
- `aggregate_events` com a mesma query exata → 0 eventos.
- `search_datadog_events` texto livre `InvalidDiskCapacity` na janela → 124 eventos, todos sem `kube_namespace`, todos `kube_kind:node`.
- `aggregate_events` agrupado por `kube_cluster_name` → prd 81, dev 32, tools 11.
- `aggregate_events` para `DiskPressure OR Evicted OR NodeNotReady` no prd na mesma janela → 359 (número não decomposto por falta de orçamento de consulta; não permite concluir causalidade direta com o `InvalidDiskCapacity`, apenas indica que há atividade de pressão/eviction de nós no cluster no mesmo período — correlação não confirmada).

Não há serviço de aplicação (`service`) afetado a consultar em logs/spans: o evento é do próprio nó Kubernetes (via `kubelet`), sem `service` ou `trace_id` associável — não há trace de aplicação para este achado.

## Linha do tempo

- `20:10:05 07/09/2026 BRT (epoch 1788822605000 · 2026-09-07T23:10:05.000Z)` — primeira ocorrência do achado (`first_seen`): nó `ip-10-0-2-20.sa-east-1.compute.internal` (prd), kubelet reporta `InvalidDiskCapacity: invalid capacity 0 on image filesystem`. Confirmado via `search_datadog_events` texto livre.
- `01:00:53 08/09/2026 BRT (epoch 1788840053000 · 2026-09-08T04:00:53.000Z)` a `18:11:47 08/09/2026 BRT (epoch 1788901907000 · 2026-09-08T21:11:47.000Z)` — mais 18 nós distintos (prd, dev e tools) reportam o mesmo evento ao longo do dia 08/09, um por nó, sem repetição no mesmo nó — padrão de nó novo provisionado.
- `23:34:22 08/09/2026 BRT (epoch 1788921262000 · 2026-09-09T02:34:22.000Z)` a `12:06:09 09/09/2026 BRT (epoch 1788966369000 · 2026-09-09T15:06:09.000Z)` — mais ~20 nós novos reportam o mesmo evento (amostra retornada, paginação truncada em 48/124 pelo limite de tokens da ferramenta).
- Dentro da janela de coleta (`window_from`: 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) até `window_to`: 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z)) o total real no cluster prd é 81 eventos — acima do `observed_count` de 21 registrado pelo achado, porque o `observed_count` foi calculado com uma query que nunca casa (ver "Causa raiz").
- `06:49:40 11/09/2026 BRT (epoch 1789120180000 · 2026-09-11T09:49:40.000Z)` — última ocorrência registrada pelo achado (`last_seen`).

Não há eventos de mudança de estado de monitor ou deploy correlacionados a reportar — este fingerprint é de fonte `kubernetes`, não `alert`.

## Evidência

- Evento original do achado (link pronto): [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aunknown-namespace%20InvalidDiskCapacity&from_ts=1788808256645&to_ts=1789153856645&live=false) — clicar nele hoje mostra 0 resultados, o que É o problema estrutural descrito acima.
- Query exata do achado rodada por mim (`source:kubernetes env:production status:warn kube_namespace:unknown-namespace InvalidDiskCapacity`, 16:10:56 07/09/2026 BRT (epoch 1788808256000 · 2026-09-07T19:10:56.000Z)–16:10:56 11/09/2026 BRT (epoch 1789153856000 · 2026-09-11T19:10:56.000Z)) → 0 eventos, via `search_datadog_events` e via `aggregate_events`.
- Query `source:kubernetes InvalidDiskCapacity` (texto livre, mesma janela) → 124 eventos totais, nenhum com tag `kube_namespace`.
- Query `source:kubernetes InvalidDiskCapacity kube_cluster_name:eks-medprev-online-prd` (mesma janela) → 81 eventos.
- Query `source:kubernetes InvalidDiskCapacity` agrupada por `kube_cluster_name` (mesma janela) → prd: 81, dev: 32, tools: 11.
- Query `source:kubernetes kube_cluster_name:eks-medprev-online-prd (DiskPressure OR Evicted OR NodeNotReady)` (mesma janela) → 359 — não decomposto, correlação não confirmada, registrado como indício não conclusivo.

## Ação recomendada

Corrigir o `houston/collector.py` para não sintetizar `kube_namespace:unknown-namespace` como termo de busca quando um evento Kubernetes não carrega namespace (eventos de nó/kubelet); a query de evidência deve, nesses casos, escopar por `kube_node`/`kube_cluster_name` — os únicos campos que esses eventos realmente carregam — ou o link ficará permanentemente quebrado (0 resultados) para todo achado desta classe.

## Corpo da issue

### Descrição do incidente
Achados do tipo Kubernetes cuja Reason não é namespaced (ex.: `InvalidDiskCapacity`, emitida pelo `kubelet` sobre o próprio nó) recebem `kube_namespace: unknown-namespace` como valor-sentinela no fingerprint e na query de evidência. O problema: a query gerada (`kube_namespace:unknown-namespace`) é incluída literalmente como filtro Datadog, mas eventos de nó nunca carregam a tag `kube_namespace` — logo a query nunca casa com nada. Qualquer humano que clique no `datadog_url`/`evidence_links` deste achado (e de qualquer outro com o mesmo padrão) vê 0 resultados, mesmo havendo o evento real ocorrendo com alto volume (81 vezes no cluster prd na mesma janela de 4 dias).

### Causa raiz
RUÍDO quanto à query do achado (0/0 eventos reais casam com o filtro construído — confirmado rodando a query exata), mas SINAL real quanto ao evento subjacente: `InvalidDiskCapacity` (kubelet, `invalid capacity 0 on image filesystem`) ocorre 81x no cluster prd, 32x no dev e 11x no tools na mesma janela — padrão consistente com nós novos provisionados via Karpenter reportando uma condição transitória de containerd/kubelet no boot. Causa raiz da condição do kubelet em si (por que o filesystem de imagem reporta capacidade 0 no boot) **não determinada** por esta investigação — ficou fora de escopo confirmar se é uma característica normal e autorresolvida do bootstrap do AMI/containerd ou um defeito de provisionamento.

### Linha do tempo
- `20:10:05 07/09/2026 BRT (epoch 1788822605000 · 2026-09-07T23:10:05.000Z)` — primeira ocorrência (nó `ip-10-0-2-20.sa-east-1.compute.internal`, prd).
- `01:00:53 08/09/2026 BRT (epoch 1788840053000 · 2026-09-08T04:00:53.000Z)`–`18:11:47 08/09/2026 BRT (epoch 1788901907000 · 2026-09-08T21:11:47.000Z)` — ~18 nós adicionais (prd/dev/tools) reportam o mesmo evento, um por nó.
- `23:34:22 08/09/2026 BRT (epoch 1788921262000 · 2026-09-09T02:34:22.000Z)`–`12:06:09 09/09/2026 BRT (epoch 1788966369000 · 2026-09-09T15:06:09.000Z)` — mais ~20 nós reportam o mesmo evento (amostra parcial, resultado paginado).
- `06:49:40 11/09/2026 BRT (epoch 1789120180000 · 2026-09-11T09:49:40.000Z)` — última ocorrência registrada pelo achado (`last_seen`).
- Nenhum deploy ou mudança de versão correlacionável foi consultado (evento não carrega `service`/`version`).

### Evidências
- Query original do achado (0 resultados hoje): https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aunknown-namespace%20InvalidDiskCapacity&from_ts=1788808256645&to_ts=1789153856645&live=false
- `source:kubernetes InvalidDiskCapacity` (texto livre, 16:10:56 07/09/2026 BRT (epoch 1788808256000 · 2026-09-07T19:10:56.000Z)–16:10:56 11/09/2026 BRT (epoch 1789153856000 · 2026-09-11T19:10:56.000Z)) → 124 eventos, nenhum com `kube_namespace`.
- `source:kubernetes InvalidDiskCapacity kube_cluster_name:eks-medprev-online-prd` (mesma janela) → 81 eventos.
- Agrupamento por `kube_cluster_name` (mesma janela) → prd: 81, dev: 32, tools: 11.

### Ação recomendada
Repositório: infra — sem repositório de código associado ao `target_repo` do achado (`null`), mas a correção é no próprio `medprev-poc-houston` (`houston/collector.py`, função de coleta de eventos Kubernetes, e `houston/fingerprint.py` para o `k8s-{cluster}-{reason}-{namespace}`). Mudança específica: quando o evento Kubernetes não tiver `kube_namespace` (eventos `kube_kind:node`), a query de evidência gerada deve usar `kube_node`/`kube_cluster_name` como escopo em vez de injetar `kube_namespace:unknown-namespace` literal — o sentinela pode continuar existindo no fingerprint para fins de dedup, mas não deve virar termo de busca no Datadog. Validação: reabrir `houston run` sobre um achado desta classe e confirmar que o `evidence_links`/`datadog_url` gerado, ao ser aberto no Datadog, retorna eventos reais (não mais 0).

### Volume
`observed_count`: 21, medido na janela `window_from`–`window_to` do achado (16:10:56 07/09/2026 BRT · 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) até 16:10:56 11/09/2026 BRT · 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z)) — mas por uma query que nunca casa (ver Causa raiz), então esse número é inexplicável a partir da consulta que ele supostamente representa. Consultando eu mesma a mesma janela sem o filtro quebrado de namespace: 81 eventos reais no cluster prd (`source:kubernetes InvalidDiskCapacity kube_cluster_name:eks-medprev-online-prd`).

### Severidade e criticidade
`severity` do achado: `medium` — não se aplica ao erro conforme descrito, pois a query do achado não representa nenhum evento real (0 casos). Avaliação de criticidade do defeito real encontrado (inferência minha): **média** — o bug de query quebra a rastreabilidade de todo achado de eventos Kubernetes sem namespace (não só este Reason), reduzindo a confiança do pipeline de investigação e desperdiçando a promessa de "evidência clicável" (ADR-0022) especificamente para essa classe de achados; o evento subjacente (`InvalidDiskCapacity` em nós novos) tem alto volume mas, sem confirmação de impacto real em disponibilidade (DiskPressure/eviction não decomposto), não caracterizo como crítico para o negócio nesta investigação.
