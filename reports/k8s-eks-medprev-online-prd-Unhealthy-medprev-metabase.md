---
fingerprint: k8s-eks-medprev-online-prd-Unhealthy-medprev-metabase
source: kubernetes
reason: Unhealthy
novelty: new
service: medprev-metabase
environment: production
window:
  from: 1788808256645
  to: 1789153856645
observed:
  count: 2
  first_seen: 1788924556000
  last_seen: 1788924566000
severity: medium
state: new
cost:
  input_tokens: 380827
  output_tokens: 7858
  cache_read_input_tokens: 313998
  cache_creation_input_tokens: 66819
  duration_s: 86.724
  usd: 0.41331260000000003
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-metabase%20Unhealthy&from_ts=1788808256645&to_ts=1789153856645&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-metabase%20Unhealthy&from_ts=1788808256645&to_ts=1789153856645&live=false

## Causa raiz

O pod `medprev-metabase-57bdcc4cdd-29t7t` (namespace `medprev-metabase`, cluster `eks-medprev-online-prd`) recebeu dois eventos `Unhealthy` do startup probe (HTTP 503) às 03:29:16Z e 03:29:26Z de 09/09/2026, durante um deploy Helm/ArgoCD que iniciou o rollout do pod às 03:29:02Z. Correlacionando com os logs de aplicação do próprio pod: o JVM subiu, a Jetty foi lançada às 03:28:32,547 e o Metabase só terminou a inicialização às 03:29:34,721 ("Metabase Initialization COMPLETE in 1.0 mins (JVM uptime: 2.3 mins)") — ou seja, os dois `Unhealthy` ocorreram *enquanto* o Metabase ainda estava de boot, 8–18s antes dele ficar pronto, e o deployment ficou `kube_condition_available:true` às 03:29:45Z, minutos depois. Não há span/trace disponível para classificar `handled`/`unhandled` (Metabase não emite APM traces neste ambiente) — a classificação aqui vem da correlação evento↔log↔deploy, não de spans.

Isto é **ruído esperado de rollout**, não uma falha real: o pod nunca ficou indisponível para tráfego (o probe em questão é o startup probe, que só gate a liveness/readiness interna antes do pod entrar em serviço), e o serviço se recuperou sozinho. Agregando os mesmos eventos `Unhealthy` deste namespace nos últimos 30 dias, o padrão se repete a cada rollout: 2 ocorrências no pod `-29t7t`, 2 no pod `-fhbbq`, 1 no pod `-dl8b9` — sinal de que o startup probe está sistematicamente mais apertado que o tempo real de boot do Metabase (~1 min de inicialização + boot da JVM), não um incidente pontual.

## Linha do tempo

- 00:27:46 09/09/2026 BRT (epoch 1788924466000 · 2026-09-09T03:27:46.000Z) — pod inicia JVM: log "Maximum memory available to JVM: 6.0 GB" (log da aplicação, `service:medprev-metabase`).
- 00:28:32 09/09/2026 BRT (epoch 1788924512547 · 2026-09-09T03:28:32.547Z) — Jetty embarcado é lançado na porta 3000 (log "Launching Embedded Jetty Webserver").
- 00:29:02 09/09/2026 BRT (epoch 1788924542000 · 2026-09-09T03:29:02.000Z) — evento de deploy: "Deployment medprev-metabase deployed... namespace: medprev-metabase", `kube_condition_available:false`, `kube_condition_progressing:true` (Events Explorer, `source:change_tracking`).
- 00:29:16 09/09/2026 BRT (epoch 1788924556000 · 2026-09-09T03:29:16.000Z) — primeiro evento `Unhealthy`: "Startup probe failed: HTTP probe failed with statuscode: 503" no pod `medprev-metabase-57bdcc4cdd-29t7t` (query do achado).
- 00:29:26 09/09/2026 BRT (epoch 1788924566000 · 2026-09-09T03:29:26.000Z) — segundo evento `Unhealthy`, mesmo sintoma, mesmo pod (query do achado).
- 00:29:34 09/09/2026 BRT (epoch 1788924574712 · 2026-09-09T03:29:34.712Z) — log da aplicação: "Metabase Initialization COMPLETE" (1.0 min de boot, JVM uptime 2.3 min).
- 00:29:45 09/09/2026 BRT (epoch 1788924585000 · 2026-09-09T03:29:45.000Z) — evento de deploy: mesmo deployment agora com `kube_condition_available:true` — rollout concluído com sucesso (Events Explorer, `source:change_tracking`).

## Evidência

- Os dois eventos `Unhealthy` (503 no startup probe) dentro da janela: [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-metabase%20Unhealthy&from_ts=1788808256645&to_ts=1789153856645&live=false) — 2 ocorrências, ambas no pod `medprev-metabase-57bdcc4cdd-29t7t`.
- Deploy do mesmo serviço em curso na mesma janela de segundos: consulta `kube_namespace:medprev-metabase (source:change_tracking OR source:deployment_analysis)` de 00:29:02 09/09/2026 BRT (epoch 1788924542000 · 2026-09-09T03:29:02.000Z) a 00:29:45 09/09/2026 BRT (epoch 1788924585000 · 2026-09-09T03:29:45.000Z) — 2 eventos de deployment (`available:false→true`), sem link direto no achado (consulta executada via `search_datadog_events`).
- Logs de aplicação do próprio pod na janela 00:27:00 09/09/2026 BRT (epoch 1788924420000 · 2026-09-09T03:27:00.000Z)–00:32:00 09/09/2026 BRT (epoch 1788924720000 · 2026-09-09T03:32:00.000Z) confirmando boot em andamento: consulta `kube_namespace:medprev-metabase pod_name:medprev-metabase-57bdcc4cdd-29t7t`, 1156 logs no total nessa janela de 5 minutos (contagem do metadado da busca), sem nenhum erro de aplicação — só inicialização de drivers e JVM.
- Log específico de conclusão do boot: consulta `... (*Initialization* OR *ready* OR *listening*)` na janela 00:29:00 09/09/2026 BRT (epoch 1788924540000 · 2026-09-09T03:29:00.000Z)–00:30:30 09/09/2026 BRT (epoch 1788924630000 · 2026-09-09T03:30:30.000Z) — 2 registros, ambos "Metabase Initialization COMPLETE" às 21:29:34 08/09/2026 BRT (epoch 1788913774712 · 2026-09-09T00:29:34.712Z) (hora local do log, UTC-3).
- Recorrência do mesmo padrão em 30 dias: `aggregate_events` sobre `source:kubernetes kube_namespace:medprev-metabase Unhealthy`, agrupado por `pod_name`, janela `now-30d`–`now` → 3 pods distintos afetados (`-29t7t`: 2, `-fhbbq`: 2, `-dl8b9`: 1), todos coincidindo com rollouts, nenhum evento fora de uma janela de deploy.

## Ação recomendada

Aumentar `initialDelaySeconds`/`failureThreshold` do startup probe do Deployment `medprev-metabase` (Helm chart `medprev-helm-charts-application`) para cobrir o boot real observado (~1 min de inicialização Metabase + ~1.3 min de JVM, total ~2.3 min), e não é uma investigação de bug de aplicação.

## Corpo da issue

### Descrição do incidente
O startup probe do Deployment `medprev-metabase` (namespace `medprev-metabase`, cluster `eks-medprev-online-prd`) dispara `Unhealthy` (HTTP 503) durante o boot normal do pod em praticamente todo rollout, porque o probe testa antes do Metabase terminar de inicializar. Não há impacto observável para o usuário: o pod nunca serviu tráfego incorreto e o rollout sempre completou (`kube_condition_available:true` minutos depois). O impacto real é ruído operacional recorrente no Error/Event Tracking a cada deploy.

### Causa raiz
Ruído — não é um bug de aplicação. Medido: 2 eventos `Unhealthy` nesta janela, ambos correlacionados a segundos de um boot de JVM em andamento (Jetty subiu 03:28:32, init completo 03:29:34,721 — 1.0 min), sem nenhum erro de aplicação nos 1156 logs revisados da janela. Recorrência confirmada em 3 pods distintos nos últimos 30 dias, sempre coincidindo com rollout. O defeito real é a configuração do startup probe (janela apertada demais em relação ao tempo de boot conhecido do Metabase), não o comportamento da aplicação.

### Linha do tempo
1. 00:27:46 09/09/2026 BRT (epoch 1788924466000 · 2026-09-09T03:27:46.000Z) — JVM inicia (log "Maximum memory available to JVM: 6.0 GB").
2. 00:28:32 09/09/2026 BRT (epoch 1788924512547 · 2026-09-09T03:28:32.547Z) — Jetty embarcado sobe na porta 3000.
3. 00:29:02 09/09/2026 BRT (epoch 1788924542000 · 2026-09-09T03:29:02.000Z) — evento de deploy inicia rollout (`kube_condition_available:false`).
4. 00:29:16 09/09/2026 BRT (epoch 1788924556000 · 2026-09-09T03:29:16.000Z) — 1º `Unhealthy`: startup probe 503.
5. 00:29:26 09/09/2026 BRT (epoch 1788924566000 · 2026-09-09T03:29:26.000Z) — 2º `Unhealthy`: startup probe 503.
6. 00:29:34 09/09/2026 BRT (epoch 1788924574712 · 2026-09-09T03:29:34.712Z) — "Metabase Initialization COMPLETE" (boot de 1.0 min).
7. 00:29:45 09/09/2026 BRT (epoch 1788924585000 · 2026-09-09T03:29:45.000Z) — deploy conclui (`kube_condition_available:true`).

### Evidências
- Events Explorer (2 eventos `Unhealthy`): https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-metabase%20Unhealthy&from_ts=1788808256645&to_ts=1789153856645&live=false
- Consulta de deploy correlacionado: `kube_namespace:medprev-metabase (source:change_tracking OR source:deployment_analysis)`, janela 03:29:02Z–03:29:45Z, 2 eventos.
- Consulta de logs de aplicação: `kube_namespace:medprev-metabase pod_name:medprev-metabase-57bdcc4cdd-29t7t`, janela 03:27:00Z–03:32:00Z, 1156 logs, sem erros.
- Consulta de recorrência histórica: `aggregate_events` sobre `source:kubernetes kube_namespace:medprev-metabase Unhealthy`, `group_by pod_name`, últimos 30 dias — 3 pods afetados (2/2/1 ocorrências).

### Ação recomendada
Infra — sem repositório de código próprio (`target_repo: null`); ação operacional no Helm chart do Deployment `medprev-metabase` (`medprev-helm-charts-application`, gerenciado via ArgoCD, `argocd.argoproj.io/instance:medprev-metabase-main`). Ajustar `startupProbe.initialDelaySeconds`/`failureThreshold`/`periodSeconds` do container para cobrir com folga os ~2.3 min de JVM uptime até "Initialization COMPLETE" observados. Validar rodando um novo deploy e conferindo que a mesma query (`source:kubernetes env:production status:warn kube_namespace:medprev-metabase Unhealthy`) não produz eventos durante o rollout seguinte.

### Volume
`observed_count`: 2 ocorrências entre 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) e 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z). Consulta adicional de 30 dias (`now-30d`–`now`) devolveu 5 ocorrências totais no namespace, distribuídas em 3 pods — janela maior, portanto número maior, consistente com um evento por rollout.

### Severidade e criticidade
`severity` do achado é `medium`, mas não se aplica ao evento em si — é ruído esperado de boot. Criticidade real (inferência): baixa para o comportamento observado (autorrecuperável, sem impacto ao usuário), porém **médio-alta olhando adiante**: se o tempo de boot do Metabase aumentar (ex.: mais plugins, banco mais lento) sem ajuste do probe, o mesmo padrão pode evoluir para falha real de rollout (`CrashLoopBackOff`/rollback), então vale corrigir preventivamente mesmo sem incidente hoje.
