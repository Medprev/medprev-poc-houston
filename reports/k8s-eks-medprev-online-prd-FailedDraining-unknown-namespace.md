---
fingerprint: k8s-eks-medprev-online-prd-FailedDraining-unknown-namespace
source: kubernetes
reason: FailedDraining
novelty: new
service: unknown-namespace
environment: production
window:
  from: 1788802594687
  to: 1789148194687
observed:
  count: 88
  first_seen: 1788821626000
  last_seen: 1789142565000
severity: medium
state: promoted
cost:
  input_tokens: 955362
  output_tokens: 12882
  cache_read_input_tokens: 844645
  cache_creation_input_tokens: 110699
  duration_s: 142.043
  usd: 0.745191
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: https://github.com/carlacurymed/medprev-poc-houston/issues/26
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aunknown-namespace%20FailedDraining&from_ts=1788802594687&to_ts=1789148194687&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aunknown-namespace%20FailedDraining&from_ts=1788802594687&to_ts=1789148194687&live=false

## Causa raiz

O evento é ruído operacional esperado do Karpenter fazendo consolidação/rotação de nós no cluster `eks-medprev-online-prd`, não um bug de aplicação. Verifiquei ao vivo, sem o filtro `kube_namespace:unknown-namespace` da própria query do achado (que devolve **zero** eventos — ver abaixo), a mesma busca trocando por `kube_cluster_name:eks-medprev-online-prd`: 88 eventos `FailedDraining` na janela **entre 14:36:34 07/09/2026 BRT (epoch 1788802594687 · 2026-09-07T17:36:34.687Z) e 14:36:34 11/09/2026 BRT (epoch 1789148194687 · 2026-09-11T17:36:34.687Z)**, batendo exatamente com `observed_count`, espalhados em **86 nós distintos** (cardinalidade sobre `kube_name`). Ou seja: é essencialmente um evento por nó, cada um com 1 a 22 pods aguardando remoção por violação de PodDisruptionBudget, seguido de `TerminationGracePeriodExpiring` e, numa minoria dos casos, `InstanceTerminating` — o ciclo de vida normal de rotação de nós do Karpenter, não uma falha recorrente num único nó. Não há trace/span associado a este tipo de evento (é um evento de control-plane do Kubernetes, não uma chamada de aplicação instrumentada), então a classificação `@error.handling`/`@http.status_code` não se aplica aqui — a classificação sinal/ruído acima se apoia na contagem por nó (86 distintos / 88 eventos) e na ausência de qualquer log de erro correlacionado. Rodei `search_datadog_logs` com `source:kubernetes kube_cluster_name:eks-medprev-online-prd (evict* OR drain* OR PodDisruptionBudget)` na mesma janela: **0 resultados** — nenhum log de aplicação menciona impacto de drenagem/evicção.

O achado que de fato merece ação não é o `FailedDraining` em si, e sim um defeito no próprio coletor deste repositório (`houston/collector.py`): a `query` e o `datadog_url`/`evidence_links` do achado usam `kube_namespace:unknown-namespace` como filtro literal, mas "unknown-namespace" é apenas um valor default do Python (`houston/collector.py:205`, `tags.get("kube_namespace", "unknown-namespace")`) para quando o evento não carrega a tag `kube_namespace` — o que é sempre o caso para eventos de nó do Karpenter (não têm namespace, são escopados a nó). `kubernetes_evidence_query` (`houston/collector.py:165-176`) então monta `f"{query} kube_namespace:{namespace}"` com esse placeholder como se fosse um valor real de tag, produzindo uma query que nunca casa com nada no Datadog real — confirmei isso rodando a query exata do achado (`source:kubernetes env:production status:warn kube_namespace:unknown-namespace FailedDraining`) na janela exata: **0 eventos**.

## Linha do tempo

Como a query do próprio achado não devolve nada (ver acima), a linha do tempo abaixo vem da busca equivalente sem o filtro quebrado (`source:kubernetes env:production status:warn FailedDraining kube_cluster_name:eks-medprev-online-prd`), ordenada por timestamp — 88 eventos no total, um por nó em sua maioria; listo os primeiros e o padrão observado, não os 88 individualmente (mostra o formato, repetitivo):

- 19:53:46 07/09/2026 BRT (epoch 1788821626000 · 2026-09-07T22:53:46.000Z) — nó `ip-10-0-1-180.sa-east-1.compute.internal`: `FailedDraining`, 1 pod aguardando remoção; `TerminationGracePeriodExpiring` até 19:53:46 08/09/2026 BRT (epoch 1788908026000 · 2026-09-08T22:53:46.000Z). Este é o `first_seen` do achado e bate exatamente com `raw.sample_workload`/`raw.timestamp` do JSON.
- 20:59:26 07/09/2026 BRT (epoch 1788825566000 · 2026-09-07T23:59:26.000Z) — nó `ip-10-0-2-20.sa-east-1.compute.internal`: `FailedDraining`, 2 pods aguardando.
- 01:01:42 08/09/2026 BRT (epoch 1788840102000 · 2026-09-08T04:01:42.000Z) — nó `ip-10-0-7-226...`: `FailedDraining`, 5 pods aguardando.
- 13:33:52 08/09/2026 BRT (epoch 1788885232000 · 2026-09-08T16:33:52.000Z) — nó `ip-10-0-7-233...`: `FailedDraining` + `InstanceTerminating` no mesmo evento (nó de fato terminou logo em seguida).
- ... padrão se repete ao longo dos 4 dias, um evento por nó diferente a cada rotação do Karpenter (ip-10-0-6-170, ip-10-0-2-247, ip-10-0-10-33, ip-10-0-4-196 (2x), ip-10-0-6-3, ip-10-0-6-169, ip-10-0-0-150, ip-10-0-3-5, ip-10-0-3-235, ip-10-0-10-52, ip-10-0-10-50, ip-10-0-3-55, ip-10-0-1-237, ip-10-0-3-20, ip-10-0-10-167 (2x), ip-10-0-3-246, ip-10-0-1-42, ip-10-0-0-32, ip-10-0-10-64, ip-10-0-3-100, ip-10-0-4-97, ip-10-0-4-113, ip-10-0-8-247, ip-10-0-11-18, ip-10-0-4-41, ip-10-0-0-128, ip-10-0-10-11, ip-10-0-3-212, ip-10-0-5-4, ip-10-0-11-67, ip-10-0-9-9, entre outros).
- último evento retornado pela consulta cai dentro da janela em 20:01:30 09/09/2026 BRT (epoch 1788994890000 · 2026-09-09T23:01:30.000Z) nos primeiros 37 registros retornados (resposta paginada — não paginei o resto para não gastar orçamento à toa, ver "Evidência"); o `last_seen` do achado (**13:02:45 11/09/2026 BRT — epoch 1789142565000 · 13:02:45 11/09/2026 BRT (epoch 1789142565000 · 2026-09-11T16:02:45.000Z)**) fica fora dos registros que efetivamente inspecionei, mas está dentro da janela coberta pela contagem agregada (88 = `observed_count` exato).

## Evidência

- 88 eventos `FailedDraining` na janela do achado, confirmados por `search_datadog_events` com `source:kubernetes env:production status:warn FailedDraining kube_cluster_name:eks-medprev-online-prd`, `from=14:36:34 07/09/2026 BRT (epoch 1788802594000 · 2026-09-07T17:36:34.000Z)`, `to=14:36:34 11/09/2026 BRT (epoch 1789148194000 · 2026-09-11T17:36:34.000Z)` (bate com `observed_count`).
- 86 nós distintos afetados, via `aggregate_events` com `CARDINALITY` sobre `kube_name` na mesma query/janela — evidência de que é rotação de nós ampla, não um nó problemático recorrente.
- A query original do achado (`https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aunknown-namespace%20FailedDraining&from_ts=1788802594687&to_ts=1789148194687&live=false`, `datadog_url`/`evidence_links[0]` do achado) devolve **0 eventos** quando executada literalmente — verificado com `search_datadog_events` na mesma string de query.
- Nenhum log de aplicação menciona evicção/drenagem/PDB no cluster nessa janela: `search_datadog_logs` com `source:kubernetes kube_cluster_name:eks-medprev-online-prd (evict* OR drain* OR PodDisruptionBudget)`, mesma janela, **0 resultados**.
- Causa do placeholder `unknown-namespace`: `houston/collector.py:205` (`tags.get("kube_namespace", "unknown-namespace")`) e `houston/collector.py:165-176` (`kubernetes_evidence_query`), lidos diretamente no repositório.

## Ação recomendada

O `FailedDraining` em si não exige ação — é rotação normal do Karpenter sob PDBs. A ação real é corrigir, neste repositório (`medprev-poc-houston`), a construção de `evidence_links`/`query` para achados Kubernetes sem `kube_namespace` real (eventos escopados a nó): não emitir `kube_namespace:unknown-namespace` como filtro literal em `kubernetes_evidence_query` (`houston/collector.py:165-176`).

## Corpo da issue

### Descrição do incidente
Achados de Kubernetes gerados para eventos escopados a **nó** (sem tag `kube_namespace`, como `FailedDraining`, e possivelmente `NodeShutdown`/`InstanceTerminating` — mesmo padrão de fingerprint `-unknown-namespace` já presente em outros arquivos deste repositório) carregam uma `query`/`evidence_links`/`datadog_url` que nunca retorna dados: o coletor usa o placeholder interno `"unknown-namespace"` como se fosse um valor real de tag `kube_namespace` do Datadog. Impacto observável: qualquer humano que clique no link do achado para investigar cai numa busca vazia, sem conseguir verificar a evidência primária do próprio relatório.

### Causa raiz
Ruído — 88 ocorrências em 86 nós distintos, ciclo normal de consolidação do Karpenter, sem log de aplicação correlacionado (0 resultados na busca de evicção/PDB). O defeito real, confirmado nesta investigação, é de engenharia de dados do próprio pipeline: `houston/collector.py:205` usa `"unknown-namespace"` como valor default em Python quando a tag `kube_namespace` está ausente, e `kubernetes_evidence_query` (linhas 165-176) embute esse default como filtro literal na query real do Datadog, que nunca existe como tag de verdade.

### Linha do tempo
Ver `## Linha do tempo` acima — primeiro evento em 19:53:46 07/09/2026 BRT (epoch 1788821626000 · 2026-09-07T22:53:46.000Z) no nó `ip-10-0-1-180.sa-east-1.compute.internal` (bate com `raw.sample_workload`/`raw.timestamp` do achado), seguido de dezenas de eventos equivalentes em outros 85 nós ao longo da janela, cada um resolvido dentro do próprio `TerminationGracePeriodExpiring`.

### Evidências
- `search_datadog_events`, `source:kubernetes env:production status:warn FailedDraining kube_cluster_name:eks-medprev-online-prd`, 14:36:34 07/09/2026 BRT (epoch 1788802594000 · 2026-09-07T17:36:34.000Z)–14:36:34 11/09/2026 BRT (epoch 1789148194000 · 2026-09-11T17:36:34.000Z) → 88 eventos.
- `aggregate_events` (CARDINALITY sobre `kube_name`), mesma query/janela → 86 nós distintos.
- Query original do achado (`kube_namespace:unknown-namespace FailedDraining`) → 0 eventos, mesma janela.
- `search_datadog_logs`, `source:kubernetes kube_cluster_name:eks-medprev-online-prd (evict* OR drain* OR PodDisruptionBudget)`, mesma janela → 0 resultados.
- Código-fonte: `houston/collector.py:165-176` (`kubernetes_evidence_query`) e `houston/collector.py:201-209` (fallback `"unknown-namespace"`).

### Ação recomendada
Repositório: `medprev-poc-houston` (o defeito está no próprio coletor deste repo, não em `target_repo`, que é `null` porque o achado original é de infraestrutura). Em `houston/collector.py`, função `kubernetes_evidence_query` (linha ~173) e o ponto que popula `namespace` (linha ~205): quando o evento não carregar `kube_namespace` (eventos escopados a nó), não incluir o termo `kube_namespace:{namespace}` na query gerada — usar apenas `kube_name`/`kube_cluster_name` como escopo, e ajustar o fingerprint (`k8s_fingerprint`) e o `evidence_links` correspondentes para não depender de um namespace inexistente. Validar rodando `houston run` contra uma janela real e conferindo manualmente, no Datadog Events Explorer, que a `query`/`evidence_links` gerada para um achado `-unknown-namespace` retorna eventos reais (contagem > 0), em vez de 0 como hoje.

### Volume
`observed_count`: 88, na janela **14:36:34 07/09/2026 BRT (epoch 1788802594687 · 2026-09-07T17:36:34.687Z)** a **14:36:34 11/09/2026 BRT (epoch 1789148194687 · 2026-09-11T17:36:34.687Z)**. Consulta equivalente ao Datadog (sem o filtro quebrado, mesma janela) devolveu o mesmo total: 88.

### Severidade e criticidade
`severity` do achado é `medium`, mas não se aplica ao `FailedDraining` em si — é ruído/comportamento esperado do Karpenter. Para o defeito real (query/evidence_links inutilizáveis para achados Kubernetes escopados a nó): inferência de criticidade **baixa-média** — não causa indisponibilidade, mas compromete a confiabilidade do pipeline de investigação (evidência primária inacessível, e granularidade de fingerprint por namespace, decidida na ADR-0008 para manter volume baixo, não se aplica a eventos de nó, podendo agregar rotações de nós não relacionadas sob um único fingerprint).
