---
fingerprint: et-c7bd8cee-dcbd-11ef-929e-da7ad0900002
source: error_tracking
reason: PartnerNotFoundException
novelty: new
service: medprev-rest-api
environment: production
window:
  from: 1788814356569
  to: 1789159956569
observed:
  count: 50
  first_seen: 1737989291000
  last_seen: 1789118586774
severity: medium
state: new
cost:
  input_tokens: 476255
  output_tokens: 8346
  cache_read_input_tokens: 419745
  cache_creation_input_tokens: 56496
  duration_s: 110.136
  usd: 0.398003
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/error-tracking/issue/c7bd8cee-dcbd-11ef-929e-da7ad0900002
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/error-tracking/issue/c7bd8cee-dcbd-11ef-929e-da7ad0900002

## Causa raiz

O achado é **ruído** no Error Tracking, não um defeito. `PartnerNotFoundException` é lançada pelo serviço `medprev-rest-api` em `GetOnlinePartnerService.getOnlinePartner` (`get-online-partner.service.js:37`) quando um `partnerId` não é encontrado — e o trace da última ocorrência mostra que o chamador recebe `http.status_code: "404"` na própria rota `GET /online/partner/:partnerId` (span raiz, `trace_id bce637a1a15d51f35b34428d3ad0cd81`), não um 5xx. Consultei o Error Tracking com `SELECT "error.handling", count(*) FROM errors GROUP BY "error.handling"` filtrado por `issue.id:c7bd8cee-dcbd-11ef-929e-da7ad0900002` na janela do achado: **50 de 50 ocorrências (100%) são `handled`** — nenhuma `unhandled`. Não há log de aplicação associado (`search_datadog_logs` com `service:medprev-rest-api @error.type:PartnerNotFoundException` na mesma janela devolveu 0 resultados), ou seja, o código não trata isso nem como evento de negócio logado — apenas deixa a exceção subir como span de erro do APM, que é o que o Error Tracking captura.

Agregando os spans da rota (`aggregate_spans`, `service:medprev-rest-api resource_name:"GET /online/partner/:partnerId"`, mesma janela): 2021 respostas 200, 451 respostas 304, 25 respostas 404 — uma taxa de ~1% de 404, volume estável e proporcional aos dias com mais tráfego. O achado tem `first_seen` em 27/01/2025 e segue ativo hoje, sem regressão (`regressed: false`), o que descarta início recente ou mudança de código como gatilho.

## Linha do tempo

- 17:52:36 07/09/2026 BRT (epoch 1788814356569 · 2026-09-07T20:52:36.569Z) — início da janela de coleta (`window_from`).
- 21:00:00 07/09/2026 BRT (epoch 1788825600000 · 2026-09-08T00:00:00.000Z) — 8 ocorrências neste dia (consulta `analyze_datadog_error_tracking_errors`, `SELECT DATE_TRUNC('day', timestamp)... GROUP BY`, filtro `issue.id:c7bd8cee-dcbd-11ef-929e-da7ad0900002`).
- 21:00:00 08/09/2026 BRT (epoch 1788912000000 · 2026-09-09T00:00:00.000Z) — 14 ocorrências.
- 21:00:00 09/09/2026 BRT (epoch 1788998400000 · 2026-09-10T00:00:00.000Z) — 14 ocorrências.
- 21:00:00 10/09/2026 BRT (epoch 1789084800000 · 2026-09-11T00:00:00.000Z) — 14 ocorrências (dia parcial, até o fim da janela).
- 06:23:06 11/09/2026 BRT (epoch 1789118586775 · 2026-09-11T09:23:06.775Z) — última ocorrência registrada no `last_error`, com `trace_id 6571950930584980865` (hex `bce637a1a15d51f35b34428d3ad0cd81`); o span raiz do trace mostra `http.route: /online/partner/:partnerId`, `http.status_code: "404"`, versão implantada `9ff86a72`.
- 17:52:36 11/09/2026 BRT (epoch 1789159956569 · 2026-09-11T20:52:36.569Z) — fim da janela de coleta (`window_to`).

Não consultei eventos anteriores a 07/09/2026 além da agregação diária acima; para o histórico completo do achado, os únicos pontos garantidos pelos campos do próprio achado são `first_seen` (11:48:11 27/01/2025 BRT · epoch 1737989291000 · 11:48:11 27/01/2025 BRT (epoch 1737989291000 · 2025-01-27T14:48:11.000Z)) e `last_seen` (06:23:06 11/09/2026 BRT · epoch 1789118586774 · 06:23:06 11/09/2026 BRT (epoch 1789118586774 · 2026-09-11T09:23:06.774Z)).

## Evidência

- Issue no Error Tracking, estado `FOR_REVIEW`, sem regressão: https://app.datadoghq.com/error-tracking/issue/c7bd8cee-dcbd-11ef-929e-da7ad0900002
- 50/50 ocorrências classificadas `error.handling: handled` na janela — consulta: `analyze_datadog_error_tracking_errors`, filtro `issue.id:c7bd8cee-dcbd-11ef-929e-da7ad0900002`, `SELECT "error.handling", count(*) FROM errors GROUP BY "error.handling"` → `handled: 50`.
- Distribuição diária (8/14/14/14) — mesma ferramenta, `SELECT DATE_TRUNC('day', timestamp), count(*) ... GROUP BY`.
- Nenhum log de aplicação para esse erro na janela — `search_datadog_logs`, query `service:medprev-rest-api @error.type:PartnerNotFoundException`, resultado: 0 registros.
- Trace da última ocorrência confirma resposta 404 ao chamador (span raiz): https://app.datadoghq.com/apm/trace/bce637a1a15d51f35b34428d3ad0cd81
- Distribuição de status HTTP da rota afetada — `aggregate_spans`, query `service:medprev-rest-api resource_name:"GET /online/partner/:partnerId"`, agrupado por `@http.status_code`: 200→2021, 304→451, 404→25 (total ~2497 requisições na janela; consulta separada da contagem do achado, note a divergência de escopo/amostragem entre Error Tracking e spans, marcada em ADR-0023-like fashion — spans do APM são amostrados probabilisticamente, `ingestion_reason:probabilistic`, `random_draw: 0.278`).
- Tentativa de agregar spans por `@error.type:PartnerNotFoundException` (`aggregate_spans`, mesma janela) devolveu 0 buckets — o atributo de erro não está indexado como facet de span nessa forma; não retentei variações, registro como resultado vazio.

## Ação recomendada

Não é uma ação de correção de bug — é reclassificação: mover `PartnerNotFoundException` para fora do Error Tracking (tratar como retorno de negócio, não exceção) no repositório `Medprev/medprev-rest-api`, arquivo `get-online-partner.service.ts` (fonte de `get-online-partner.service.js`), função `getOnlinePartner`.

## Corpo da issue

### Descrição do incidente
O serviço `medprev-rest-api` lança `PartnerNotFoundException` em `GetOnlinePartnerService.getOnlinePartner` sempre que um `partnerId` não é encontrado na rota `GET /online/partner/:partnerId`, e essa exceção é capturada pelo Datadog Error Tracking como se fosse um defeito. Não há impacto observável para o usuário: o endpoint responde corretamente com HTTP 404. O único efeito real é ruído operacional — a issue acumula ocorrências indefinidamente (achado aberto desde 27/01/2025) e consome atenção/triagem sem indicar uma falha real.

### Causa raiz
**Ruído, não bug** — 100% das 50 ocorrências na janela (`error.handling: handled`, consulta SQL contra `errors` filtrada por `issue.id:c7bd8cee-dcbd-11ef-929e-da7ad0900002`) são exceções tratadas pelo próprio código, e o trace confirma resposta 404 ao chamador. É um resultado de negócio (partner inexistente) modelado como exceção lançada, não uma falha de execução.

### Linha do tempo
- 21:00:00 07/09/2026 BRT (epoch 1788825600000 · 2026-09-08T00:00:00.000Z): 8 ocorrências.
- 21:00:00 08/09/2026 BRT (epoch 1788912000000 · 2026-09-09T00:00:00.000Z): 14 ocorrências.
- 21:00:00 09/09/2026 BRT (epoch 1788998400000 · 2026-09-10T00:00:00.000Z): 14 ocorrências.
- 21:00:00 10/09/2026 BRT (epoch 1789084800000 · 2026-09-11T00:00:00.000Z): 14 ocorrências (dia parcial).
- 06:23:06 11/09/2026 BRT (epoch 1789118586775 · 2026-09-11T09:23:06.775Z): última ocorrência, trace `bce637a1a15d51f35b34428d3ad0cd81`, versão `9ff86a72`, resposta 404 confirmada no span raiz.
- Sem mudança de versão associada a um salto de volume: `first_seen_version` (`20250124.9`) e `last_seen_version` (`9ff86a72`) são apenas o primeiro e o mais recente deploy observados, não indicam regressão (`regressed: false`).

### Evidências
- Issue: https://app.datadoghq.com/error-tracking/issue/c7bd8cee-dcbd-11ef-929e-da7ad0900002
- Trace da última ocorrência: https://app.datadoghq.com/apm/trace/bce637a1a15d51f35b34428d3ad0cd81
- Consulta `error.handling` (50/50 handled): `analyze_datadog_error_tracking_errors`, filtro `issue.id:c7bd8cee-dcbd-11ef-929e-da7ad0900002`, SQL `SELECT "error.handling", count(*) FROM errors GROUP BY "error.handling"`
- Consulta de status HTTP da rota (200:2021, 304:451, 404:25): `aggregate_spans`, query `service:medprev-rest-api resource_name:"GET /online/partner/:partnerId"`, group by `@http.status_code`
- Ausência de log de aplicação: `search_datadog_logs`, query `service:medprev-rest-api @error.type:PartnerNotFoundException` → 0 resultados

### Ação recomendada
No repositório `Medprev/medprev-rest-api`, em `src/modules/partner/service/online/get-online-partner.service.ts` (função `getOnlinePartner`), parar de lançar `PartnerNotFoundException` como exceção não capturada pelo instrumentador de erro — capturar/suprimir a marcação de erro no span (ou usar um filtro de exclusão de Error Tracking por `error.type:PartnerNotFoundException` no serviço) e, se ainda não existir, adicionar um log estruturado em nível `info` com o `partnerId` não encontrado para rastreabilidade de negócio. Validar checando que novas ocorrências de "partner not found" não geram mais entradas no Error Tracking, mas continuam retornando 404 corretamente na rota (`aggregate_spans` na mesma rota, esperando volume de 404 inalterado e zero novos itens em `search_datadog_error_tracking_issues` para esse `error.type`).

### Volume
50 ocorrências entre 17:52:36 07/09/2026 BRT (epoch 1788814356569 · 2026-09-07T20:52:36.569Z) e 17:52:36 11/09/2026 BRT (epoch 1789159956569 · 2026-09-11T20:52:36.569Z) (`observed_count`). Na mesma janela, os spans da rota afetada mostram 25 respostas 404 em 2497 requisições totais — divergência explicada por amostragem probabilística do APM (spans), diferente do mecanismo de captura do Error Tracking.

### Severidade e criticidade
`severity: medium` no achado — mas essa severidade não se aplica ao erro em si, já que é ruído classificado como exceção. O defeito real encontrado é a classificação incorreta (exceção de negócio poluindo o Error Tracking): **inferência minha**, criticidade **baixa** — não há impacto a usuário ou dado, apenas custo de triagem/observabilidade acumulado por mais de um ano e meio.
