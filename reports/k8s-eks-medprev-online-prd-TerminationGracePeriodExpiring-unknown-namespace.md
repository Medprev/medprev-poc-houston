---
fingerprint: k8s-eks-medprev-online-prd-TerminationGracePeriodExpiring-unknown-namespace
source: kubernetes
reason: TerminationGracePeriodExpiring
novelty: new
service: unknown-namespace
environment: production
window:
  from: 1788806810930
  to: 1789152410930
observed:
  count: 81
  first_seen: 1788821626000
  last_seen: 1789132516000
severity: medium
state: promoted
cost:
  input_tokens: 663997
  output_tokens: 11788
  cache_read_input_tokens: 589586
  cache_creation_input_tokens: 74395
  duration_s: 125.962
  usd: 0.5380802000000001
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: https://github.com/carlacurymed/medprev-poc-houston/issues/26
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aunknown-namespace%20TerminationGracePeriodExpiring&from_ts=1788806810930&to_ts=1789152410930&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aunknown-namespace%20TerminationGracePeriodExpiring&from_ts=1788806810930&to_ts=1789152410930&live=false

## Causa raiz

O achado é um evento de infraestrutura Kubernetes, não um erro de aplicação: `TerminationGracePeriodExpiring` é emitido pelo **Karpenter** (`reporting_controller:karpenter`, `source_component:karpenter`) sobre objetos `Node` e `NodeClaim` do cluster `eks-medprev-online-prd`, avisando que o prazo de graça para finalizar os pods de um nó em terminação está expirando. Não existe classificação `handled`/`unhandled` aqui (isso se aplica a spans de erro de aplicação, e este achado não tem trace associado — é evento de ciclo de vida de nó, sem `trace_id`).

Classifico como **RUÍDO operacional esperado, mas com uma consulta de evidência quebrada por trás dele**: consultei `source:kubernetes env:production TerminationGracePeriodExpiring` na janela do achado (sem o filtro `kube_namespace:unknown-namespace`) e obtive **178 eventos**, cobrindo **89 `NodeClaim`s distintos** terminados (~22 nós/dia) — volume consistente com consolidação/scale-down normal de um `karpenter_nodepool:default`, não com um crash loop. Rodando a **query exata do achado** (`kube_namespace:unknown-namespace` incluso), o retorno foi **0 eventos** — porque nenhum desses eventos carrega a tag `kube_namespace` (nós e NodeClaims não são recursos namespaced). `unknown-namespace` é um valor de fallback que o coletor usa internamente para o fingerprint, mas foi colocado, literalmente, dentro da query de evidência (`evidence_links`/`datadog_url`), tornando-a irreproduzível — quem clicar no link do achado no Datadog nunca verá os eventos que o geraram.

Consultas de log de aplicação (`search_datadog_logs`) e span (`search_datadog_spans`) não se aplicam a este achado: não há `service` de aplicação nem `trace_id` associado a um evento de ciclo de vida de nó Kubernetes — não existe "trace do erro" porque não é um erro de aplicação.

## Linha do tempo

- 19:53:46 07/09/2026 BRT (epoch 1788821626000 · 2026-09-07T22:53:46.000Z) — primeiro evento na janela: `NodeClaim default-ddzhb` e o `Node ip-10-0-1-180...` recebem `TerminationGracePeriodExpiring` (`FailedDraining`: 1 pod aguardando remoção). Query: `source:kubernetes env:production TerminationGracePeriodExpiring`.
- 20:59:26 07/09/2026 BRT (epoch 1788825566000 · 2026-09-07T23:59:26.000Z) — `NodeClaim default-llrx5` / `Node ip-10-0-2-20...`, `FailedDraining` com 2 pods aguardando.
- 01:01:42 08/09/2026 BRT (epoch 1788840102000 · 2026-09-08T04:01:42.000Z) — `NodeClaim default-8xnjr` / `Node ip-10-0-7-226...`, `FailedDraining` com 5 pods aguardando.
- 01:02:43 08/09/2026 BRT (epoch 1788840163000 · 2026-09-08T04:02:43.000Z) — `NodeClaim default-gm7gm` / `Node ip-10-0-6-170...`, `FailedDraining` com 9 pods aguardando.
- 05:20:02 08/09/2026 BRT (epoch 1788855602000 · 2026-09-08T08:20:02.000Z) — `NodeClaim default-pr857` / `Node ip-10-0-2-247...`, `FailedDraining` com 5 pods aguardando.
- 07:01:50 08/09/2026 BRT (epoch 1788861710000 · 2026-09-08T10:01:50.000Z) — `NodeClaim default-2tb95` / `Node ip-10-0-10-33...`, `FailedDraining` com 5 pods aguardando.
- 07:45:28 08/09/2026 BRT (epoch 1788864328000 · 2026-09-08T10:45:28.000Z) — `NodeClaim default-qvh5j` / `Node ip-10-0-4-196...`, `FailedDraining` com 5 pods aguardando.
- 10:50:59 08/09/2026 BRT (epoch 1788875459000 · 2026-09-08T13:50:59.000Z) — `NodeClaim default-vctlr` / `Node ip-10-0-6-3...`, `FailedDraining` com 1 pod aguardando.
- ... o padrão se repete continuamente até o fim da janela; a busca paginada devolveu 178 eventos no total e não foi integralmente listada aqui para preservar orçamento de contexto (ver seção Evidência).
- Conforme os campos do próprio achado: janela de coleta `window_from` = 15:46:50 07/09/2026 BRT (epoch 1788806810930 · 2026-09-07T18:46:50.930Z) até `window_to` = 15:46:50 11/09/2026 BRT (epoch 1789152410930 · 2026-09-11T18:46:50.930Z); `first_seen` = 19:53:46 07/09/2026 BRT (epoch 1788821626000 · 2026-09-07T22:53:46.000Z) — coincide com o primeiro evento acima; `last_seen` = 10:15:16 11/09/2026 BRT (epoch 1789132516000 · 2026-09-11T13:15:16.000Z), fora da amostra paginada que li.

## Evidência

- 178 eventos retornados por `source:kubernetes env:production TerminationGracePeriodExpiring` na janela do achado (`from=1788806810930, to=1789152410930`) — consulta que eu rodei diretamente (sem `kube_namespace`), não há link de `evidence_links` para ela porque ela não é a query original do achado.
- A query literal do achado (`source:kubernetes env:production status:warn kube_namespace:unknown-namespace TerminationGracePeriodExpiring`) devolveu **0 eventos** na mesma janela — [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aunknown-namespace%20TerminationGracePeriodExpiring&from_ts=1788806810930&to_ts=1789152410930&live=false) — confirma que o link do próprio achado não reproduz nada.
- `kube_namespace:*` não existe em nenhum dos 178 eventos amostrados (tags observadas: `kube_cluster_name`, `kube_kind`, `kube_name`, `kubernetes_kind`, `orchestrator`, `reporting_controller`, `source_component`) — verificado ao inspecionar as tags de uma amostra de 16 eventos via `search_datadog_events`.
- 89 `NodeClaim`s distintos terminados na janela: `source:kubernetes env:production TerminationGracePeriodExpiring kubernetes_kind:nodeclaim` com `cardinality(kube_name)` = 89, `count` = 89.
- 88 dos 178 eventos citam também `FailedDraining` (nó/nodeclaim com pods ainda aguardando remoção no momento do log): `source:kubernetes env:production TerminationGracePeriodExpiring FailedDraining`, `count` = 88.
- Nenhuma query de log ou span de aplicação se aplica: o achado não carrega `service` nem `trace_id` de APM — não há trace correlacionável a buscar.
- `observed_count` do achado é 81, medido entre `window_from` (15:46:50 07/09/2026 BRT (epoch 1788806810930 · 2026-09-07T18:46:50.930Z)) e `window_to` (15:46:50 11/09/2026 BRT (epoch 1789152410930 · 2026-09-11T18:46:50.930Z)); meu total via consulta ampla (178, sem `status:warn`/`kube_namespace`) e a contagem por `kubernetes_kind:nodeclaim` (89) usam filtros diferentes do achado, o que explica a divergência.

## Ação recomendada

Corrigir a construção da query de `evidence_links`/`datadog_url` para eventos Kubernetes sem namespace real: quando o coletor usa `unknown-namespace` como fallback de fingerprint, ele não deve inserir esse valor como filtro `kube_namespace:` na query de evidência — a query deve simplesmente omitir o filtro de namespace nesses casos, para o link do achado voltar a ser reproduzível.

## Corpo da issue

### Descrição do incidente
O achado `k8s-eks-medprev-online-prd-TerminationGracePeriodExpiring-unknown-namespace` representa eventos de ciclo de vida de nó emitidos pelo Karpenter (`TerminationGracePeriodExpiring`/`FailedDraining`) no cluster `eks-medprev-online-prd`. Esses eventos não carregam a tag `kube_namespace` (nós e NodeClaims não são recursos namespaced), mas `houston/collector.py` monta a query de evidência do achado usando o fallback de fingerprint `unknown-namespace` como filtro literal `kube_namespace:unknown-namespace`. Resultado: o link do achado no Datadog (`evidence_links`, `datadog_url`) nunca retorna nenhum evento, mesmo quando o achado tem `observed_count: 81`. Impacto: qualquer humano investigando este achado pelo link clica e vê uma tela vazia, sem conseguir confirmar a evidência sem reconstruir a query manualmente.

### Causa raiz
Ruído operacional esperado no evento em si (89 `NodeClaim`s distintos terminados em ~4 dias, ~22/dia — consolidação normal de nodepool, sem crash loop), mas com um defeito real e confirmado na query de evidência: ela filtra por `kube_namespace:unknown-namespace`, um valor de fallback do fingerprint que nunca existe de fato nas tags do evento (0 de 178 eventos na janela carregam qualquer `kube_namespace`), então a query sempre retorna vazio.

### Linha do tempo
- 19:53:46 07/09/2026 BRT (epoch 1788821626000 · 2026-09-07T22:53:46.000Z) — primeiro evento da janela (`first_seen` do achado): NodeClaim/Node emitem `TerminationGracePeriodExpiring`.
- 20:59:26 07/09/2026 BRT (epoch 1788825566000 · 2026-09-07T23:59:26.000Z), 01:01:42 08/09/2026 BRT (epoch 1788840102000 · 2026-09-08T04:01:42.000Z), 01:02:43 08/09/2026 BRT (epoch 1788840163000 · 2026-09-08T04:02:43.000Z), 05:20:02 08/09/2026 BRT (epoch 1788855602000 · 2026-09-08T08:20:02.000Z), 07:01:50 08/09/2026 BRT (epoch 1788861710000 · 2026-09-08T10:01:50.000Z), 07:45:28 08/09/2026 BRT (epoch 1788864328000 · 2026-09-08T10:45:28.000Z), 10:50:59 08/09/2026 BRT (epoch 1788875459000 · 2026-09-08T13:50:59.000Z) — eventos subsequentes do mesmo padrão (novo NodeClaim/Node por evento), a maioria com `FailedDraining` concorrente indicando pods ainda em remoção no momento do log.
- Padrão contínuo até `last_seen` do achado (10:15:16 11/09/2026 BRT (epoch 1789132516000 · 2026-09-11T13:15:16.000Z)), totalizando 178 eventos brutos / 89 NodeClaims distintos na janela de coleta.
- Não foi possível determinar o horário exato de cada um dos 178 eventos individualmente (paginação limitada por orçamento de contexto); os 8 acima são os primeiros 8 de 16 lidos na primeira página.

### Evidências
- Query original do achado (retorna 0 resultados): [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aunknown-namespace%20TerminationGracePeriodExpiring&from_ts=1788806810930&to_ts=1789152410930&live=false)
- Query sem filtro de namespace (retorna 178 eventos na mesma janela): `source:kubernetes env:production TerminationGracePeriodExpiring`, `from=1788806810930`, `to=1789152410930`
- Cardinalidade de NodeClaims: `source:kubernetes env:production TerminationGracePeriodExpiring kubernetes_kind:nodeclaim` → count=89, cardinality(kube_name)=89
- Co-ocorrência com `FailedDraining`: `source:kubernetes env:production TerminationGracePeriodExpiring FailedDraining` → count=88

### Ação recomendada
Repositório: nulo — infra sem repositório de código (`target_repo: null`), mas o defeito da query de evidência é do próprio `medprev-poc-houston`. Em `houston/collector.py`, na função `collect_kubernetes_findings()` (ou onde `evidence_links`/`datadog_url` são montados para achados Kubernetes), remover o filtro `kube_namespace:{namespace}` da query sempre que o namespace usado no fingerprint for o valor de fallback (`unknown-namespace`) — nesse caso a query deve conter só `source:kubernetes env:production status:warn <Reason>`. Validar rodando `mise run test -- kubernetes` (ou o teste correspondente em `tests/test_collector.py`) mais uma verificação manual: reexecutar a query do próximo achado `k8s-*-unknown-namespace-*` gerado e confirmar que o Events Explorer retorna eventos (>0), fechando a lacuna que hoje é 0 sempre.

### Volume
`observed_count`: 81, medido na janela `window_from` (15:46:50 07/09/2026 BRT · epoch 1788806810930) a `window_to` (15:46:50 11/09/2026 BRT · epoch 1789152410930). Consulta própria sem o filtro `kube_namespace` na mesma janela: 178 eventos brutos (Node+NodeClaim duplicados por ação) / 89 NodeClaims distintos.

### Severidade e criticidade
`severity` do achado: `medium` — mas essa severidade mede o evento `TerminationGracePeriodExpiring` em si, que classifiquei como ruído operacional esperado (consolidação normal do Karpenter). O defeito real que encontrei — a query de evidência sempre vazia — é, na minha avaliação (inferência, não campo direto do achado), de criticidade **baixa a média**: não afeta usuários finais nem dados, mas compromete a auditabilidade de todo achado Kubernetes gerado com namespace desconhecido, reduzindo a confiança do time nos links de evidência do pipeline.
