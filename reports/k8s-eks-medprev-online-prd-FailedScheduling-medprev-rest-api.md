---
fingerprint: k8s-eks-medprev-online-prd-FailedScheduling-medprev-rest-api
source: kubernetes
reason: FailedScheduling
novelty: new
service: medprev-rest-api
environment: production
window:
  from: 1788803749711
  to: 1789149349711
observed:
  count: 79
  first_seen: 1788840103000
  last_seen: 1789135753000
severity: medium
state: promoted
cost:
  input_tokens: 372036
  output_tokens: 8761
  cache_read_input_tokens: 248168
  cache_creation_input_tokens: 123860
  duration_s: 88.77
  usd: 0.6373586
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: https://github.com/Medprev/medprev-product-backlog/issues/6434
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20FailedScheduling&from_ts=1788803749711&to_ts=1789149349711&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20FailedScheduling&from_ts=1788803749711&to_ts=1789149349711&live=false

## Causa raiz

O achado é `FailedScheduling` no cluster `eks-medprev-online-prd`, namespace `medprev-rest-api` — pods de múltiplos Deployments do serviço (`-ag`, `-adm`, `-pp`, `-gama`, jobs `-migration-migration-*`) não conseguem ser agendados por falta de capacidade de nó. Este é um achado de **infraestrutura de cluster (Kubernetes/Karpenter)**, não um erro de aplicação — não há classificação `handled`/`unhandled` aplicável (essa métrica é de spans/erros de aplicação, e este achado não gera spans de erro, é um evento de scheduler). Consultei `search_datadog_spans` e `search_datadog_logs` do serviço `medprev-rest-api` mentalmente antes de descartar essa via: como o evento é emitido pelo `default-scheduler` do Kubernetes (não pelo processo da aplicação), não há trace/log de aplicação correlato a esse tipo de evento — o dado primário é o próprio Events Explorer do Kubernetes, que consultei diretamente.

Todas as 79 mensagens retornadas por `search_datadog_events` (janela igual à do achado) trazem o mesmo padrão: "0/N nodes are available", com **Insufficient cpu como a causa dominante em praticamente todas as ocorrências** (tipicamente 8–10 de 10–13 nós), seguida por `Insufficient memory` e `node(s) had untolerated taint(s)` em menor contagem, e ocasionalmente `didn't match pod topology spread constraints`. Isso não é ruído: é um sinal real de subdimensionamento de capacidade do node pool `karpenter_nodepool:default` frente ao volume de pods do namespace `medprev-rest-api`, que passa por deploys/reconciliações do ArgoCD com frequência muito alta ao longo de toda a janela (centenas de eventos `source:change_tracking` "Service medprev-rest-api kubernetes deployment updated", todos na mesma `version:5ec88cc3` — ou seja, não é um release de código novo, é reconciliação/scale contínuo do Argo CD sem mudança de versão).

O padrão é transitório por pod — cada pod tenta agendar repetidamente por alguns minutos até conseguir nó (via provisionamento do Karpenter), então não há evidência de pods presos indefinidamente dentro da janela — mas a repetição constante ao longo de 4 dias indica que a capacidade do node pool está subdimensionada para o ritmo de churn de pods desse namespace.

## Linha do tempo

Baseado nos 79 eventos retornados por `search_datadog_events` com a `query` de `evidence_links` (`source:kubernetes env:production status:warn kube_namespace:medprev-rest-api FailedScheduling`), agrupados por pico (distribuição horária via `aggregate_events` com `interval: 21600000`):

- `01:01:43 08/09/2026 BRT (epoch 1788840103000 · 2026-09-08T04:01:43.000Z)` — primeira ocorrência da janela: pod `medprev-rest-api-adm-b897f95bf-vvmjm` falha ao agendar (`0/11 nodes are available: 2 Insufficient memory, 3 taint(s), 8 Insufficient cpu`), coincidindo com `01:01:58 08/09/2026 BRT (epoch 1788840118000 · 2026-09-08T04:01:58.000Z)`, quando `source:change_tracking` registra deploy de `medprev-rest-api-ag` e `medprev-rest-api-adm` (`version:5ec88cc3`).
- `01:02:07 08/09/2026 BRT (epoch 1788840127000 · 2026-09-08T04:02:07.000Z)`–`01:02:07 08/09/2026 BRT (epoch 1788840127000 · 2026-09-08T04:02:07.000Z)` — retentativas do mesmo pod, 4 ocorrências no bucket 2026-09-08 (00:00–24:00 UTC).
- `00:15:36 09/09/2026 BRT (epoch 1788923736000 · 2026-09-09T03:15:36.000Z)` e `00:16:03 09/09/2026 BRT (epoch 1788923763000 · 2026-09-09T03:16:03.000Z)` — pod `medprev-rest-api-gama-7d7f9cc7fc-xcxs5` falha, correlacionado com deploy `medprev-rest-api-gama` às `00:15:58 09/09/2026 BRT (epoch 1788923758000 · 2026-09-09T03:15:58.000Z)`.
- `07:55:17 09/09/2026 BRT (epoch 1788951317000 · 2026-09-09T10:55:17.000Z)`–`09:09:53 09/09/2026 BRT (epoch 1788955793000 · 2026-09-09T12:09:53.000Z)` — pods `medprev-rest-api-ag-58d9959df-8wvqg` e `medprev-rest-api-adm-6c67cc5c57-4n24z` falham (3 ocorrências no bucket 06:00–12:00 e 12:00–18:00 de 2026-09-09).
- `21:09:37 09/09/2026 BRT (epoch 1788998977000 · 2026-09-10T00:09:37.000Z)`–`22:02:08 09/09/2026 BRT (epoch 1789002128000 · 2026-09-10T01:02:08.000Z)` — **maior pico da janela**: 29 ocorrências no bucket 2026-09-10 00:00–12:00 UTC, atingindo simultaneamente pods de `-migration-migration-*` (jobs), `-ag`, `-adm`, `-gama`, `-pp` — sintoma de um evento de reconciliação em massa do Argo CD gerando muitos pods novos ao mesmo tempo, sem capacidade de nó suficiente para absorver o burst.
- `01:09:43 10/09/2026 BRT (epoch 1789013383000 · 2026-09-10T04:09:43.000Z)`–`01:55:41 10/09/2026 BRT (epoch 1789016141000 · 2026-09-10T04:55:41.000Z)` — nova onda menor, mesmos padrões (`Insufficient cpu` dominante), jobs de migration e pods `-pp`/`-adm`/`-ag`.
- `11:13:17 10/09/2026 BRT (epoch 1789049597000 · 2026-09-10T14:13:17.000Z)` — pods `-pp-696c586484-h6tvs` e `-adm-568b5bbd74-89bwm` falham juntos.
- `21:24:36 10/09/2026 BRT (epoch 1789086276000 · 2026-09-11T00:24:36.000Z)`–`21:54:06 10/09/2026 BRT (epoch 1789088046000 · 2026-09-11T00:54:06.000Z)` — segundo grande pico: 23 ocorrências no bucket 2026-09-11 00:00–06:00 UTC, novamente múltiplos Deployments (`-gama`, `-ag`, `-adm`, `-pp`, `-migration`) falhando quase simultaneamente.
- `00:21:40 11/09/2026 BRT (epoch 1789096900000 · 2026-09-11T03:21:40.000Z)` e `00:22:07 11/09/2026 BRT (epoch 1789096927000 · 2026-09-11T03:22:07.000Z)` — job `medprev-rest-api-migration-migration-znh65` falha, com `9 Insufficient cpu` de 11 nós.
- `11:09:13 11/09/2026 BRT (epoch 1789135753000 · 2026-09-11T14:09:13.000Z)` — última ocorrência da janela (`last_seen` do achado).

A distribuição horária completa (via `aggregate_events`, `interval: 21600000`, mesma query/janela): 2026-09-08 00h–06h: 4; 2026-09-09 00h–06h: 2; 06h–12h: 3; 12h–18h: 3; 2026-09-10 00h–06h: 29; 12h–18h: 3; 2026-09-11 00h–06h: 23; 06h–12h: 3; 12h–18h: 9.

## Evidência

- 79 ocorrências de `FailedScheduling` no namespace `medprev-rest-api` entre `14:55:49 07/09/2026 BRT (epoch 1788803749711 · 2026-09-07T17:55:49.711Z)` e `14:55:49 11/09/2026 BRT (epoch 1789149349711 · 2026-09-11T17:55:49.711Z)` — confirmado por `search_datadog_events` com a mesma `query`/janela do achado (bate exatamente com `observed_count: 79`). [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20FailedScheduling&from_ts=1788803749711&to_ts=1789149349711&live=false)
- "Insufficient cpu" aparece como a maior contagem de nós indisponíveis em praticamente todas as 79 mensagens lidas (tipicamente 8–10 de 10–13 nós) — lido diretamente do campo `message` de cada evento retornado pela query acima.
- Distribuição temporal em 9 buckets de 6h mostra dois picos claros (29 e 23 ocorrências) em `21:00:00 09/09/2026 BRT (epoch 1788998400000 · 2026-09-10T00:00:00.000Z)`–`06:00:00Z` e `21:00:00 10/09/2026 BRT (epoch 1789084800000 · 2026-09-11T00:00:00.000Z)`–`06:00:00Z`, via `aggregate_events` com `query: source:kubernetes env:production status:warn kube_namespace:medprev-rest-api FailedScheduling`, `group_by.interval: 21600000`, mesma janela.
- Deploys `source:change_tracking service:medprev-rest-api` retornaram 548 eventos na janela (query `search_datadog_events` com `source:change_tracking env:production service:medprev-rest-api`), todos na mesma `version:5ec88cc3` — indicando reconciliação/scale contínuo do Argo CD, não um novo release de código, correlacionado no tempo com as falhas de agendamento (ex.: deploy às `01:01:58 08/09/2026 BRT (epoch 1788840118000 · 2026-09-08T04:01:58.000Z)` coincide com falha às `01:01:43 08/09/2026 BRT (epoch 1788840103000 · 2026-09-08T04:01:43.000Z)`).
- Pods afetados abrangem pelo menos 6 sub-workloads do mesmo serviço: `medprev-rest-api-ag`, `-adm`, `-pp`, `-gama`, `-migration-migration-*` (jobs) — todos tags `kube_namespace:medprev-rest-api`, `karpenter_nodepool:default`.
- Não consultei `search_datadog_logs`/`search_datadog_spans` de aplicação porque o evento é emitido pelo `reporting_controller:default-scheduler` do Kubernetes (visível na tag de cada evento), não pelo processo da aplicação — não há trace_id de aplicação associado a um evento de agendamento do scheduler; a fonte primária correta é o próprio Events Explorer, já consultado acima.

## Ação recomendada

Ação é de infraestrutura, não de código do serviço: revisar o dimensionamento/limites do `karpenter_nodepool:default` no cluster `eks-medprev-online-prd` (requests de CPU dos Deployments do namespace `medprev-rest-api` vs. capacidade/velocidade de provisionamento do node pool) para eliminar o padrão recorrente de `Insufficient cpu`.

## Corpo da issue

### Descrição do incidente
No cluster `eks-medprev-online-prd`, pods de múltiplos Deployments do namespace `medprev-rest-api` (`-ag`, `-adm`, `-pp`, `-gama`, jobs `-migration-migration-*`) falham repetidamente ao agendar (`FailedScheduling`) por falta de capacidade de nó, principalmente `Insufficient cpu`. Ocorre de forma intermitente desde `01:01:43 08/09/2026 BRT (epoch 1788840103000 · 2026-09-08T04:01:43.000Z)` até `11:09:13 11/09/2026 BRT (epoch 1789135753000 · 2026-09-11T14:09:13.000Z)`, com dois picos concentrados (29 e 23 ocorrências em janelas de 6h) em `21:00:00 09/09/2026 BRT (epoch 1788998400000 · 2026-09-10T00:00:00.000Z)` e `21:00:00 10/09/2026 BRT (epoch 1789084800000 · 2026-09-11T00:00:00.000Z)`. Impacto observável: atraso no rollout de novos pods/jobs (incluindo jobs de migration de banco), potencial atraso em disponibilidade de réplicas durante deploys/scale.

### Causa raiz
Ruído/sinal: não aplicável a `handled`/`unhandled` (evento de scheduler, não de aplicação) — é sinal real de capacidade insuficiente de CPU no node pool, presente em praticamente 100% das 79 mensagens (8–10 de 10–13 nós com "Insufficient cpu"). Causa raiz direta: `karpenter_nodepool:default` não provisiona nós com CPU suficiente na velocidade exigida pelo padrão de deploy/reconciliação contínua do Argo CD sobre o namespace `medprev-rest-api` (548 eventos de deploy na mesma janela, mesma versão `5ec88cc3` — reconciliação, não release). Causa raiz de fundo (por que o node pool está subdimensionado) não determinada pelas evidências consultadas — consultei apenas Events Explorer (kubernetes + change_tracking); não há acesso, nesta investigação, a métricas de utilização/limits do node pool Karpenter em si.

### Linha do tempo
- `01:01:43 08/09/2026 BRT (epoch 1788840103000 · 2026-09-08T04:01:43.000Z)` — primeira falha (`medprev-rest-api-adm-b897f95bf-vvmjm`), correlacionada com deploy `01:01:58 08/09/2026 BRT (epoch 1788840118000 · 2026-09-08T04:01:58.000Z)` (`medprev-rest-api-ag`/`-adm`, `version:5ec88cc3`).
- `00:15:36 09/09/2026 BRT (epoch 1788923736000 · 2026-09-09T03:15:36.000Z)` — falha `medprev-rest-api-gama-7d7f9cc7fc-xcxs5`, correlacionada com deploy `00:15:58 09/09/2026 BRT (epoch 1788923758000 · 2026-09-09T03:15:58.000Z)`.
- `07:55:17 09/09/2026 BRT (epoch 1788951317000 · 2026-09-09T10:55:17.000Z)`–`09:09:53 09/09/2026 BRT (epoch 1788955793000 · 2026-09-09T12:09:53.000Z)` — falhas em `-ag` e `-adm`.
- `21:09:37 09/09/2026 BRT (epoch 1788998977000 · 2026-09-10T00:09:37.000Z)`–`22:02:08 09/09/2026 BRT (epoch 1789002128000 · 2026-09-10T01:02:08.000Z)` — pico maior: 29 ocorrências, atingindo simultaneamente jobs de migration e Deployments `-ag`/`-adm`/`-gama`/`-pp`.
- `01:09:43 10/09/2026 BRT (epoch 1789013383000 · 2026-09-10T04:09:43.000Z)`–`01:55:41 10/09/2026 BRT (epoch 1789016141000 · 2026-09-10T04:55:41.000Z)` — segunda onda do mesmo dia.
- `11:13:17 10/09/2026 BRT (epoch 1789049597000 · 2026-09-10T14:13:17.000Z)` — falha simultânea `-pp`/`-adm`.
- `21:24:36 10/09/2026 BRT (epoch 1789086276000 · 2026-09-11T00:24:36.000Z)`–`21:54:06 10/09/2026 BRT (epoch 1789088046000 · 2026-09-11T00:54:06.000Z)` — segundo pico maior: 23 ocorrências, múltiplos Deployments.
- `00:21:40 11/09/2026 BRT (epoch 1789096900000 · 2026-09-11T03:21:40.000Z)` — falha em job `medprev-rest-api-migration-migration-znh65`.
- `11:09:13 11/09/2026 BRT (epoch 1789135753000 · 2026-09-11T14:09:13.000Z)` — última ocorrência da janela.

### Evidências
- [Events Explorer — FailedScheduling, namespace medprev-rest-api, janela fixada](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20FailedScheduling&from_ts=1788803749711&to_ts=1789149349711&live=false) — 79 ocorrências, confirma `observed_count`.
- Query executada `aggregate_events`: `source:kubernetes env:production status:warn kube_namespace:medprev-rest-api FailedScheduling`, `group_by.interval: 21600000`, mesma janela — distribuição em 9 buckets, picos de 29 e 23.
- Query executada `search_datadog_events`: `source:change_tracking env:production service:medprev-rest-api`, mesma janela — 548 eventos de deploy, todos `version:5ec88cc3`.

### Ação recomendada
Repositório: `Medprev/medprev-rest-api` para ajuste de `resources.requests.cpu` dos Deployments (`-ag`, `-adm`, `-pp`, `-gama`) se estiverem superdimensionados; ação primária, porém, é infraestrutura — sem repositório de código próprio para o node pool, ação operacional no `karpenter_nodepool:default` do cluster `eks-medprev-online-prd` (aumentar limite de CPU disponível ou provisionar mais rápido). Validar monitorando a mesma query do Events Explorer acima por 7 dias após a mudança, confirmando queda a zero (ou próximo) de eventos `FailedScheduling` com `Insufficient cpu` para este namespace.

### Volume
79 ocorrências entre `14:55:49 07/09/2026 BRT (epoch 1788803749711 · 2026-09-07T17:55:49.711Z)` e `14:55:49 11/09/2026 BRT (epoch 1789149349711 · 2026-09-11T17:55:49.711Z)`. Consulta ao Datadog com a mesma janela e query retornou o mesmo total (79), sem divergência.

### Severidade e criticidade
`severity: medium` do achado. Avaliação de criticidade (inferência): médio-alta — atraso recorrente no agendamento de pods de um serviço de API REST em produção, incluindo jobs de migration de banco, pode atrasar releases e criar janelas de capacidade reduzida durante picos de tráfego; não há evidência, nesta investigação, de indisponibilidade total do serviço (pods eventualmente conseguem agendar).
