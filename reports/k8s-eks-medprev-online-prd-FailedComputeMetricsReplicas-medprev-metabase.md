---
fingerprint: k8s-eks-medprev-online-prd-FailedComputeMetricsReplicas-medprev-metabase
source: kubernetes
reason: FailedComputeMetricsReplicas
novelty: new
service: medprev-metabase
environment: production
window:
  from: 1788808256645
  to: 1789153856645
observed:
  count: 14
  first_seen: 1788924177000
  last_seen: 1789086457000
severity: medium
state: new
cost:
  input_tokens: 315360
  output_tokens: 8016
  cache_read_input_tokens: 263143
  cache_creation_input_tokens: 52207
  duration_s: 86.245
  usd: 0.34633759999999997
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-metabase%20FailedComputeMetricsReplicas&from_ts=1788808256645&to_ts=1789153856645&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-metabase%20FailedComputeMetricsReplicas&from_ts=1788808256645&to_ts=1789153856645&live=false

## Causa raiz

O achado é sobre `medprev-metabase` (namespace Kubernetes no cluster `eks-medprev-online-prd`), mas o componente que efetivamente falha é o `metrics-server` do cluster, não a aplicação Metabase em si. O HorizontalPodAutoscaler do namespace `medprev-metabase` não consegue calcular réplicas porque a Metrics API (`pods.metrics.k8s.io`) do metrics-server não devolve métricas de CPU/memória — dois erros distintos aparecem intercalados: "the server is currently unable to handle the request (get pods.metrics.k8s.io)" e "no metrics returned from resource metrics API". Consultei os próprios logs do `metrics-server` (`kube_namespace:kube-system (metrics-server OR *metrics-server*)`, janela do achado) e encontrei falhas de probe recorrentes — `probe="metric-storage-ready" err="no metrics to serve"` — em múltiplos hosts e também no ambiente `development`, não só em `production`. Isso é **sinal**, não ruído: não há classificação `@error.handling` aplicável aqui porque este é um evento de control-plane do Kubernetes (HPA), não um span de APM com handled/unhandled — mas os próprios logs do metrics-server confirmam uma falha real e recorrente do componente, cluster-wide, e não um efeito isolado da carga do Metabase. A causa raiz exata do porquê o metrics-server intermitentemente não serve métricas (recurso insuficiente do pod, falha de scrape do kubelet, etc.) **não foi determinada** com as consultas feitas — as evidências mostram o sintoma (probe falhando) mas não o motivo interno do metrics-server.

## Linha do tempo

Consultei `search_datadog_events` com a `query` de `evidence_links` na janela do achado (`window_from`/`window_to` abaixo) e recebi 14 eventos no total; a resposta veio truncada em 9 — API do Datadog, motivo declarado como "response truncated", não ficção minha, e não reconsultei o restante por orçamento de sessão.

- 00:22:57 09/09/2026 BRT (epoch 1788924177000 · 2026-09-09T03:22:57.000Z) — 1º `FailedComputeMetricsReplicas` (variante "unable to fetch metrics ... server is currently unable to handle the request"), host `ip-10-0-10-78`.
- 00:23:12 09/09/2026 BRT (epoch 1788924192000 · 2026-09-09T03:23:12.000Z) — 2º evento, mesma variante, mesmo host.
- 00:23:27 09/09/2026 BRT (epoch 1788924207000 · 2026-09-09T03:23:27.000Z) — 3º evento, variante "no metrics returned from resource metrics API".
- 03:45:39 09/09/2026 BRT (epoch 1788936339000 · 2026-09-09T06:45:39.000Z) — 4º evento, 1ª variante, host muda para `ip-10-0-8-39`.
- 03:45:54 09/09/2026 BRT (epoch 1788936354000 · 2026-09-09T06:45:54.000Z) — 5º evento, 2ª variante.
- 07:35:50 09/09/2026 BRT (epoch 1788950150000 · 2026-09-09T10:35:50.000Z) — 6º evento, 1ª variante.
- 07:36:05 09/09/2026 BRT (epoch 1788950165000 · 2026-09-09T10:36:05.000Z) — 7º evento, 1ª variante.
- 07:36:20 09/09/2026 BRT (epoch 1788950180000 · 2026-09-09T10:36:20.000Z) — 8º evento, 2ª variante.
- 07:54:37 09/09/2026 BRT (epoch 1788951277000 · 2026-09-09T10:54:37.000Z) — 9º evento, 1ª variante.
- Faltam 5 eventos entre este ponto e o `last_seen`; a ferramenta não os devolveu nesta chamada. O achado garante que o último ocorreu em `last_seen`: "21:27:37 10/09/2026 BRT (epoch 1789086457000 · 2026-09-11T00:27:37.000Z)".
- Correlação: `search_datadog_logs` sobre `metrics-server` mostrou probes falhando também **fora** desta janela — 09:06:07 10/09/2026 BRT (epoch 1789041967000 · 2026-09-10T12:06:07.000Z), 21:25:30 10/09/2026 BRT (epoch 1789086330000 · 2026-09-11T00:25:30.000Z), 08:50:35 11/09/2026 BRT (epoch 1789127435000 · 2026-09-11T11:50:35.000Z), 08:58:21 11/09/2026 BRT (epoch 1789127901000 · 2026-09-11T11:58:21.000Z), 11:36:51 11/09/2026 BRT (epoch 1789137411000 · 2026-09-11T14:36:51.000Z) — em hosts diferentes e no ambiente `development`, indicando que o problema é do componente `metrics-server`, contínuo, não específico do namespace `medprev-metabase`.

## Evidência

- 14 ocorrências de `FailedComputeMetricsReplicas` no namespace `medprev-metabase` entre `window_from`: "16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z)" e `window_to`: "16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z)" — https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-metabase%20FailedComputeMetricsReplicas&from_ts=1788808256645&to_ts=1789153856645&live=false
- `search_datadog_events` sobre essa mesma query devolveu 9 de 14 eventos na primeira página (truncado pela própria ferramenta, não por mim), todos emitidos pelo `horizontal-pod-autoscaler medprev-metabase/medprev-metabase`, alternando entre duas causas de erro no metrics-server ("server currently unable to handle the request" e "no metrics returned").
- `search_datadog_logs` com `kube_namespace:kube-system (metrics-server OR *metrics-server*)` na mesma janela devolveu 8 logs no total (5 exibidos), todos `status:error`, mensagem de probe `metric-storage-ready` falhando — URL retornada pela própria ferramenta: https://app.datadoghq.com/logs?from_ts=1788808256645&live=false&query=kube_namespace%3Akube-system+%28metrics-server+OR+%2Ametrics-server%2A%29&stream_sort=desc&to_ts=1789153856645
- Não consultei `search_datadog_spans`/`aggregate_spans`: este achado é um evento de control-plane do Kubernetes (HPA), sem `trace_id` associado — não há span de aplicação a inspecionar para este tipo de fonte.

## Ação recomendada

Ação de infraestrutura no `metrics-server` do cluster `eks-medprev-online-prd` (recursos/réplicas/health do add-on), não no código do Metabase — ver "Corpo da issue" para detalhes de investigação e critério de validação.

## Corpo da issue

### Descrição do incidente
O HorizontalPodAutoscaler do namespace `medprev-metabase`, no cluster `eks-medprev-online-prd`, não consegue calcular réplicas (`FailedComputeMetricsReplicas`) por falha ao obter métricas de CPU/memória via `pods.metrics.k8s.io`. Impacto observável: o HPA fica sem dado para decidir scaling durante essas janelas — risco de não escalar o Metabase sob carga. Os logs do próprio `metrics-server` mostram o mesmo tipo de falha (`probe="metric-storage-ready" err="no metrics to serve"`) em outros hosts e no ambiente `development`, sugerindo problema do componente, não do namespace.

### Causa raiz
Sinal (não ruído) — falha real do `metrics-server`, corroborada por logs do próprio componente com múltiplas ocorrências de probe falhando fora da janela do achado (não há classificação handled/unhandled aplicável a eventos de control-plane do Kubernetes). Causa raiz interna do metrics-server (recurso insuficiente, scrape do kubelet, etc.) **não determinada** com as consultas feitas — só o sintoma foi confirmado.

### Linha do tempo
Ver seção "## Linha do tempo" acima — 9 dos 14 eventos do HPA em 2026-09-09 (entre 00:22:57 09/09/2026 BRT (epoch 1788924177000 · 2026-09-09T03:22:57.000Z) e 07:54:37 09/09/2026 BRT (epoch 1788951277000 · 2026-09-09T10:54:37.000Z)), mais falhas de probe do `metrics-server` continuando até 11:36:51 11/09/2026 BRT (epoch 1789137411000 · 2026-09-11T14:36:51.000Z), além do `last_seen` do achado ("21:27:37 10/09/2026 BRT (epoch 1789086457000 · 2026-09-11T00:27:37.000Z)").

### Evidências
- Events Explorer (query fixada na janela): https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-metabase%20FailedComputeMetricsReplicas&from_ts=1788808256645&to_ts=1789153856645&live=false
- Logs Explorer (`metrics-server`, mesma janela): https://app.datadoghq.com/logs?from_ts=1788808256645&live=false&query=kube_namespace%3Akube-system+%28metrics-server+OR+%2Ametrics-server%2A%29&stream_sort=desc&to_ts=1789153856645

### Ação recomendada
`target_repo`: nulo — infra, sem repositório de código; ação operacional. Investigar a saúde do add-on `metrics-server` no cluster `eks-medprev-online-prd` (requests/limits do pod, réplicas, eventos de restart/OOM, latência de scrape do kubelet) — o mesmo padrão de falha aparece em `development`, então vale checar se é uma versão/config compartilhada do add-on. Validar a correção monitorando ausência de novos eventos `FailedComputeMetricsReplicas` e de logs `probe="metric-storage-ready" err="no metrics to serve"` por pelo menos 24h após a mudança.

### Volume
14 ocorrências entre `window_from`: "16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z)" e `window_to`: "16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z)". `search_datadog_events` com a mesma query e janela também retornou 14 no metadado `count` (9 exibidos na página) — consistente com `observed_count`.

### Severidade e criticidade
`severity` do achado: `medium`. Como classifiquei como sinal (não ruído), a severidade se aplica ao próprio evento. Criticidade para o negócio (inferência): média — o HPA sem métricas não escala automaticamente sob pico de carga do Metabase, mas não há indício, nas consultas feitas, de indisponibilidade do serviço ou perda de dados; o defeito real (metrics-server falhando cluster-wide, inclusive em `development`) pode ter criticidade maior que a do achado original se afetar HPAs de outros namespaces — isso não foi verificado nesta investigação.
