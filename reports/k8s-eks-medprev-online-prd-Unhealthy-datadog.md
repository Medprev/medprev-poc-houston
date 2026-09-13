---
fingerprint: k8s-eks-medprev-online-prd-Unhealthy-datadog
source: kubernetes
reason: Unhealthy
novelty: new
service: datadog
environment: production
window:
  from: 1788808256645
  to: 1789153856645
observed:
  count: 23
  first_seen: 1788864348000
  last_seen: 1789142563000
severity: medium
state: new
cost:
  input_tokens: 327800
  output_tokens: 9398
  cache_read_input_tokens: 240241
  cache_creation_input_tokens: 87551
  duration_s: 100.231
  usd: 0.4968292
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Adatadog%20Unhealthy&from_ts=1788808256645&to_ts=1789153856645&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Adatadog%20Unhealthy&from_ts=1788808256645&to_ts=1789153856645&live=false

## Causa raiz

O achado é sobre o namespace `datadog` (DaemonSet do Datadog Agent + Cluster Agent) no cluster `eks-medprev-online-prd`, componente de infraestrutura sem repositório de código próprio (`target_repo: null`). Consultei o Events Explorer com a própria `query` do achado e recuperei as 23 ocorrências completas dentro da janela de coleta (16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) – 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z)) — bate exatamente com `observed_count: 23`.

Padrão observado: cada uma das 23 ocorrências acontece em um **pod diferente**, em um **node diferente** (`kube_node`/`host_provider_id` distintos em quase todas), e nenhum pod se repete na janela. Duas naturezas de falha de probe: ~17 ocorrências são `connection refused` na porta 5555/5556 (processo do agent ainda não escutava) e ~6 são `HTTP probe failed with statuscode: 500` (processo já escutando, mas ainda não pronto internamente) — ambas típicas de probe disparando durante a inicialização do pod, não de uma falha sustentada. Rodei também uma busca por eventos correlatos de `BackOff`, `Restarted`, `Killing`, `Pulled`, `Failed` no mesmo namespace/janela e o resultado retornado foi idêntico ao conjunto de 23 "Unhealthy" (nenhum evento adicional de crash/restart) — ou seja, não há evidência de CrashLoopBackOff nem de terminação de pod correlacionada.

**Classificação: sinal fraco / ruído operacional, não confirmado como defeito de aplicação.** Não há `@error.handling`/`@http.status_code` de spans APM para classificar (ver evidência abaixo — 0 spans), porque o Datadog Agent não é instrumentado com APM; a classificação equivalente aqui é "1 ocorrência isolada por pod, sem repetição, sem evento de crash correlato" = comportamento consistente com corrida entre o probe de readiness e a inicialização do processo em pods novos, não com uma falha persistente do agente.

**Não determinei a causa raiz da renovação de pods/nodes em si** (não consultei eventos de ciclo de vida de node/Karpenter para confirmar se são nodes novos sendo provisionados) — trato isso explicitamente como não verificado, e não devo afirmar "é o Karpenter" sem essa consulta.

Consultas efetivamente rodadas e retorno:
- `search_datadog_events` com a query do achado, janela completa → 23 eventos (usado para a linha do tempo abaixo).
- `search_datadog_logs` com `kube_namespace:datadog service:datadog-agent env:production status:(error OR warn)`, mesma janela → 0 logs.
- `search_datadog_logs` com `kube_namespace:datadog env:production`, janela estreita em torno do primeiro evento → 2 logs, ambos `service:operator`, nível `info` (nenhum erro/warn).
- `aggregate_spans` com `service:datadog-agent env:production`, mesma janela, agrupado por `@http.status_code`/`@error.handling` → 0 buckets (sem spans APM, esperado para este componente).
- `search_datadog_events` com filtro adicional `(BackOff OR Restarted OR Killing OR Pulled OR Failed)` → mesmos 23 eventos, nenhum evento adicional de crash/restart encontrado.

## Linha do tempo

- 07:45:48 08/09/2026 BRT (epoch 1788864348000 · 2026-09-08T10:45:48.000Z) — Readiness probe falha (`connection refused` :5555) no pod `datadog-bvzfx`, node `ip-10-0-4-196` — primeira ocorrência da janela (`first_seen`). Consulta: Events Explorer (namespace + Reason, janela fixada).
- 16:38:48 08/09/2026 BRT (epoch 1788896328000 · 2026-09-08T19:38:48.000Z) — mesmo padrão, pod `datadog-8vwv6`, node `ip-10-0-0-150`.
- 00:21:38 09/09/2026 BRT (epoch 1788924098000 · 2026-09-09T03:21:38.000Z) — pod `datadog-t7lnz`, node `ip-10-0-10-52`, `connection refused` :5555.
- 00:25:46 09/09/2026 BRT (epoch 1788924346000 · 2026-09-09T03:25:46.000Z) — `datadog-cluster-agent-566cbd77d5-cq5hh`, `connection refused` :5556.
- 00:27:51 09/09/2026 BRT (epoch 1788924471000 · 2026-09-09T03:27:51.000Z) — `datadog-7b59k`, readiness `HTTP 500` (processo já escutando).
- 00:28:01 09/09/2026 BRT (epoch 1788924481000 · 2026-09-09T03:28:01.000Z) — `datadog-cluster-agent-566cbd77d5-qljbg`, liveness **e** readiness `HTTP 500` simultâneos.
- 00:35:26 09/09/2026 BRT (epoch 1788924926000 · 2026-09-09T03:35:26.000Z) — `datadog-lrxpt`, readiness `HTTP 500`.
- 07:28:04 09/09/2026 BRT (epoch 1788949684000 · 2026-09-09T10:28:04.000Z) — `datadog-gpfrg`, `connection refused` :5555.
- 07:56:40 09/09/2026 BRT (epoch 1788951400000 · 2026-09-09T10:56:40.000Z) — `datadog-tksg7`, readiness `HTTP 500`.
- 20:00:37 09/09/2026 BRT (epoch 1788994837000 · 2026-09-09T23:00:37.000Z) — `datadog-zwdsk`, `connection refused` :5555.
- 21:33:50 09/09/2026 BRT (epoch 1789000430000 · 2026-09-10T00:33:50.000Z) — `datadog-6wwtf`, `connection refused` :5555.
- 01:35:30 10/09/2026 BRT (epoch 1789014930000 · 2026-09-10T04:35:30.000Z) — `datadog-c6chm`, `connection refused` :5555.
- 21:27:04 10/09/2026 BRT (epoch 1789086424000 · 2026-09-11T00:27:04.000Z) — `datadog-2744q`, `connection refused` :5555.
- 21:27:43 10/09/2026 BRT (epoch 1789086463000 · 2026-09-11T00:27:43.000Z) — `datadog-5jwkc`, evento agregado (3 ocorrências) de readiness `HTTP 500`.
- 22:29:04 10/09/2026 BRT (epoch 1789090144000 · 2026-09-11T01:29:04.000Z) — `datadog-9vkgk`, `connection refused` :5555.
- 00:27:43 11/09/2026 BRT (epoch 1789097263000 · 2026-09-11T03:27:43.000Z) — `datadog-srpsw`, `connection refused` :5555.
- 00:45:50 11/09/2026 BRT (epoch 1789098350000 · 2026-09-11T03:45:50.000Z) — `datadog-qq4gx`, `connection refused` :5555.
- 03:23:45 11/09/2026 BRT (epoch 1789107825000 · 2026-09-11T06:23:45.000Z) — `datadog-9tw9q`, `connection refused` :5555.
- 04:19:25 11/09/2026 BRT (epoch 1789111165000 · 2026-09-11T07:19:25.000Z) — `datadog-m7brk`, `connection refused` :5555.
- 06:51:05 11/09/2026 BRT (epoch 1789120265000 · 2026-09-11T09:51:05.000Z) — `datadog-cgpp9`, readiness `HTTP 500`.
- 07:50:48 11/09/2026 BRT (epoch 1789123848000 · 2026-09-11T10:50:48.000Z) — `datadog-gl57q`, `connection refused` :5555.
- 10:15:17 11/09/2026 BRT (epoch 1789132517000 · 2026-09-11T13:15:17.000Z) — `datadog-mwpfq`, `connection refused` :5555.
- 13:02:43 11/09/2026 BRT (epoch 1789142563000 · 2026-09-11T16:02:43.000Z) — `datadog-gwsv8`, `connection refused` :5555 — última ocorrência da janela (bate com `last_seen`: 13:02:43 11/09/2026 BRT (epoch 1789142563000 · 2026-09-11T16:02:43.000Z)).

Não encontrei, na mesma janela, nenhum evento de restart/crash/kill correlacionado a esses pods (consulta específica retornou o mesmo conjunto de 23, sem adicionais).

## Evidência

- 23 eventos "Unhealthy" no namespace `datadog`, todos em pods distintos, dentro da janela 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) – 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z) — Events Explorer (namespace + Reason, janela fixada).
- Nenhum log de erro/warn do `service:datadog-agent` no mesmo namespace/janela — consulta `kube_namespace:datadog service:datadog-agent env:production status:(error OR warn)`, 0 resultados.
- Únicos logs no namespace na janela estreita em torno da primeira ocorrência são `service:operator`, nível `info` — consulta `kube_namespace:datadog env:production`, janela 1788864000000–1788864700000, 2 resultados.
- Nenhum span APM para `service:datadog-agent` na janela (esperado, componente sem instrumentação) — `aggregate_spans` query `service:datadog-agent env:production`, 0 buckets.
- Nenhum evento correlato de restart/crash (`BackOff`, `Restarted`, `Killing`, `Pulled`, `Failed`) no mesmo namespace/janela além dos 23 já contados — mesma query de eventos com esses termos OR-ados, 23 resultados idênticos aos originais.

## Ação recomendada

Infra — sem repositório de código, ação operacional: revisar o `initialDelaySeconds`/`periodSeconds` do readiness/liveness probe do DaemonSet `datadog`/`datadog-cluster-agent` (Helm chart ou manifest do Datadog Operator) para tolerar o tempo de inicialização do agente em pods recém-agendados, e confirmar via consulta de eventos de ciclo de vida de node (não feita aqui) se a causa da renovação frequente de pods é rotação de nodes.

## Corpo da issue

### Descrição do incidente
23 eventos "Unhealthy" (readiness/liveness probe) no namespace `datadog` do cluster `eks-medprev-online-prd`, entre 07/09/2026 e 11/09/2026, um por pod distinto do DaemonSet `datadog`/`datadog-cluster-agent`, sem repetição no mesmo pod. Impacto observável: nenhum — não há evidência de indisponibilidade sustentada do agente nem de perda de telemetria, apenas o evento de probe em si.

### Causa raiz
Ruído operacional / sinal fraco, não confirmado como defeito: os 23 eventos ocorrem um por pod (nunca dois na mesma instância), sendo ~17 `connection refused` (processo ainda não escutava) e ~6 `HTTP 500` (processo escutando mas ainda inicializando), sem nenhum evento de crash/restart/kill correlacionado na mesma janela. Isso é consistente com o probe disparando durante a janela normal de startup do pod, não com falha persistente do agente. Não determinei se há renovação anormal de nodes por trás disso (nenhuma consulta de ciclo de vida de node foi executada) — não inventar essa causa.

### Linha do tempo
Ver lista completa na seção `## Linha do tempo` acima: 23 eventos entre 07:45:48 08/09/2026 BRT (epoch 1788864348000 · 2026-09-08T10:45:48.000Z) (primeira ocorrência) e 13:02:43 11/09/2026 BRT (epoch 1789142563000 · 2026-09-11T16:02:43.000Z) (última ocorrência), cada um em pod/node distinto, sem eventos de crash/restart correlacionados encontrados.

### Evidências
- Events Explorer (namespace + Reason, janela fixada): https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Adatadog%20Unhealthy&from_ts=1788808256645&to_ts=1789153856645&live=false
- Consulta de logs `kube_namespace:datadog service:datadog-agent env:production status:(error OR warn)` na mesma janela → 0 resultados.
- Consulta de spans `service:datadog-agent env:production` na mesma janela, agrupada por `@http.status_code`/`@error.handling` → 0 spans (sem instrumentação APM neste componente).
- Consulta de eventos correlatos `(BackOff OR Restarted OR Killing OR Pulled OR Failed)` no mesmo namespace/janela → mesmos 23 eventos, nenhum adicional.

### Ação recomendada
Infra — sem repositório de código, ação operacional. Revisar a configuração de `readinessProbe`/`livenessProbe` (`initialDelaySeconds`, `periodSeconds`, `failureThreshold`) do Helm chart/Datadog Operator usado para o DaemonSet `datadog` e o Deployment `datadog-cluster-agent` neste cluster, ajustando para tolerar o tempo real de inicialização observado (probe falhando enquanto a porta 5555/5556 ainda não está aberta). Validar rodando uma nova janela de coleta após o ajuste e confirmando queda no `observed_count` deste fingerprint para próximo de zero. Complementarmente, investigar via eventos de node/Karpenter (fora do escopo desta consulta) se há renovação de nodes acima do esperado, o que explicaria por que cada ocorrência acontece sempre em um pod novo.

### Volume
23 ocorrências na janela 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) – 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z). A consulta que rodei no Events Explorer, na mesma janela, retornou o mesmo total (23) — sem divergência.

### Severidade e criticidade
`severity` do achado é `medium`, mas essa classificação não se aplica bem ao padrão observado: trata-se de eventos isolados por pod, sem repetição e sem correlação com crash/restart, compatíveis com o probe disparando durante inicialização normal. Avaliação de criticidade (inferência): **baixa** — não há evidência de indisponibilidade do agente ou perda de dados de observabilidade; o único efeito é ruído nos Kubernetes Events, que pode ocultar sinais mais graves nesse mesmo namespace se acumulado. Recomendo tratar como ajuste de tuning de probe, não como incidente.
