---
fingerprint: k8s-eks-medprev-online-prd-Unhealthy-external-dns
source: kubernetes
reason: Unhealthy
novelty: new
service: external-dns
environment: production
window:
  from: 1788814356569
  to: 1789159956569
observed:
  count: 1
  first_seen: 1789087464000
  last_seen: 1789087464000
severity: medium
state: new
cost:
  input_tokens: 446237
  output_tokens: 8870
  cache_read_input_tokens: 346096
  cache_creation_input_tokens: 100131
  duration_s: 93.931
  usd: 0.5630472
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aexternal-dns%20Unhealthy&from_ts=1788814356569&to_ts=1789159956569&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aexternal-dns%20Unhealthy&from_ts=1788814356569&to_ts=1789159956569&live=false

## Causa raiz

**Ruído.** O único evento (`observed_count: 1`, na janela 17:52:36 07/09/2026 BRT (epoch 1788814356569 · 2026-09-07T20:52:36.569Z) até 17:52:36 11/09/2026 BRT (epoch 1789159956569 · 2026-09-11T20:52:36.569Z)) é uma falha de readiness probe (`connection refused` na porta 7979/healthz) do pod `cloudflare-external-dns-588fc7566-wstm2`, no namespace `external-dns` do cluster `eks-medprev-online-prd`. Reconstruindo o histórico completo do pod, o evento **Unhealthy** ocorre 2 segundos depois de um evento **Killing** disparado pelo Karpenter para consolidação de nó (`Nominated: Pod should schedule on: nodeclaim/default-vxxmz`) — ou seja, o kubelet sondou o container exatamente no instante em que ele já estava sendo encerrado para reagendamento em outro nó, não por falha de aplicação. O mesmo padrão (Killing por Karpenter → novo pod agendado → Pulling/Started) se repete pelo menos 6 vezes ao longo da janela (08/09, 09/09 ×3, 10/09), incluindo um `Evicted: Underutilized` explícito do Karpenter — é o comportamento normal de consolidação de nós desse nodepool, não uma degradação do serviço. Os logs de aplicação do `external-dns` no horário do evento (1012 logs numa janela de amostragem de ~1h24 em torno do horário) são 100% `status:info` ("record(s) were successfully updated", "Changing record"), sem nenhum erro correlacionado. Não há spans APM para `service:external-dns` (0 resultados) — o componente não é instrumentado com tracing, então a classificação `handled`/`unhandled` não se aplica; a equivalente aqui é: 1 evento Unhealthy, 100% explicado por um evento Killing de infraestrutura, 0% por falha de aplicação.

## Linha do tempo

- 21:23:27 10/09/2026 BRT (epoch 1789086207000 · 2026-09-11T00:23:27.000Z) Pod `cloudflare-external-dns-588fc7566-wstm2` agendado no nó `ip-10-0-1-50` (`Scheduled`). Consulta: `pod_name:cloudflare-external-dns-588fc7566-wstm2`.
- 21:23:41 10/09/2026 BRT (epoch 1789086221000 · 2026-09-11T00:23:41.000Z) Container `external-dns` criado, imagem puxada e iniciado (`Created`/`Pulled`/`Started`). Mesma consulta.
- 21:44:22 10/09/2026 BRT (epoch 1789087462000 · 2026-09-11T00:44:22.000Z) Karpenter emite `Killing: Stopping container external-dns` + `Nominated: Pod should schedule on: nodeclaim/default-vxxmz, node/ip-10-0-0-113` — início da consolidação/substituição do nó. Mesma consulta.
- 21:44:23 10/09/2026 BRT (epoch 1789087463000 · 2026-09-11T00:44:23.000Z) Task do containerd deletada com exit code 0 — encerramento limpo, não crash. Mesma consulta.
- 21:44:24 10/09/2026 BRT (epoch 1789087464000 · 2026-09-11T00:44:24.000Z) **Evento do achado**: `Unhealthy: Readiness probe failed: Get "http://10.0.0.32:7979/healthz": dial tcp 10.0.0.32:7979: connect: connection refused` — sonda chegou após o container já estar sendo finalizado. Evidência: `evidence_links[0]` (Events Explorer, query `source:kubernetes env:production status:warn kube_namespace:external-dns Unhealthy`).
- 21:44:24 10/09/2026 BRT (epoch 1789087464000 · 2026-09-11T00:44:24.000Z) Container deletado pelo containerd — fim do ciclo de vida do pod substituído. Mesma consulta.

Padrão recorrente de churn por consolidação do Karpenter (mesmo mecanismo, outros pods/namespaces, fora do fingerprint deste achado, usados só como contexto): 01:01:42 08/09/2026 BRT (epoch 1788840102000 · 2026-09-08T04:01:42.000Z) `Evicted: Underutilized` + `Killing`; 00:31:23 09/09/2026 BRT (epoch 1788924683000 · 2026-09-09T03:31:23.000Z) `Killing` + novo pod criado; 07:55:16 09/09/2026 BRT (epoch 1788951316000 · 2026-09-09T10:55:16.000Z) `Killing` + novo pod criado; 20:01:32 09/09/2026 BRT (epoch 1788994892000 · 2026-09-09T23:01:32.000Z) `Killing` + novo pod criado; 21:16:22 09/09/2026 BRT (epoch 1788999382000 · 2026-09-10T00:16:22.000Z) `Killing` + novo pod criado. Consulta: `kube_namespace:external-dns env:production cluster_name:eks-medprev-online-prd`.

## Evidência

- Evento único do achado, com toda a sequência de causa (Killing → Unhealthy → deleted) do próprio pod: `pod_name:cloudflare-external-dns-588fc7566-wstm2` — 7 eventos retornados na janela.
- Padrão de churn recorrente do namespace inteiro: `kube_namespace:external-dns env:production cluster_name:eks-medprev-online-prd` — 54 eventos retornados na janela (truncado em 29 exibidos), todos ciclos de Killing/Create/Pulling por Karpenter.
- Ausência de erro de aplicação: `search_datadog_logs` com `service:external-dns env:production status:error` na janela do achado — **0 logs retornados**.
- Aplicação saudável no horário do evento: `search_datadog_logs` com `service:external-dns env:production` (sem filtro de status), janela de amostra 2026-09-11 ~00:43–02:03 — **1012 logs, 100% `status:info`**.
- Ausência de instrumentação de tracing: `search_datadog_spans` com `service:external-dns` na janela do achado — **0 spans** (componente não emite APM).
- Link pronto: [evidence_links[0] — Events Explorer](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aexternal-dns%20Unhealthy&from_ts=1788814356569&to_ts=1789159956569&live=false).

## Ação recomendada

Nenhuma ação de código: é ruído operacional do Karpenter consolidando nós. Ação de infraestrutura opcional — ajustar `terminationGracePeriodSeconds`/`preStop` ou o `disruption budget` do nodepool `default` para que o pod pare de responder à readiness probe antes do SIGTERM, eliminando o falso-positivo no Error Tracking/Events sem alterar o comportamento real de consolidação.

## Corpo da issue

### Descrição do incidente
O Events Explorer do Datadog registrou 1 evento `Unhealthy` (readiness probe failed, connection refused na porta 7979) para o pod `cloudflare-external-dns-588fc7566-wstm2`, no namespace `external-dns` do cluster `eks-medprev-online-prd`, entre 17:52:36 07/09/2026 BRT (epoch 1788814356569 · 2026-09-07T20:52:36.569Z) e 17:52:36 11/09/2026 BRT (epoch 1789159956569 · 2026-09-11T20:52:36.569Z). Não há impacto observável no usuário nem no sistema: o pod foi substituído normalmente pelo ReplicaSet e a aplicação continuou operando (logs 100% `info` no mesmo horário).

### Causa raiz
Ruído — 1 evento Unhealthy, 100% explicado por um evento `Killing` de infraestrutura 2 segundos antes (0% atribuível a falha de aplicação; 0 spans/0 erros de log correlacionados). A causa confirmada nas evidências é a race entre o kubelet's readiness probe e o encerramento do container disparado pelo Karpenter para consolidação de nó (`Nominated: nodeclaim/default-vxxmz`), parte de um padrão recorrente de churn do mesmo tipo observado ao menos 6 vezes na janela.

### Linha do tempo
- 21:23:27 10/09/2026 BRT (epoch 1789086207000 · 2026-09-11T00:23:27.000Z) pod agendado no nó `ip-10-0-1-50`.
- 21:23:41 10/09/2026 BRT (epoch 1789086221000 · 2026-09-11T00:23:41.000Z) container criado e iniciado.
- 21:44:22 10/09/2026 BRT (epoch 1789087462000 · 2026-09-11T00:44:22.000Z) Karpenter inicia `Killing` para consolidação, nomeando o nó de destino `ip-10-0-0-113`.
- 21:44:23 10/09/2026 BRT (epoch 1789087463000 · 2026-09-11T00:44:23.000Z) task do containerd encerrada com exit code 0 (encerramento limpo).
- 21:44:24 10/09/2026 BRT (epoch 1789087464000 · 2026-09-11T00:44:24.000Z) readiness probe falha por `connection refused` — evento do achado, ocorrido durante o encerramento já em andamento.
- 21:44:24 10/09/2026 BRT (epoch 1789087464000 · 2026-09-11T00:44:24.000Z) container deletado.
- Correlação: mesmo padrão Killing→recreate por consolidação do Karpenter em 01:01:42 08/09/2026 BRT (epoch 1788840102000 · 2026-09-08T04:01:42.000Z), 00:31:23 09/09/2026 BRT (epoch 1788924683000 · 2026-09-09T03:31:23.000Z), 07:55:16 09/09/2026 BRT (epoch 1788951316000 · 2026-09-09T10:55:16.000Z), 20:01:32 09/09/2026 BRT (epoch 1788994892000 · 2026-09-09T23:01:32.000Z) e 21:16:22 09/09/2026 BRT (epoch 1788999382000 · 2026-09-10T00:16:22.000Z) — não há deploy de versão correlacionado (imagem seguiu `0.15.0-debian-12-r1` em todos os ciclos).

### Evidências
- Events Explorer (query fixada na janela): https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aexternal-dns%20Unhealthy&from_ts=1788814356569&to_ts=1789159956569&live=false
- Consulta de logs de erro (`service:external-dns env:production status:error`, mesma janela): 0 resultados.
- Consulta de logs gerais (`service:external-dns env:production`, amostra ~2026-09-11 00:43–02:03): 1012 logs, 100% `status:info`.
- Consulta de spans (`service:external-dns`, mesma janela): 0 spans — serviço sem instrumentação APM.
- Consulta de eventos do pod específico (`pod_name:cloudflare-external-dns-588fc7566-wstm2`, mesma janela): 7 eventos.
- Consulta do padrão de churn (`kube_namespace:external-dns env:production cluster_name:eks-medprev-online-prd`, mesma janela): 54 eventos.

### Ação recomendada
`target_repo` é nulo — infra, sem repositório de código; ação operacional. Componente: nodepool `default` do Karpenter e/ou `spec.template.spec.terminationGracePeriodSeconds`/`readinessProbe` do Helm chart `external-dns` (`kube_deployment: cloudflare-external-dns`, chart `external-dns-8.3.8`). Mudança sugerida: adicionar um `preStop` hook (ex.: `sleep` curto) ou reduzir a janela em que a readiness probe continua rodando após o SIGTERM ser enviado, para que o Karpenter pare de gerar eventos `Unhealthy` como efeito colateral de consolidações normais. Validação: após o ajuste, repetir a mesma query do Events Explorer por 7 dias e confirmar ausência de novos eventos `Unhealthy` coincidindo com eventos `Killing` do Karpenter no namespace `external-dns`.

### Volume
1 ocorrência entre 17:52:36 07/09/2026 BRT (epoch 1788814356569 · 2026-09-07T20:52:36.569Z) e 17:52:36 11/09/2026 BRT (epoch 1789159956569 · 2026-09-11T20:52:36.569Z) (`observed_count`). Não foi feita nenhuma consulta com filtro/janela diferente que tenha retornado um total divergente para este `Reason` específico.

### Severidade e criticidade
`severity: medium` no achado — não se aplica ao evento em si, que é ruído confirmado. Avaliação de criticidade do defeito real encontrado (inferência): baixa — é apenas um artefato cosmético no Error Tracking/Events causado pela ordem de operações entre probe e terminação durante consolidação de nó; não há indício de impacto em resolução de DNS, disponibilidade do serviço ou dados.
