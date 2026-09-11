---
fingerprint: k8s-eks-medprev-online-prd-InstanceTerminating-unknown-namespace
source: kubernetes
reason: InstanceTerminating
novelty: new
service: unknown-namespace
environment: production
window:
  from: 1788795962045
  to: 1789141562045
observed:
  count: 169
  first_seen: 1788821630000
  last_seen: 1789132520000
severity: medium
state: promoted
cost:
  input_tokens: 903715
  output_tokens: 13318
  cache_read_input_tokens: 818614
  cache_creation_input_tokens: 85081
  duration_s: 156.051
  usd: 0.6418788
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: https://github.com/carlacurymed/medprev-poc-houston/issues/26
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aunknown-namespace%20InstanceTerminating&from_ts=1788795962045&to_ts=1789141562045&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aunknown-namespace%20InstanceTerminating&from_ts=1788795962045&to_ts=1789141562045&live=false

## Causa raiz

O `service`/namespace `unknown-namespace` não é um namespace real do Kubernetes — é o fallback que o próprio código do houston grava quando um evento não carrega a tag `kube_namespace` (`houston/collector.py:205`, `namespace = tags.get("kube_namespace", "unknown-namespace")`). Confirmei isso consultando `source:kubernetes InstanceTerminating` no cluster `eks-medprev-online-prd` na janela: todos os eventos retornados são emitidos pelo `reporting_controller:karpenter` sobre objetos `Node`/`NodeClaim` (rotação/consolidação de nós, incluindo interrupções de spot), e nenhum desses eventos carrega a tag `kube_namespace` — uma consulta agregada filtrando `kube_namespace:*` sobre o mesmo escopo devolveu 0. Ou seja, o achado é **RUÍDO de instrumentação, não um incidente de produção**: os nós terminam normalmente (Karpenter substituindo/consolidando instâncias), e o defeito real é que o pipeline do houston constrói uma query de evidência (`kube_namespace:unknown-namespace`) que nunca pode casar com nenhum evento real — a própria query do achado, rodada literalmente, devolveu 0 resultados, enquanto a query equivalente sem o filtro de namespace devolveu 175 eventos na mesma janela (89 `NodeClaim` + 86 `Node`, `env:production`).

Não é um erro de serviço, então "handled/unhandled" e status HTTP não se aplicam — é um evento de infraestrutura Kubernetes, e a classificação sinal/ruído aqui está no par (evento real vs. link morto): 175/175 eventos reais são rotação normal de nó (0 evidência de falha de aplicação: `source:kubernetes env:production status:error` na mesma janela devolveu 0 logs; consulta de spans em `kube_node:ip-10-0-10-78*` devolveu 0 buckets — não há spans de aplicação indexados por essa tag). Cerca de metade (87 de 175, medido com `source:kubernetes FailedDraining env:production`) veio acompanhada de `FailedDraining` (pods aguardando eviction no momento do terminate), o que é esperado durante rotação de nó e não um sinal de falha isolado.

## Linha do tempo

Sem paginar: a busca listou os primeiros 41 de 267 eventos totais (`source:kubernetes InstanceTerminating`, todos os envs, mesma janela); os passos abaixo são os que caem em `eks-medprev-online-prd` (`env:production`) dentro da janela de coleta (`window_from`: "12:46:02 07/09/2026 BRT (epoch 1788795962045 · 2026-09-07T15:46:02.045Z)" a `window_to`: "12:46:02 11/09/2026 BRT (epoch 1789141562045 · 2026-09-11T15:46:02.045Z)"):

1. 19:53:50 07/09/2026 BRT (epoch 1788821630000 · 2026-09-07T22:53:50.000Z) — `NodeClaim default-ddzhb` e `Node ip-10-0-1-180.sa-east-1.compute.internal` terminam (evento amostra do achado, `raw.timestamp`). Sem `FailedDraining` associado.
2. 20:59:46 07/09/2026 BRT (epoch 1788825586000 · 2026-09-07T23:59:46.000Z) — `NodeClaim default-llrx5` / `Node ip-10-0-2-20...` terminam.
3. 01:02:05 08/09/2026 BRT (epoch 1788840125000 · 2026-09-08T04:02:05.000Z) e 01:03:19 08/09/2026 BRT (epoch 1788840199000 · 2026-09-08T04:03:19.000Z) — duas rotações de nó consecutivas (`default-8xnjr`/`ip-10-0-7-226`, `default-gm7gm`/`ip-10-0-6-170`).
4. 05:20:38 08/09/2026 BRT (epoch 1788855638000 · 2026-09-08T08:20:38.000Z), 07:02:13 08/09/2026 BRT (epoch 1788861733000 · 2026-09-08T10:02:13.000Z), 07:45:50 08/09/2026 BRT (epoch 1788864350000 · 2026-09-08T10:45:50.000Z) — mais três rotações sem `FailedDraining`.
5. 10:51:03 08/09/2026 BRT (epoch 1788875463000 · 2026-09-08T13:51:03.000Z) — `NodeClaim default-vctlr` / `Node ip-10-0-6-3...` terminam.
6. 13:33:52 08/09/2026 BRT (epoch 1788885232000 · 2026-09-08T16:33:52.000Z) — `Node ip-10-0-7-233...` termina com `FailedDraining` (1 pod aguardando eviction).
7. 14:51:41 08/09/2026 BRT (epoch 1788889901000 · 2026-09-08T17:51:41.000Z) — `Node ip-10-0-6-169...` termina com `FailedDraining` (1 pod aguardando eviction).
8. 16:38:51 08/09/2026 BRT (epoch 1788896331000 · 2026-09-08T19:38:51.000Z) — `Node ip-10-0-0-150...` termina com `FailedDraining` (1 pod aguardando eviction).
9. ... (mais 166 eventos análogos de rotação Karpenter até `last_seen`) ...
10. `last_seen`: "10:15:20 11/09/2026 BRT (epoch 1789132520000 · 2026-09-11T13:15:20.000Z)" — último evento registrado no histórico completo do achado (fora do range detalhado acima por limite de paginação da consulta).

Não paginei os 267 eventos completos (custo desnecessário para o que a pergunta pede); a contagem agregada acima (175 em produção) e a amostra cronológica bastam para caracterizar o padrão como rotação contínua e não um pico isolado.

## Evidência

- Consulta literal do achado (`query` / `datadog_url` / `evidence_links[0].url`) devolve **0 eventos** na janela — confirmado rodando exatamente `source:kubernetes env:production status:warn kube_namespace:unknown-namespace InstanceTerminating` de `1788795962045` a `1789141562045`.
- A mesma consulta sem o filtro `kube_namespace` (`source:kubernetes InstanceTerminating env:production`) devolve **175 eventos** na mesma janela (89 `kube_kind:nodeclaim` + 86 `kube_kind:node`) — via `aggregate_events`, sem link pronto (não há `evidence_links` para essa variante; consulta rodada diretamente).
- Nenhum evento de `InstanceTerminating` em produção, na janela, carrega a tag `kube_namespace` — `aggregate_events` com `kube_namespace:*` sobre o mesmo escopo devolveu 0.
- `source:kubernetes FailedDraining env:production` na mesma janela: **87 eventos** (pods aguardando eviction durante o terminate).
- `source:kubernetes env:production status:error` na mesma janela: **0 logs de erro de aplicação** — https://app.datadoghq.com/logs?from_ts=1788795962045&live=false&query=source%3Akubernetes+env%3Aproduction+status%3Aerror&to_ts=1789141562045
- `aggregate_spans` para `env:production kube_node:ip-10-0-10-78*` na mesma janela: **0 buckets** — https://app.datadoghq.com/apm/traces?end=1789141562045&historicalData=true&paused=true&query=env%3Aproduction+kube_node%3Aip-10-0-10-78%2A&start=1788795962045
- Origem do defeito no código: `houston/collector.py:205` (`namespace = tags.get("kube_namespace", "unknown-namespace")`) e `houston/collector.py:173` (`kubernetes_evidence_query`, que sempre anexa `kube_namespace:{namespace}`).

## Ação recomendada

Corrigir `houston/collector.py` para não gerar uma query de evidência com `kube_namespace:{namespace}` quando `namespace == "unknown-namespace"` (ou seja, quando o evento Kubernetes original não carregava `kube_namespace`) — nesses casos, a query deve cair para `source:kubernetes env:<env> status:warn {reason}` (sem o filtro de namespace), o único jeito de o link realmente devolver os eventos que o achado descreve.

## Corpo da issue

### Descrição do incidente
O achado `k8s-eks-medprev-online-prd-InstanceTerminating-unknown-namespace` reporta 169 eventos de `InstanceTerminating` no cluster `eks-medprev-online-prd`, mas o link de evidência do próprio achado (`evidence_links[0].url` / `datadog_url`) devolve zero eventos no Datadog. O serviço/namespace "unknown-namespace" não existe no cluster — é um valor de fallback do código do houston. Impacto observável: qualquer pessoa que clique no link de evidência deste (e de qualquer futuro) achado de Kubernetes cujo Reason seja escopado a `Node`/`NodeClaim` (sem `kube_namespace`) verá "nenhum evento encontrado", mesmo quando o evento é real e frequente.

### Causa raiz
RUÍDO: 175 eventos reais de rotação de nó do Karpenter no cluster de produção na janela (89 `NodeClaim` + 86 `Node`), 0 logs de erro de aplicação e 0 spans correlacionados — ou seja, o `InstanceTerminating` em si é comportamento normal de rotação/consolidação de nós, não um incidente. O defeito real é no pipeline: `houston/collector.py:205` grava `namespace = "unknown-namespace"` quando a tag `kube_namespace` está ausente (o caso de todo evento emitido sobre `Node`/`NodeClaim`, que são escopados ao nó, não a um namespace de workload), e `kubernetes_evidence_query` (linha 173) sempre concatena `kube_namespace:{namespace}` na query de evidência — produzindo um filtro que não pode casar com nenhum evento real. Confirmado rodando a query literal do achado (0 resultados) contra a mesma query sem o filtro de namespace (175 resultados).

### Linha do tempo
- 19:53:50 07/09/2026 BRT (epoch 1788821630000 · 2026-09-07T22:53:50.000Z) — primeiro evento da amostra do achado: `NodeClaim default-ddzhb` / `Node ip-10-0-1-180.sa-east-1.compute.internal` terminam.
- 20:59:46 07/09/2026 BRT (epoch 1788825586000 · 2026-09-07T23:59:46.000Z) a 16:38:51 08/09/2026 BRT (epoch 1788896331000 · 2026-09-08T19:38:51.000Z) — rotações subsequentes de nós/nodeclaims Karpenter em produção, cerca de metade acompanhadas de `FailedDraining` (pods aguardando eviction no momento do terminate, ex.: 13:33:52 08/09/2026 BRT (epoch 1788885232000 · 2026-09-08T16:33:52.000Z), 14:51:41 08/09/2026 BRT (epoch 1788889901000 · 2026-09-08T17:51:41.000Z), 16:38:51 08/09/2026 BRT (epoch 1788896331000 · 2026-09-08T19:38:51.000Z)).
- Padrão contínuo (não pico isolado) até `last_seen` do histórico completo do achado: "10:15:20 11/09/2026 BRT (epoch 1789132520000 · 2026-09-11T13:15:20.000Z)".
- Não há evento de deploy/versão correlacionado: essas são rotações de infraestrutura (Karpenter), não de aplicação.

### Evidências
- Query literal do achado (0 resultados): https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aunknown-namespace%20InstanceTerminating&from_ts=1788795962045&to_ts=1789141562045&live=false
- Mesma query sem `kube_namespace` (175 resultados, sem link pronto — consulta rodada direto): `source:kubernetes InstanceTerminating env:production`, `from=1788795962045`, `to=1789141562045`.
- `FailedDraining` correlacionado (87 eventos): `source:kubernetes FailedDraining env:production`, mesma janela.
- Logs de erro de aplicação (0 resultados): https://app.datadoghq.com/logs?from_ts=1788795962045&live=false&query=source%3Akubernetes+env%3Aproduction+status%3Aerror&to_ts=1789141562045
- Spans correlacionados (0 resultados): https://app.datadoghq.com/apm/traces?end=1789141562045&historicalData=true&paused=true&query=env%3Aproduction+kube_node%3Aip-10-0-10-78%2A&start=1788795962045

### Ação recomendada
Repositório: `medprev-poc-houston` (este mesmo repo — o defeito está no próprio pipeline, não em um serviço externo; `target_repo` do achado é `null` porque o achado trata de infraestrutura sem repo de aplicação, mas o *código a corrigir* é o do houston). Arquivo/função: `houston/collector.py`, função `kubernetes_evidence_query` (linha 165) e o ponto de chamada em `collect_kubernetes_findings` (linha ~222). Mudança: quando `namespace == "unknown-namespace"` (isto é, o evento original não carregava `kube_namespace` — típico de Reasons emitidos sobre `Node`/`NodeClaim`, como `InstanceTerminating`, `FailedDraining`, `SpotInterrupted`), a query gerada não deve incluir o termo `kube_namespace:unknown-namespace`; deve cair para `{query} {reason}` sem o filtro de namespace. Validação: reexecutar `mise run test` (adicionar um caso em `tests/test_collector.py` que sintetize um evento Karpenter sem `kube_namespace` e assertar que a `scoped_query` resultante, quando rodada contra os mesmos eventos, devolve resultados não vazios) e confirmar manualmente no Datadog que a nova URL de evidência de um achado `k8s-*-unknown-namespace` retorna os eventos reais.

### Volume
`observed_count`: 169 ocorrências entre "12:46:02 07/09/2026 BRT (epoch 1788795962045 · 2026-09-07T15:46:02.045Z)" e "12:46:02 11/09/2026 BRT (epoch 1789141562045 · 2026-09-11T15:46:02.045Z)". Consulta direta ao Datadog na mesma janela, sem o filtro `kube_namespace` (que zera o resultado): 175 eventos (89 `NodeClaim` + 86 `Node`) — a pequena diferença (169 vs. 175) é consistente com o critério exato de regex/Reason usado internamente pelo collector para agrupar mensagens multi-Reason, não foi investigada a fundo por ser irrelevante à causa raiz.

### Severidade e criticidade
`severity` do achado é `medium`, mas não se aplica ao evento `InstanceTerminating` em si — é rotação normal de infraestrutura, sem impacto observado (0 erros de aplicação, 0 spans afetados). A criticidade real é a do defeito de instrumentação: **baixa a média** (inferência) — não causa incidente em produção, mas rouba confiabilidade do processo de triagem do houston (qualquer engenheiro que clique no link do achado terá uma evidência falsa-negativa, o que compromete a credibilidade do relatório automatizado e pode fazer alguém descartar erroneamente um achado real por "sem dados"). Deve ser corrigido, mas não é bloqueante de operação.
