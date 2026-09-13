---
fingerprint: k8s-eks-medprev-online-prd-FailedScheduling-medprev-cms
source: kubernetes
reason: FailedScheduling
novelty: new
service: medprev-cms
environment: production
window:
  from: 1788814356569
  to: 1789159956569
observed:
  count: 3
  first_seen: 1788951251000
  last_seen: 1788951276000
severity: medium
state: new
cost:
  input_tokens: 430846
  output_tokens: 8400
  cache_read_input_tokens: 337607
  cache_creation_input_tokens: 93229
  duration_s: 86.978
  usd: 0.5291044
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-cms%20FailedScheduling&from_ts=1788814356569&to_ts=1789159956569&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-cms%20FailedScheduling&from_ts=1788814356569&to_ts=1789159956569&live=false

## Causa raiz

O achado é sobre o namespace `medprev-cms` no cluster `eks-medprev-online-prd`, evento `FailedScheduling` do Kubernetes — não é um erro de aplicação (Error Tracking) nem gera spans/logs de erro no serviço, então a divisão `handled`/`unhandled` de spans não se aplica aqui; a consulta `aggregate_spans` com `service:medprev-cms status:error` na janela da coleta devolveu 0 buckets, ou seja, nenhum span de erro no período. Isso é **RUÍDO** em relação ao achado original: os 3 eventos `FailedScheduling` registrados para o pod `medprev-cms-58548cdc94-rhn9q` entre 07:54:11 09/09/2026 BRT (epoch 1788951251000 · 2026-09-09T10:54:11.000Z) e 07:54:36 09/09/2026 BRT (epoch 1788951276000 · 2026-09-09T10:54:36.000Z) são falta transitória de capacidade (CPU/memória insuficientes em 11–12 nós, mais nós com taint) enquanto o Karpenter provisionava um nó novo — o próprio pod foi agendado com sucesso em 07:54:56 09/09/2026 BRT (epoch 1788951296000 · 2026-09-09T10:54:56.000Z) e o container iniciou em 07:55:58 09/09/2026 BRT (epoch 1788951358000 · 2026-09-09T10:55:58.000Z), 45 segundos depois do primeiro `FailedScheduling`. Agregando os eventos `FailedScheduling` de todo o cluster na mesma janela (`source:kubernetes status:warn FailedScheduling`, agrupado por `kube_namespace`), 24 namespaces diferentes foram afetados (`medprev-web-app`: 145, `medprev-rest-api`: 80, `nginx-gateway-fabric`: 78, ..., `medprev-cms`: apenas 3) — o padrão é comportamento normal de escalonamento do cluster (spot/Karpenter), não algo específico do código do `medprev-cms`.

O que **não** é ruído: ao iniciar, o container sofreu falha de startup probe (`connect: connection refused` em `10.0.10.225:1337/_health`) às 07:56:15 09/09/2026 BRT (epoch 1788951375000 · 2026-09-09T10:56:15.000Z), típica de app ainda subindo — não determinei se isso se resolveu, pois a janela do achado só cobre até 07:56:15 09/09/2026 BRT (epoch 1788951375000 · 2026-09-09T10:56:15.000Z) nos eventos consultados; não busquei eventos posteriores a esse ponto.

Consultas efetivamente rodadas e retorno:
- `search_datadog_events` com a query exata do achado (`source:kubernetes env:production status:warn kube_namespace:medprev-cms FailedScheduling`), janela `window_from`–`window_to` → 3 eventos, batendo com `observed_count: 3`.
- `search_datadog_logs` (`service:medprev-cms env:production status:error`), mesma janela → 90 logs, todos ruído de build (`npm notice` classificado erroneamente como `error`), nenhum relacionado ao FailedScheduling.
- `aggregate_spans` (`service:medprev-cms status:error`, agrupado por `@error.handling`/`@http.status_code`) → 0 buckets, sem spans de erro no serviço na janela.
- `search_datadog_events` filtrado por `kube_name:medprev-cms-58548cdc94-rhn9q` numa janela mais ampla ao redor do incidente → 8 eventos, reconstruindo o ciclo completo de scheduling→pull→start→probe.
- `aggregate_events` (`source:kubernetes status:warn FailedScheduling`, agrupado por `kube_namespace`, janela do achado) → 24 namespaces afetados, `medprev-cms` com apenas 3 do total.

## Linha do tempo

- 07:54:11 09/09/2026 BRT (epoch 1788951251000 · 2026-09-09T10:54:11.000Z) — Primeiro `FailedScheduling`: "0/11 nodes are available: 1 Insufficient memory, 3 node(s) had untolerated taint(s), 8 Insufficient cpu" para o pod `medprev-cms-58548cdc94-rhn9q`. (Events Explorer, query `source:kubernetes env:production status:warn kube_namespace:medprev-cms FailedScheduling`)
- 07:54:12 09/09/2026 BRT (epoch 1788951252000 · 2026-09-09T10:54:12.000Z) — Karpenter nomeia o pod para a `nodeclaim/default-z9c8v` (início do provisionamento de um novo nó).
- 07:54:36 09/09/2026 BRT (epoch 1788951276000 · 2026-09-09T10:54:36.000Z) — Segundo `FailedScheduling` (registrado duas vezes, em nós diferentes): "0/12 nodes are available: 1 Insufficient memory, 4 node(s) had untolerated taint(s), 8 Insufficient cpu" — ainda esperando capacidade.
- 07:54:56 09/09/2026 BRT (epoch 1788951296000 · 2026-09-09T10:54:56.000Z) — `Scheduled`: pod atribuído com sucesso a `ip-10-0-9-9.sa-east-1.compute.internal`; início do `Pulling` da imagem `medprev-cms:e8ed3dc7`.
- 07:54:58 09/09/2026 BRT (epoch 1788951298000 · 2026-09-09T10:54:58.000Z) — `TaintManagerEviction` cancela a eviction pendente do pod (nó já saudável).
- 07:55:58 09/09/2026 BRT (epoch 1788951358000 · 2026-09-09T10:55:58.000Z) — Imagem baixada em 1m01s, container criado e iniciado (`Created`/`Pulled`/`Started`).
- 07:56:15 09/09/2026 BRT (epoch 1788951375000 · 2026-09-09T10:56:15.000Z) — `Unhealthy`: startup probe falha com `connection refused` em `10.0.10.225:1337/_health` (container ainda subindo). Não determinei se essa falha se resolveu logo em seguida — não consultei eventos além desse ponto.

## Evidência

- 3 ocorrências de `FailedScheduling` no namespace `medprev-cms` dentro de `window_from`–`window_to`, confirmando `observed_count`: [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-cms%20FailedScheduling&from_ts=1788814356569&to_ts=1789159956569&live=false).
- Nenhum span de erro de `medprev-cms` na janela do achado: `aggregate_spans` com `query: "service:medprev-cms status:error"`, `from`/`to` = `window_from_ms`/`window_to_ms` → 0 buckets.
- Nenhum log de erro de aplicação relacionado ao evento: `search_datadog_logs` com `query: "service:medprev-cms env:production status:error"`, mesma janela → 90 logs, todos `npm notice` de build, sem relação com scheduling.
- O pod afetado foi agendado e iniciado com sucesso ~45s depois do primeiro `FailedScheduling`: `search_datadog_events` com `query: "source:kubernetes kube_name:medprev-cms-58548cdc94-rhn9q"`, janela em torno de 07:54:11 09/09/2026 BRT (epoch 1788951251000 · 2026-09-09T10:54:11.000Z)–07:56:15 09/09/2026 BRT (epoch 1788951375000 · 2026-09-09T10:56:15.000Z) → 8 eventos mostrando `Nominated` → `Scheduled` → `Pulling`/`Pulled` → `Created`/`Started` → `Unhealthy` (startup probe).
- `FailedScheduling` no mesmo período atingiu 24 namespaces do cluster, não só `medprev-cms`: `aggregate_events` com `query: "source:kubernetes status:warn FailedScheduling"`, `group_by: kube_namespace`, mesma janela → `medprev-web-app`: 145, `medprev-rest-api`: 80, `nginx-gateway-fabric`: 78, `zuul`: 59, ..., `medprev-cms`: 3 (menor volume entre os afetados).

## Ação recomendada

Nenhuma ação de código em `medprev-cms` — investigar (infra, não `target_repo`) se a capacidade base do node pool `default` do Karpenter no cluster `eks-medprev-online-prd` está subdimensionada para picos de deploy/scale, já que 24 namespaces sofreram `FailedScheduling` na mesma janela de 4 dias.

## Corpo da issue

### Descrição do incidente
O namespace `medprev-cms`, no cluster EKS `eks-medprev-online-prd`, registrou 3 eventos `FailedScheduling` para o pod `medprev-cms-58548cdc94-rhn9q` entre 10:54:11 e 10:54:36 UTC de 09/09/2026, por falta transitória de CPU/memória disponível nos nós existentes. Nenhum impacto observável ao usuário foi identificado: o pod foi agendado e o container iniciou dentro de ~2 minutos do primeiro evento.

### Causa raiz
RUÍDO — 0 spans de erro de `medprev-cms` na janela (`aggregate_spans service:medprev-cms status:error` → 0 buckets) e nenhum log de erro de aplicação correlacionado. O `FailedScheduling` é o comportamento esperado do Karpenter durante o provisionamento de um novo nó sob demanda: o pod ficou pendente por ~45s enquanto um nó era lançado, e depois agendou normalmente. O mesmo padrão ocorreu em 24 namespaces do cluster na mesma janela de 4 dias (`medprev-web-app`: 145, `medprev-rest-api`: 80, etc.), o que descarta causa específica do código ou configuração de `medprev-cms` — é pressão de capacidade cluster-wide.

### Linha do tempo
- 10:54:11 UTC — 1º `FailedScheduling`: 0/11 nós disponíveis (memória insuficiente, taints, CPU insuficiente).
- 10:54:12 UTC — Karpenter nomeia o pod para uma nova `nodeclaim` (`default-z9c8v`).
- 10:54:36 UTC — 2º/3º `FailedScheduling` (registrado 2x): 0/12 nós disponíveis, ainda aguardando novo nó.
- 10:54:56 UTC — `Scheduled` com sucesso em `ip-10-0-9-9.sa-east-1.compute.internal`; início do pull da imagem `medprev-cms:e8ed3dc7`.
- 10:54:58 UTC — Eviction pendente cancelada (nó já saudável).
- 10:55:58 UTC — Imagem baixada (1m01s), container criado e iniciado.
- 10:56:15 UTC — Startup probe falha uma vez com `connection refused` (app ainda subindo); não foi possível confirmar se se resolveu logo depois, pois a consulta não cobriu além desse instante.

### Evidências
- [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-cms%20FailedScheduling&from_ts=1788814356569&to_ts=1789159956569&live=false) — 3 eventos, confere com `observed_count`.
- Consulta `aggregate_spans` (`query: "service:medprev-cms status:error"`, janela `window_from_ms`–`window_to_ms`) → 0 buckets (sem spans de erro).
- Consulta `search_datadog_logs` (`query: "service:medprev-cms env:production status:error"`, mesma janela) → 90 logs, todos ruído de build `npm notice`.
- Consulta `search_datadog_events` (`query: "source:kubernetes kube_name:medprev-cms-58548cdc94-rhn9q"`, janela ao redor do incidente) → 8 eventos mostrando o ciclo completo até o container iniciar.
- Consulta `aggregate_events` (`query: "source:kubernetes status:warn FailedScheduling"`, `group_by: kube_namespace`, mesma janela) → 24 namespaces afetados, `medprev-cms` com apenas 3 ocorrências (o menor volume entre os namespaces impactados).

### Ação recomendada
Infra — sem repositório de código, ação operacional. Avaliar, no repositório de infraestrutura do cluster (não identificado nesta investigação), se o `NodePool` `default` do Karpenter em `eks-medprev-online-prd` precisa de um buffer de capacidade maior (ex.: `disruption` menos agressivo ou nós reservados) para reduzir a janela de `FailedScheduling` durante picos de deploy — já que 24 namespaces sofreram o mesmo padrão na janela observada. Validar monitorando a métrica/evento `FailedScheduling` agregado por cluster após qualquer ajuste, confirmando queda no volume cluster-wide, não apenas em `medprev-cms`.

### Volume
3 ocorrências entre `window_from` (17:52:36 07/09/2026 BRT · 17:52:36 07/09/2026 BRT (epoch 1788814356569 · 2026-09-07T20:52:36.569Z)) e `window_to` (17:52:36 11/09/2026 BRT · 17:52:36 11/09/2026 BRT (epoch 1789159956569 · 2026-09-11T20:52:36.569Z)) — confirmado pela minha própria consulta ao Events Explorer com a mesma query e janela, que devolveu o mesmo total (3).

### Severidade e criticidade
`severity` do achado é `medium`, mas não se aplica ao erro em si — classificado como ruído/comportamento esperado do autoscaler, autorresolvido em ~45 segundos sem impacto observado. Inferência: a criticidade real é baixa, pois não há evidência de impacto ao usuário (pod agendado e saudável minutos depois); o único ponto que mereceria acompanhamento (não confirmado como problema) é a falha única de startup probe às 10:56:15 UTC — se recorrente, poderia indicar lentidão de boot do `medprev-cms`, mas não há dados nesta investigação para afirmar isso.
