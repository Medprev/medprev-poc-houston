---
fingerprint: k8s-eks-medprev-online-prd-Unhealthy-medprev-rest-api
source: kubernetes
reason: Unhealthy
novelty: new
service: medprev-rest-api
environment: production
window:
  from: 1788794372355
  to: 1789139972355
observed:
  count: 188
  first_seen: 1788796300000
  last_seen: 1789139652000
severity: medium
state: new
cost:
  input_tokens: 563259
  output_tokens: 10001
  cache_read_input_tokens: 458043
  cache_creation_input_tokens: 105204
  duration_s: 115.956
  usd: 0.6171086000000001
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20Unhealthy&from_ts=1788794372355&to_ts=1789139972355&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20Unhealthy&from_ts=1788794372355&to_ts=1789139972355&live=false

## Causa raiz

**Sinal, não ruído.** `medprev-rest-api` acumulou 188 eventos `Unhealthy` (falhas de liveness/readiness/startup probe no endpoint `/public/health-check`) na janela coletada, distribuídos por pelo menos 4 deployments diferentes (`gama`, `pp`, `adm`, `ag`) e múltiplos pods — não é um pico isolado nem um único pod com defeito de hardware. Correlacionando com logs de aplicação no mesmo intervalo: 75 ocorrências de `Redis [single] is down.` (causa raiz imediata: `connect ECONNREFUSED` para `medprev-rest-api-redis-master.medprev-rest-api.svc.cluster.local:6379`), mais 78 warnings de timeout do SDK AWS (`@smithy/node-http-handler ... requestTimeout`), 64 falhas de processamento de filas `pgBoss`, e 56 ocorrências de `Unhandled exception reached the global filter`. Reconstruí o trace completo (`trace_id:2625c07f179e93322624142f910b9d41`) de uma dessas quedas de Redis: é a sequência de boot da aplicação (`PartnerModule dependencies initialized`, `ShoppingModule dependencies initialized`, ...) tentando repetidamente `connect` ao Redis (spans `db.system:redis`, ~12 tentativas entre 21:45:04 10/09/2026 BRT (epoch 1789087504727 · 2026-09-11T00:45:04.727Z) e 21:45:20 10/09/2026 BRT (epoch 1789087520103 · 2026-09-11T00:45:20.103Z), cada uma com duração crescente) até finalmente conseguir (`Redis [single] is up.` em 21:45:20 10/09/2026 BRT (epoch 1789087520000 · 2026-09-11T00:45:20.000Z)). Isso indica que o pod fica preso em ciclo de reconexão ao Redis durante o start/restart, e enquanto isso o readiness/liveness probe expira (`context deadline exceeded`) — gerando o evento `Unhealthy` repetidamente, inclusive para pods que já estavam servindo tráfego (mensagens de "Liveness probe failed" em pods rodando, não só em `Startup probe failed`).

Não determinei a causa raiz da própria instabilidade do Redis (por que o serviço `medprev-rest-api-redis-master` fica inacessível intermitentemente) — isso está fora do escopo de spans/logs do lado do cliente `medprev-rest-api`; exigiria telemetria do próprio Redis/infra, que não está disponível pelas ferramentas consultadas nesta investigação.

## Linha do tempo

- 12:51:40 07/09/2026 BRT (epoch 1788796300000 · 2026-09-07T15:51:40.000Z) — primeira ocorrência do achado: `Unhealthy: Readiness probe failed` no pod `medprev-rest-api-gama-7d7f9cc7fc-9xsqw` (`http://10.0.5.112:3000/public/health-check`, context deadline exceeded). Confirma `first_seen` do achado.
- 14:21:37 07/09/2026 BRT (epoch 1788801697000 · 2026-09-07T17:21:37.000Z) — `Liveness probe failed` no pod `medprev-rest-api-pp-7d6c7f8d65-g7hdc` — pod já rodando, não em startup.
- 15:30:10 07/09/2026 BRT (epoch 1788805810000 · 2026-09-07T18:30:10.000Z) a 04:20:20 08/09/2026 BRT (epoch 1788852020000 · 2026-09-08T07:20:20.000Z) — sequência contínua de `Unhealthy` (liveness e readiness) alternando entre os pods `gama-9xsqw`, `gama-zh2lt`, `ag-7h298`, `adm-vvmjm`, `pp-dx56v`, sempre no mesmo padrão: `context deadline exceeded` ao chamar `/public/health-check`.
- 01:06:15 08/09/2026 BRT (epoch 1788840375000 · 2026-09-08T04:06:15.000Z) — três `Startup probe failed: connect: connection refused` simultâneos em pods novos (`pp-dx56v`, `ag-7h298`, `adm-vvmjm`), indicando que a aplicação ainda não havia aberto a porta 3000 (processo ainda inicializando dependências).
- 21:44:58 10/09/2026 BRT (epoch 1789087498000 · 2026-09-11T00:44:58.000Z) a 21:45:20 10/09/2026 BRT (epoch 1789087520000 · 2026-09-11T00:45:20.000Z) — trace completo de um boot: módulos NestJS inicializando em sequência, ~12 tentativas de `connect` ao Redis com backoff crescente, log `Redis [single] is down. | error.message: connect ECONNREFUSED 172.20.146.54:6379` seguido por `Redis [single] is up.` ao final — evidência direta do mecanismo que atrasa o boot e expira o probe.
- 12:02:16 11/09/2026 BRT (epoch 1789138936000 · 2026-09-11T15:02:16.000Z) — log de erro mais recente correlacionado (`Query runner already released. Cannot run queries anymore.`), indicando estresse também no pool de conexões de banco na mesma janela.
- `last_seen`: 12:14:12 11/09/2026 BRT (epoch 1789139652000 · 2026-09-11T15:14:12.000Z) — última ocorrência registrada pelo achado, consistente com o volume ainda ativo no fim da janela.

A busca de eventos retornou exatamente 188 registros na janela (paginação confirmou `count: 188`), batendo com `observed_count`.

## Evidência

- 188 eventos `Unhealthy` (readiness/liveness/startup) para `medprev-rest-api` entre `window_from` e `window_to` — [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20Unhealthy&from_ts=1788794372355&to_ts=1789139972355&live=false).
- 471 logs `status:error` para `service:medprev-rest-api` na mesma janela — consulta `search_datadog_logs` com `service:medprev-rest-api env:production status:error`, `from=1788794372355 to=1789139972355` (contagem retornada: 471).
- Distribuição dos erros mais frequentes na janela (`analyze_datadog_logs`, mesmo filtro): `Redis [single] is down.` = 75; AWS SDK `requestTimeout` warn = 78; `pgBoss_queue_ClinicScheduledPartnerProtocolRedemptionService handling failed` = 64; `Unhandled exception reached the global filter` = 56; `Pagarme antifraud decision backfill tick failed` = 26; `Failed to capture the pix payment from the webhook` = 13; demais filas pgBoss = 3 a 12 cada.
- Trace completo `trace_id:2625c07f179e93322624142f910b9d41` (boot da aplicação com múltiplas tentativas de `connect` ao Redis) — consulta `search_datadog_spans` com `query: "trace_id:2625c07f179e93322624142f910b9d41"`, 47 spans retornados; URL: https://app.datadoghq.com/apm/traces?end=1789139972355&historicalData=true&paused=true&query=trace_id%3A2625c07f179e93322624142f910b9d41&start=1788794372355.
- `aggregate_spans` de `resource_name` para `service:medprev-rest-api` na janela não retornou nenhum span com `resource_name:*health*` (0 buckets) — o endpoint de health-check não é instrumentado como span de aplicação, então a confirmação da causa veio pelos logs/eventos de kubelet, não pelo APM do endpoint em si.
- Volume de spans dominante no serviço na janela: `pg-pool.connect` (2.063.184), `pg.query:SELECT` (1.875.199), `pg.connect` (72.062) — consistente com pressão alta sobre o pool de conexões de banco, correlacionada ao erro `Query runner already released` observado em 12:02:16 11/09/2026 BRT (epoch 1789138936000 · 2026-09-11T15:02:16.000Z).

## Ação recomendada
Investigar a causa da indisponibilidade intermitente do `medprev-rest-api-redis-master` (rede/DNS interno, restart do Redis, ou saturação do serviço) e, no código de `Medprev/medprev-rest-api`, tornar o boot resiliente a essa indisponibilidade (o probe de readiness não deveria depender de uma conexão Redis totalmente estabelecida com retries síncronos bloqueando o start).

## Corpo da issue

### Descrição do incidente
`medprev-rest-api` (namespace `medprev-rest-api`, cluster `eks-medprev-online-prd`) apresentou 188 eventos `Unhealthy` de probes Kubernetes (liveness, readiness e startup) na janela `window_from` 12:19:32 07/09/2026 BRT (epoch 1788794372355 · 2026-09-07T15:19:32.355Z) a `window_to` 12:19:32 11/09/2026 BRT (epoch 1789139972355 · 2026-09-11T15:19:32.355Z), espalhados por múltiplos deployments (`gama`, `pp`, `adm`, `ag`) e pods. O impacto observável é reinício/instabilidade recorrente de pods do serviço, com potencial de indisponibilidade momentânea de rotas que dependem de Redis ou do pool de banco durante o ciclo de restart.

### Causa raiz
Sinal real, não ruído — 188 ocorrências recorrentes em múltiplos pods, não uma anomalia isolada. Causa raiz imediata confirmada via trace (`trace_id:2625c07f179e93322624142f910b9d41`): durante o boot, a aplicação tenta reconectar ao Redis (`medprev-rest-api-redis-master.medprev-rest-api.svc.cluster.local:6379`) repetidamente após `ECONNREFUSED`, atrasando a inicialização até o readiness/liveness probe expirar (`context deadline exceeded`). Causa raiz de fundo — por que o Redis fica inacessível intermitentemente — **não determinada**: exigiria telemetria do lado do Redis/infra, fora do escopo dos logs/spans do cliente `medprev-rest-api` consultados.

### Linha do tempo
- 12:51:40 07/09/2026 BRT (epoch 1788796300000 · 2026-09-07T15:51:40.000Z): primeira ocorrência (`Unhealthy: Readiness probe failed`, pod `gama-9xsqw`).
- 14:21:37 07/09/2026 BRT (epoch 1788801697000 · 2026-09-07T17:21:37.000Z): `Liveness probe failed` em pod já em execução (`pp-g7hdc`), não durante boot.
- 15:30:10 07/09/2026 BRT (epoch 1788805810000 · 2026-09-07T18:30:10.000Z)–04:20:20 08/09/2026 BRT (epoch 1788852020000 · 2026-09-08T07:20:20.000Z): sequência contínua de eventos `Unhealthy` alternando entre pods.
- 01:06:15 08/09/2026 BRT (epoch 1788840375000 · 2026-09-08T04:06:15.000Z): `Startup probe failed: connection refused` simultâneo em 3 pods novos.
- 21:44:58 10/09/2026 BRT (epoch 1789087498000 · 2026-09-11T00:44:58.000Z)–21:45:20 10/09/2026 BRT (epoch 1789087520000 · 2026-09-11T00:45:20.000Z): trace de boot mostrando ~12 tentativas de `connect` ao Redis até sucesso (`Redis [single] is down.` → `Redis [single] is up.`).
- 12:02:16 11/09/2026 BRT (epoch 1789138936000 · 2026-09-11T15:02:16.000Z): log de erro correlacionado no pool de banco (`Query runner already released`).
- last_seen do achado: 12:14:12 11/09/2026 BRT (epoch 1789139652000 · 2026-09-11T15:14:12.000Z).

### Evidências
- Events Explorer (188 eventos na janela): https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20Unhealthy&from_ts=1788794372355&to_ts=1789139972355&live=false
- Trace completo do boot com reconexões ao Redis: https://app.datadoghq.com/apm/traces?end=1789139972355&historicalData=true&paused=true&query=trace_id%3A2625c07f179e93322624142f910b9d41&start=1788794372355
- Logs de erro do serviço na janela (471 no total, `service:medprev-rest-api env:production status:error`): https://app.datadoghq.com/logs?from_ts=1788794372355&live=false&query=service%3Amedprev-rest-api+env%3Aproduction+status%3Aerror&stream_sort=desc&to_ts=1789139972355
- Logs "Redis is down" (75 ocorrências): https://app.datadoghq.com/logs?from_ts=1788794372355&live=false&query=service%3Amedprev-rest-api+env%3Aproduction+%22Redis+%5Bsingle%5D+is+down%22&stream_sort=desc&to_ts=1789139972355

### Ação recomendada
Repositório: `Medprev/medprev-rest-api`. (1) Investigar operacionalmente a estabilidade do serviço `medprev-rest-api-redis-master` no namespace `medprev-rest-api` (ver logs/eventos do próprio Redis, não cobertos por esta investigação). (2) No código do bootstrap da aplicação (módulo que inicializa a conexão `ioredis`, chamado antes do boot completar todos os `*Module dependencies initialized`), desacoplar o readiness probe da conexão Redis bloqueante — o handler de `/public/health-check` não deve aguardar sincronamente o Redis estar pronto com retries que estouram o timeout do probe; considerar readiness independente por dependência (liveness não deve falhar por Redis fora do ar se o processo HTTP está saudável). Validar aumentando `initialDelaySeconds`/`timeoutSeconds` do probe apenas como paliativo, e confirmando a correção observando queda de `Unhealthy` events (mesma query acima) e de `Redis [single] is down.` para próximo de zero nas próximas 96h após o deploy.

### Volume
188 ocorrências entre window_from (12:19:32 07/09/2026 BRT · 12:19:32 07/09/2026 BRT (epoch 1788794372355 · 2026-09-07T15:19:32.355Z)) e window_to (12:19:32 11/09/2026 BRT · 12:19:32 11/09/2026 BRT (epoch 1789139972355 · 2026-09-11T15:19:32.355Z)) — confirmado por consulta direta ao Events Explorer na mesma janela (188 eventos, mesma contagem, mesmo filtro).

### Severidade e criticidade
`severity` do achado: `medium`. Avaliação de criticidade (inferência): moderada-alta — o padrão de reconexões falhas ao Redis durante boot/restart, combinado com 56 `Unhandled exception` e 64 falhas de processamento de filas assíncronas (`pgBoss`) na mesma janela, sugere risco de perda ou atraso de processamento de eventos de negócio (ex.: `PagarmeSqsConsumer`, reembolsos, backfills) durante os ciclos de instabilidade — não confirmado se houve perda de dados, apenas correlação temporal de logs.
