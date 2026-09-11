---
fingerprint: k8s-eks-medprev-online-prd-Unhealthy-medprev-n8n
source: kubernetes
reason: Unhealthy
novelty: new
service: medprev-n8n
environment: production
window:
  from: 1788806810930
  to: 1789152410930
observed:
  count: 73
  first_seen: 1788861931000
  last_seen: 1789141246000
severity: medium
state: promoted
cost:
  input_tokens: 431947
  output_tokens: 9460
  cache_read_input_tokens: 339808
  cache_creation_input_tokens: 92129
  duration_s: 102.743
  usd: 0.5357336
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: https://github.com/Medprev/medprev-product-backlog/issues/6433
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-n8n%20Unhealthy&from_ts=1788806810930&to_ts=1789152410930&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-n8n%20Unhealthy&from_ts=1788806810930&to_ts=1789152410930&live=false

## Causa raiz

O serviço é `medprev-n8n` (deployment `medprev-n8n`, imagem `n8nio/n8n:2.13.0`, gerenciado por Helm no cluster `eks-medprev-online-prd`), com o Reason `Unhealthy` do Kubernetes disparando por falhas de liveness/readiness probe (`GET http://<pod-ip>:5678/healthz` e `/healthz/readiness`) desde `07:05:31 08/09/2026 BRT (epoch 1788861931000 · 2026-09-08T10:05:31.000Z)` (`first_seen`) até `12:40:46 11/09/2026 BRT (epoch 1789141246000 · 2026-09-11T15:40:46.000Z)` (`last_seen`).

Não há spans de APM para `service:medprev-n8n` na janela (`aggregate_spans` com `query: "service:medprev-n8n"` de `1788806810930` a `1789152410930` retornou 0 buckets), então a classificação `handled`/`unhandled` de spans (aplicável a Error Tracking) **não se aplica** aqui — este é um evento de infraestrutura Kubernetes, não um erro de aplicação instrumentado.

Isto é **sinal**, não ruído: os logs de aplicação do próprio pod no momento da primeira falha (`kube_namespace:medprev-n8n pod_name:medprev-n8n-dcc8d6554-sksjd`, `1788861631000`–`1788862231000`) mostram, no mesmo intervalo do probe falhando, erros reais e repetidos do processo n8n: `"Details: Unexpected server response: 403"`, `"[runnner:js] Error: Failed to connect to n8n task broker at 127.0.0.1:5679"` e `"Task runner connection attempt failed: invalid or expired grant token"` — o processo principal do n8n não responde ao `healthz` enquanto sua conexão interna com o task broker (autenticada por um grant token) falha com 403. A distribuição por pod (`aggregate_events` agrupado por `pod_name`, mesma janela) mostra o evento espalhado por **15 pods distintos** (2 a 8 ocorrências cada, incluindo `medprev-n8n-redis-master-0` com 2), não concentrado num único pod defeituoso — é um padrão recorrente de inicialização, coincidindo com o repetido reagendamento de pods pelo Karpenter (`karpenter_nodepool:default` em todos os eventos).

## Linha do tempo

Passo a passo dos eventos dentro da janela (`window_from`: "15:46:50 07/09/2026 BRT (epoch 1788806810930 · 2026-09-07T18:46:50.930Z)" até `window_to`: "15:46:50 11/09/2026 BRT (epoch 1789152410930 · 2026-09-11T18:46:50.930Z)"), consultados via `search_datadog_events` com a `query` de `evidence_links` (retornou 73 no total; 20 exibidos por limite de resposta, ordem cronológica):

- 07:05:31 08/09/2026 BRT (epoch 1788861931000 · 2026-09-08T10:05:31.000Z) — pod `medprev-n8n-dcc8d6554-sksjd`: 3x liveness "connection refused" + 10x readiness "connection refused" (porta 5678).
- 07:05:40 08/09/2026 BRT (epoch 1788861940000 · 2026-09-08T10:05:40.000Z) — mesmo pod: 1x readiness HTTP 503.
- 07:06:01 08/09/2026 BRT (epoch 1788861961000 · 2026-09-08T10:06:01.000Z) — mesmo pod: liveness/readiness "context deadline exceeded" + 2x readiness 503.
- 07:06:09 08/09/2026 BRT (epoch 1788861969000 · 2026-09-08T10:06:09.000Z) — log de aplicação: `"Details: Unexpected server response: 403"` (task broker).
- 07:06:10 08/09/2026 BRT (epoch 1788861970000 · 2026-09-08T10:06:10.000Z) — mesmo pod: 2x liveness deadline exceeded + 3x readiness 503.
- 07:06:22 08/09/2026 BRT (epoch 1788861982000 · 2026-09-08T10:06:22.000Z) — mesmo pod: 3x liveness + 2x readiness deadline exceeded.
- 07:06:24 08/09/2026 BRT (epoch 1788861984000 · 2026-09-08T10:06:24.000Z) — logs de aplicação no mesmo pod: `"Unexpected server response: 403"`, `"Failed to connect to n8n task broker at 127.0.0.1:5679"`, `"Task runner connection attempt failed: invalid or expired grant token"`.
- 07:06:32 08/09/2026 BRT (epoch 1788861992000 · 2026-09-08T10:06:32.000Z) — mesmo pod: 4x liveness deadline exceeded (última ocorrência registrada para este pod).
- 07:06:34 08/09/2026 BRT (epoch 1788861994000 · 2026-09-08T10:06:34.000Z) — logs de aplicação: warnings de depreciação do Node (não relacionados à causa).
- 00:22:30 09/09/2026 BRT (epoch 1788924150000 · 2026-09-09T03:22:30.000Z) — pod `medprev-n8n-redis-master-0`: readiness probe com `rpc error: code = Canceled` (componente Redis do release, não o `n8n-main`).
- 00:25:14 09/09/2026 BRT (epoch 1788924314000 · 2026-09-09T03:25:14.000Z) — pod `medprev-n8n-dcc8d6554-kq8p2`: liveness + 10x readiness "connection refused".
- 00:25:24 09/09/2026 BRT (epoch 1788924324000 · 2026-09-09T03:25:24.000Z) — mesmo pod: readiness 503.
- 00:33:44 09/09/2026 BRT (epoch 1788924824000 · 2026-09-09T03:33:44.000Z) a 01:00:35 09/09/2026 BRT (epoch 1788926435000 · 2026-09-09T04:00:35.000Z) — pod `medprev-n8n-dcc8d6554-5jtht`: sequência análoga (connection refused → deadline exceeded → 503), 5 eventos.
- 03:47:00 09/09/2026 BRT (epoch 1788936420000 · 2026-09-09T06:47:00.000Z) a 03:47:34 09/09/2026 BRT (epoch 1788936454000 · 2026-09-09T06:47:34.000Z) — pod `medprev-n8n-dcc8d6554-h44m7`: mesma sequência, 4 eventos.
- 07:04:32 09/09/2026 BRT (epoch 1788948272000 · 2026-09-09T10:04:32.000Z) — pod `medprev-n8n-dcc8d6554-md788`: liveness + 3x readiness "connection refused" (último evento retornado no lote de 20; os 53 restantes seguem o mesmo padrão em outros pods, conforme a contagem por `pod_name` acima).

O padrão se repete de forma idêntica a cada novo pod que sobe (connection refused → deadline exceeded → 503 → recuperação), consistente com uma corrida de inicialização entre o probe e a conexão do task runner, não com uma falha isolada.

## Evidência

- 73 ocorrências de `Unhealthy` em `medprev-n8n` na janela do achado — [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-n8n%20Unhealthy&from_ts=1788806810930&to_ts=1789152410930&live=false).
- Distribuição por pod (15 pods distintos, 2–8 eventos cada) — consulta `aggregate_events`, `query: "source:kubernetes env:production status:warn kube_namespace:medprev-n8n Unhealthy"`, `group_by: pod_name`, janela `1788806810930`–`1789152410930`.
- 0 spans de APM para `service:medprev-n8n` na mesma janela — consulta `aggregate_spans`, `query: "service:medprev-n8n"`, mesma janela (`total_buckets: 0`), confirmando ausência de instrumentação de tracing para este serviço.
- Erros de aplicação coincidentes com a primeira falha do probe: 3 linhas de log com `status:info`/`status:error` contendo `"Unexpected server response: 403"`, `"Failed to connect to n8n task broker at 127.0.0.1:5679"` e `"Task runner connection attempt failed: invalid or expired grant token"` — consulta `search_datadog_logs`, `query: "kube_namespace:medprev-n8n pod_name:medprev-n8n-dcc8d6554-sksjd"`, janela `1788861631000`–`1788862231000` (103 logs no total nessa janela de 10 min, 6 exibidos).

## Ação recomendada

Investigar, no chart/values do Helm de `medprev-n8n`, o mecanismo de grant token do task runner interno (`N8N_RUNNERS_*` / broker na porta 5679) e o `initialDelaySeconds`/`periodSeconds` das probes de liveness/readiness — o probe está correndo contra um processo que ainda não terminou de autenticar seu task runner, gerando falhas 403/connection-refused recorrentes em toda subida de pod.

## Corpo da issue

### Descrição do incidente
O deployment `medprev-n8n` (namespace `medprev-n8n`, cluster `eks-medprev-online-prd`) apresenta o evento Kubernetes `Unhealthy` recorrente em toda inicialização de pod, com falhas de liveness e readiness probe contra `http://<pod-ip>:5678/healthz` e `/healthz/readiness`. Não há indicação de indisponibilidade total do serviço (o padrão afeta pods individuais durante a subida, não todos simultaneamente), mas o pod fica fora de rotação do Service enquanto o probe falha, e o padrão se repete a cada novo pod (deploy, reagendamento por Karpenter, etc.).

### Causa raiz
Sinal, não ruído — confirmado por 0 spans de APM (`service:medprev-n8n`, mesma janela) e por logs de aplicação reais coincidentes com a falha do probe. Nos logs do pod `medprev-n8n-dcc8d6554-sksjd` no instante da primeira falha, o processo n8n registra `"Failed to connect to n8n task broker at 127.0.0.1:5679"` e `"Task runner connection attempt failed: invalid or expired grant token"`, seguidos de `"Unexpected server response: 403"`. O padrão indica uma corrida de inicialização: o `/healthz` só responde depois que o processo autentica com sucesso seu task runner interno, e essa autenticação falha (403/grant token inválido) nas primeiras tentativas após o pod subir — reproduzido em 15 pods distintos na janela, não isolado a um pod.

### Linha do tempo
Ver seção `## Linha do tempo` acima — padrão idêntico (connection refused → deadline exceeded → 503 → recuperação) repetido em `medprev-n8n-dcc8d6554-{sksjd,kq8p2,5jtht,h44m7,md788,...}` entre 07:05:31 08/09/2026 BRT (epoch 1788861931000 · 2026-09-08T10:05:31.000Z) e 07:04:32 09/09/2026 BRT (epoch 1788948272000 · 2026-09-09T10:04:32.000Z) (amostra dos 73 eventos), mais um evento isolado e de causa distinta em `medprev-n8n-redis-master-0` (00:22:30 09/09/2026 BRT (epoch 1788924150000 · 2026-09-09T03:22:30.000Z), `rpc error: code = Canceled`, provavelmente não relacionado).

### Evidências
- [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-n8n%20Unhealthy&from_ts=1788806810930&to_ts=1789152410930&live=false) — 73 ocorrências na janela.
- `aggregate_events` (`kube_namespace:medprev-n8n Unhealthy`, `group_by: pod_name`, mesma janela) — 15 pods distintos afetados, 2–8 eventos cada.
- `aggregate_spans` (`service:medprev-n8n`, mesma janela) — 0 buckets, sem instrumentação APM.
- `search_datadog_logs` (`kube_namespace:medprev-n8n pod_name:medprev-n8n-dcc8d6554-sksjd`, janela `1788861631000`–`1788862231000`) — 103 logs, incluindo os três erros de task-broker/grant-token citados acima.

### Ação recomendada
Repositório: nenhum próprio da Medprev — a imagem é `n8nio/n8n` (upstream, `github.com/n8n-io/n8n`); ação é de configuração de infraestrutura (chart Helm do release `medprev-n8n`), sem repositório de código Medprev associado. Ajustar `initialDelaySeconds`/`failureThreshold` das probes de liveness/readiness do container `n8n-main` para tolerar o tempo real de handshake do task runner com o broker interno (porta 5679), e/ou investigar por que o grant token do task runner chega inválido/expirado na primeira tentativa de cada subida (possível corrida entre geração do token e o healthcheck). Validar monitorando a mesma query de eventos (`kube_namespace:medprev-n8n Unhealthy`) por 96h após o ajuste e confirmando queda para o volume basal de outros namespaces comparáveis.

### Volume
73 ocorrências entre `window_from` "15:46:50 07/09/2026 BRT (epoch 1788806810930 · 2026-09-07T18:46:50.930Z)" e `window_to` "15:46:50 11/09/2026 BRT (epoch 1789152410930 · 2026-09-11T18:46:50.930Z)".

### Severidade e criticidade
`severity` do achado: medium. Criticidade de negócio (inferência): impacto operacional moderado — o n8n é uma plataforma de automação; o padrão observado tira pods individuais de rotação durante a subida sem indicação de indisponibilidade total, mas a recorrência em 15 pods na janela sugere reagendamentos/restarts frequentes que merecem atenção antes de se tornarem crash-loop sob maior carga ou menor tolerância do probe.
