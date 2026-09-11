---
fingerprint: k8s-eks-medprev-online-prd-FailedScheduling-medprev-web-app
source: kubernetes
reason: FailedScheduling
novelty: new
service: medprev-web-app
environment: production
window:
  from: 1788796708898
  to: 1789142308898
observed:
  count: 145
  first_seen: 1788799289000
  last_seen: 1789120828000
severity: medium
state: promoted
cost:
  input_tokens: 419142
  output_tokens: 9216
  cache_read_input_tokens: 339689
  cache_creation_input_tokens: 79443
  duration_s: 99.569
  usd: 0.48257180000000005
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: https://github.com/Medprev/medprev-product-backlog/issues/6434
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-web-app%20FailedScheduling&from_ts=1788796708898&to_ts=1789142308898&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-web-app%20FailedScheduling&from_ts=1788796708898&to_ts=1789142308898&live=false

## Causa raiz

O `medprev-web-app` (namespace `medprev-web-app` no cluster `eks-medprev-online-prd`) sofre atrasos recorrentes de agendamento de pods pelo `default-scheduler`: a cada novo pod (rollouts do Deployment `medprev-web-app-frontend` e execuções do CronJob `medprev-web-app-sitemap-generate-laboratories`), o Karpenter não tem nó do nodepool `default` com CPU/memória disponível no instante da criação do pod (mensagem recorrente: "Insufficient cpu", "Insufficient memory", "node(s) had untolerated taint(s)"), e o pod fica sem nó por uma janela curta até o Karpenter provisionar um nó novo. Isso é **sinal real, não ruído** — não é uma classificação `handled`/`unhandled` de span (esse eixo não existe para eventos de scheduling do Kubernetes), mas a evidência direta é: consultei o evento subsequente do primeiro pod afetado (`medprev-web-app-frontend-68bbd8d888-htt78`) e ele foi agendado com sucesso em `13:42:15 07/09/2026 BRT (epoch 1788799335000 · 2026-09-07T16:42:15.000Z)`, **46 segundos** depois da primeira falha em `13:41:29 07/09/2026 BRT (epoch 1788799289000 · 2026-09-07T16:41:29.000Z)` — ou seja, todo pod observado eventualmente é agendado, o problema é o atraso, não uma falha permanente.

O evento é contínuo ao longo de toda a janela (não concentrado em um único incidente): agregando por blocos de 6h entre `12:58:28 07/09/2026 BRT (epoch 1788796708898 · 2026-09-07T15:58:28.898Z)` e `12:58:28 11/09/2026 BRT (epoch 1789142308898 · 2026-09-11T15:58:28.898Z)`, a contagem varia de 2 a 25 eventos por bucket, todos os 4 dias — indicando subdimensionamento estrutural do nodepool `default`, não um pico isolado de deploy.

Não consegui medir impacto real ao usuário via APM: `service:medprev-web-app-frontend` não retornou nenhum span no período (`aggregate_spans` devolveu 0 buckets) — esse serviço parece ser um frontend estático/RUM sem instrumentação de servidor, e os únicos logs encontrados sob esse nome de serviço são eventos de RUM do navegador (ex.: erro de fetch para `doubleclick.net`), não logs de aplicação server-side. Portanto **não determinei** se o atraso de scheduling chegou a causar indisponibilidade percebida (ex.: readiness/PDB insuficiente derrubando réplicas ativas) — consultas rodadas e resultado de cada uma:
- `search_datadog_logs` com `service:medprev-web-app-frontend env:production` na janela: 1.434.812 logs, mas são eventos de RUM do navegador, não logs de servidor.
- `aggregate_spans` com `service:medprev-web-app-frontend env:production`: 0 buckets — sem spans de APM.
- `search_datadog_events` filtrando `Scheduled` para o pod `htt78` logo após sua primeira falha: 1 evento, confirmando reagendamento bem-sucedido em 46s.

## Linha do tempo

- `13:41:29 07/09/2026 BRT (epoch 1788799289000 · 2026-09-07T16:41:29.000Z)` — primeira falha de scheduling do pod `medprev-web-app-frontend-68bbd8d888-htt78`: "0/10 nodes are available: 2 node(s) had untolerated taint(s), 3 Insufficient memory, 8 Insufficient cpu" (Events Explorer, query abaixo).
- `13:41:55 07/09/2026 BRT (epoch 1788799315000 · 2026-09-07T16:41:55.000Z)` — segunda tentativa falha do mesmo pod, agora "0/11 nodes": mais um nó apareceu no cluster mas ainda insuficiente.
- `13:42:15 07/09/2026 BRT (epoch 1788799335000 · 2026-09-07T16:42:15.000Z)` — pod `htt78` agendado com sucesso em `ip-10-0-1-180.sa-east-1.compute.internal` (evento `Scheduled` + `Pulling` da imagem `medprev-web-app-frontend:2a695aba`) — resolução em 46s.
- `20:09:43 07/09/2026 BRT (epoch 1788822583000 · 2026-09-07T23:09:43.000Z)` a `20:10:08 07/09/2026 BRT (epoch 1788822608000 · 2026-09-07T23:10:08.000Z)` — mesmo padrão repete para o pod `...g6km4` (novo ReplicaSet, mesma imagem de rollout).
- `05:11:43 08/09/2026 BRT (epoch 1788855103000 · 2026-09-08T08:11:43.000Z)` a `05:12:12 08/09/2026 BRT (epoch 1788855132000 · 2026-09-08T08:12:12.000Z)` — repete para `...gdkx8`.
- `06:52:25 08/09/2026 BRT (epoch 1788861145000 · 2026-09-08T09:52:25.000Z)` a `06:52:49 08/09/2026 BRT (epoch 1788861169000 · 2026-09-08T09:52:49.000Z)` — repete para `...62hvd`.
- `07:05:00 08/09/2026 BRT (epoch 1788861900000 · 2026-09-08T10:05:00.000Z)` a `07:05:27 08/09/2026 BRT (epoch 1788861927000 · 2026-09-08T10:05:27.000Z)` — primeira ocorrência em um **CronJob**, não no Deployment: `medprev-web-app-sitemap-generate-laboratories-29814365-nfzfd`.
- `10:25:20 08/09/2026 BRT (epoch 1788873920000 · 2026-09-08T13:25:20.000Z)` a `10:25:49 08/09/2026 BRT (epoch 1788873949000 · 2026-09-08T13:25:49.000Z)` — repete para `...44zdc`.
- `13:02:24 08/09/2026 BRT (epoch 1788883344000 · 2026-09-08T16:02:24.000Z)` a `13:03:01 08/09/2026 BRT (epoch 1788883381000 · 2026-09-08T16:03:01.000Z)` — repete para `...9bc8m`.
- `14:00:31 08/09/2026 BRT (epoch 1788886831000 · 2026-09-08T17:00:31.000Z)` a `14:00:55 08/09/2026 BRT (epoch 1788886855000 · 2026-09-08T17:00:55.000Z)` — repete para `...zl9j2`.
- `14:56:36 08/09/2026 BRT (epoch 1788890196000 · 2026-09-08T17:56:36.000Z)` — repete para `...6tvbp` (última amostra individual consultada; a busca retornou 145 eventos no total e foi truncada em 24 itens por chamada — o padrão se mantém idêntico nas amostras seguintes por agregação).
- Distribuição por blocos de 6h confirma que o padrão continua até o fim da janela, com picos em `03:00:00 09/09/2026 BRT (epoch 1788933600000 · 2026-09-09T06:00:00.000Z)` (25 eventos) e `21:00:00 10/09/2026 BRT (epoch 1789084800000 · 2026-09-11T00:00:00.000Z)` (25 eventos).

Consulta usada para todos os itens acima: `source:kubernetes env:production status:warn kube_namespace:medprev-web-app FailedScheduling` (Events Explorer).

## Evidência

- 145 ocorrências de `FailedScheduling` entre `12:58:28 07/09/2026 BRT (epoch 1788796708898 · 2026-09-07T15:58:28.898Z)` e `12:58:28 11/09/2026 BRT (epoch 1789142308898 · 2026-09-11T15:58:28.898Z)` — [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-web-app%20FailedScheduling&from_ts=1788796708898&to_ts=1789142308898&live=false).
- Causa recorrente do bloqueio: `Insufficient cpu` (presente em praticamente todos os eventos amostrados), `Insufficient memory` e `node(s) had untolerated taint(s)` no nodepool `karpenter_nodepool:default` — mesma query acima, campo `message`.
- Pod afetado é agendado com sucesso pouco depois de cada falha (confirmado para `htt78`, resolução em 46s): consulta `source:kubernetes kube_namespace:medprev-web-app (Scheduled OR NodeNotReady OR ProvisioningStarted OR NoNodesAvailable)` no intervalo `1788796708898`–`1788800000000`, 1 evento retornado.
- Distribuição temporal contínua (não é pico único): `aggregate_events` com a mesma query, agrupado em intervalos de 6h, 15 buckets, contagens entre 2 e 25 por bucket ao longo dos 4 dias.
- Sem spans de APM para o serviço afetado: `aggregate_spans` com `service:medprev-web-app-frontend env:production` na mesma janela retornou 0 buckets — não há como correlacionar erro de aplicação server-side a este achado.
- Logs sob esse nome de serviço são de RUM (client-side), não de servidor: `search_datadog_logs` com `service:medprev-web-app-frontend env:production`, 1.434.812 registros na janela, amostra única inspecionada é um evento de fetch de terceiro (`doubleclick.net`), sem relação com scheduling.
- Achado também ocorre no CronJob `medprev-web-app-sitemap-generate-laboratories`, não só no Deployment `frontend` — visto na amostra de eventos acima (`07:05:00 08/09/2026 BRT (epoch 1788861900000 · 2026-09-08T10:05:00.000Z)`).

## Ação recomendada

Aumentar a capacidade/velocidade de provisionamento do nodepool `default` do Karpenter no cluster `eks-medprev-online-prd` (ex.: consolidação menos agressiva, buffer de capacidade ou instance types com provisionamento mais rápido) para que rollouts do `medprev-web-app-frontend` e execuções do CronJob de sitemap não fiquem, mesmo que por segundos, sem nó disponível; isso é infraestrutura (Karpenter/EKS), não código de aplicação.

## Corpo da issue

### Descrição do incidente
O agendamento de pods do namespace `medprev-web-app` no cluster `eks-medprev-online-prd` falha repetidamente por falta momentânea de capacidade no nodepool `default` do Karpenter. Afeta tanto o Deployment `medprev-web-app-frontend` (a cada rollout/novo pod) quanto o CronJob `medprev-web-app-sitemap-generate-laboratories`. O padrão é contínuo desde pelo menos `12:58:28 07/09/2026 BRT (epoch 1788796708898 · 2026-09-07T15:58:28.898Z)` até `12:58:28 11/09/2026 BRT (epoch 1789142308898 · 2026-09-11T15:58:28.898Z)`, com 145 ocorrências. O impacto observável direto é atraso de segundos (confirmado 46s em um caso) na disponibilidade de novos pods; impacto em disponibilidade percebida pelo usuário final não foi determinado (ver Causa raiz).

### Causa raiz
Sinal real, não ruído: todo pod observado eventualmente é agendado (evento `Scheduled` confirmado 46s após a primeira falha do pod `htt78`), então o defeito é atraso recorrente de scheduling, não falha permanente. Causa root confirmada pelas mensagens do próprio scheduler: o nodepool `default` do Karpenter não tem, no instante de criação de cada novo pod, CPU/memória suficiente nos nós existentes (e alguns nós têm taints não tolerados), obrigando o Karpenter a provisionar nó sob demanda a cada pico de rotação de pods. Não determinado: se esse atraso já causou indisponibilidade real percebida pelo usuário — não há spans de APM nem logs de servidor para este serviço (`medprev-web-app-frontend` só expõe eventos de RUM client-side), então não foi possível correlacionar com erro/latência de requisição real.

### Linha do tempo
- `13:41:29 07/09/2026 BRT (epoch 1788799289000 · 2026-09-07T16:41:29.000Z)` primeira falha de scheduling do pod `medprev-web-app-frontend-68bbd8d888-htt78` ("Insufficient cpu"/"Insufficient memory"/taints).
- `13:41:55 07/09/2026 BRT (epoch 1788799315000 · 2026-09-07T16:41:55.000Z)` segunda tentativa falha do mesmo pod.
- `13:42:15 07/09/2026 BRT (epoch 1788799335000 · 2026-09-07T16:42:15.000Z)` pod `htt78` agendado com sucesso em `ip-10-0-1-180.sa-east-1.compute.internal` (46s de atraso total).
- Mesmo padrão repete para novos pods do Deployment em `20:09:43 07/09/2026 BRT (epoch 1788822583000 · 2026-09-07T23:09:43.000Z)`, `05:11:43 08/09/2026 BRT (epoch 1788855103000 · 2026-09-08T08:11:43.000Z)`, `06:52:25 08/09/2026 BRT (epoch 1788861145000 · 2026-09-08T09:52:25.000Z)`, `10:25:20 08/09/2026 BRT (epoch 1788873920000 · 2026-09-08T13:25:20.000Z)`, `13:02:24 08/09/2026 BRT (epoch 1788883344000 · 2026-09-08T16:02:24.000Z)`, `14:00:31 08/09/2026 BRT (epoch 1788886831000 · 2026-09-08T17:00:31.000Z)`, `14:56:36 08/09/2026 BRT (epoch 1788890196000 · 2026-09-08T17:56:36.000Z)`.
- `07:05:00 08/09/2026 BRT (epoch 1788861900000 · 2026-09-08T10:05:00.000Z)` mesmo padrão no CronJob `medprev-web-app-sitemap-generate-laboratories-29814365-nfzfd`.
- Volume por bloco de 6h permanece entre 2 e 25 eventos até `03:00:00 11/09/2026 BRT (epoch 1789106400000 · 2026-09-11T06:00:00.000Z)`, sem sinal de resolução espontânea.

### Evidências
- [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-web-app%20FailedScheduling&from_ts=1788796708898&to_ts=1789142308898&live=false) — 145 eventos.
- Consulta de confirmação de reagendamento: `source:kubernetes kube_namespace:medprev-web-app (Scheduled OR NodeNotReady OR ProvisioningStarted OR NoNodesAvailable)`, janela `1788796708898`–`1788800000000`, 1 evento.
- Consulta de distribuição temporal: `aggregate_events` sobre a mesma query com intervalo de 6h, 15 buckets.
- Consulta de correlação APM: `aggregate_spans` com `service:medprev-web-app-frontend env:production`, mesma janela, 0 buckets.
- Consulta de logs: `search_datadog_logs` com `service:medprev-web-app-frontend env:production`, mesma janela, 1.434.812 registros (RUM client-side, não server-side).

### Ação recomendada
Repositório: `Medprev/medprev-web-app` para os manifests de deploy/CronJob; a mudança de fundo é operacional em `infra` — sem repositório de código específico para o nodepool do Karpenter (ajuste é na configuração do NodePool/EC2NodeClass do Karpenter para o cluster `eks-medprev-online-prd`, não em código da aplicação). Ações concretas: (1) aumentar `requests` de buffer/headroom no NodePool `default` do Karpenter ou reduzir a agressividade de consolidação para reduzir a janela sem capacidade; (2) revisar se os taints citados ("untolerated taint(s)") são intencionais para os nós do pool — se não forem, remover ou ajustar tolerations dos pods do `medprev-web-app`; (3) validar `resources.requests` de CPU/memória do Deployment `medprev-web-app-frontend` e do CronJob de sitemap, que podem estar superdimensionados forçando mais falhas de bin-packing. Validação: após o ajuste, repetir a mesma query de `FailedScheduling` por 4 dias e confirmar volume próximo de zero, e medir o tempo entre a primeira falha e o evento `Scheduled` de cada pod (deve cair para próximo de 0s).

### Volume
145 ocorrências na janela `12:58:28 07/09/2026 BRT (epoch 1788796708898 · 2026-09-07T15:58:28.898Z)` a `12:58:28 11/09/2026 BRT (epoch 1789142308898 · 2026-09-11T15:58:28.898Z)` (`observed_count` do achado). Não consultei um total com janela diferente para comparação.

### Severidade e criticidade
`severity` do achado é `medium`. Avaliação de criticidade (inferência): impacto operacional moderado — atrasos de segundos em rollouts e no CronJob de sitemap, sem evidência de indisponibilidade real ao usuário (não medida via APM/logs de servidor, ver "Causa raiz"). Se a intermitência de capacidade piorar (nodepool cada vez mais subdimensionado frente ao crescimento de tráfego), pode evoluir para falha real de disponibilidade em rollouts futuros — isso é inferência, não dado direto do achado.
