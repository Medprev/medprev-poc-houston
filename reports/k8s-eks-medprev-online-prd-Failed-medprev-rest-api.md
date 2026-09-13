---
fingerprint: k8s-eks-medprev-online-prd-Failed-medprev-rest-api
source: kubernetes
reason: Failed
novelty: new
service: medprev-rest-api
environment: production
window:
  from: 1788808256645
  to: 1789153856645
observed:
  count: 2
  first_seen: 1789111207000
  last_seen: 1789111207000
severity: medium
state: new
cost:
  input_tokens: 443327
  output_tokens: 9287
  cache_read_input_tokens: 345415
  cache_creation_input_tokens: 97902
  duration_s: 105.819
  usd: 0.558196
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20Failed&from_ts=1788808256645&to_ts=1789153856645&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20Failed&from_ts=1788808256645&to_ts=1789153856645&live=false

## Causa raiz

O achado é do namespace Kubernetes `medprev-rest-api` (cluster `eks-medprev-online-prd`), reason `Failed`. Consultando o evento específico do pod `medprev-rest-api-pp-5bb99996f6-czl5v` citado em `raw.sample_workload`, encontrei a mensagem exata: **"Failed: Error: failed to sync secret cache: timed out waiting for the condition"**, emitida pelo kubelet em `04:20:07 11/09/2026 BRT (epoch 1789111207000 · 2026-09-11T07:20:07.000Z)` — timeout do kubelet ao sincronizar o cache de secrets projetados no momento da criação do pod, não um erro da aplicação.

Classifico como **ruído operacional, não bug de código**: o mesmo pod teve o container criado e iniciado com sucesso 1 segundo depois (04:20:08 11/09/2026 BRT (epoch 1789111208000 · 2026-09-11T07:20:08.000Z)), e os logs de aplicação do próprio pod ~43s depois (04:20:50 11/09/2026 BRT (epoch 1789111250000 · 2026-09-11T07:20:50.000Z)–04:20:51 11/09/2026 BRT (epoch 1789111251000 · 2026-09-11T07:20:51.000Z)) mostram apenas avisos benignos de inicialização do NestJS ("taking Nms to serialize" — warning conhecido do framework, não erro), confirmando boot normal. Não há log de erro/crash da aplicação nesse pod na janela consultada (0 logs `status:error`, 7 logs `status:warn`, todos de serialização de módulo NestJS). Uma consulta a `aggregate_spans` para `service:medprev-rest-api` na mesma janela (±1h ao redor do evento) devolveu **0 spans** — não há instrumentação APM (ou o nome de serviço no APM diverge) que permita medir `@error.handling`/`@http.status_code` para esse serviço; não é possível, portanto, classificar sinal/ruído pela via de spans — a classificação acima se apoia na sequência de eventos do Kubernetes e nos logs de aplicação, não em spans.

Não consegui localizar a segunda ocorrência que `observed_count: 2` indica: a busca direta por eventos desse pod específico na janela ±1h do `first_seen` retornou apenas 1 evento `Failed` (mais Scheduled/Pulling antes e Created/Pulled/Started depois). A causa raiz do evento em si (timeout do kubelet ao sincronizar secrets) está confirmada por evidência primária; a origem da segunda ocorrência contada por `observed_count` não foi determinada com as consultas feitas.

## Linha do tempo

- 04:18:54 11/09/2026 BRT (epoch 1789111134000 · 2026-09-11T07:18:54.000Z) — Pod agendado no node `ip-10-0-3-54.sa-east-1.compute.internal` e início do pull da imagem `medprev-rest-api:9ff86a72` (evento Scheduled+Pulling, mesmo `pod_name`).
- 04:20:07 11/09/2026 BRT (epoch 1789111207000 · 2026-09-11T07:20:07.000Z) — Evento **Failed**: "Error: failed to sync secret cache: timed out waiting for the condition" — este é o evento que gerou o achado (`raw.timestamp`, `first_seen`, `last_seen` coincidem com este timestamp).
- 04:20:08 11/09/2026 BRT (epoch 1789111208000 · 2026-09-11T07:20:08.000Z) — Container criado, imagem já presente, pulled (1m11.842s) e container iniciado com sucesso — recuperação em 1 segundo.
- 04:20:50 11/09/2026 BRT (epoch 1789111250000 · 2026-09-11T07:20:50.000Z)–04:20:51 11/09/2026 BRT (epoch 1789111251000 · 2026-09-11T07:20:51.000Z) — Logs de aplicação (`status:warn`) mostram a inicialização normal dos módulos NestJS (TypeOrmModule, PgBossModule, InternalCoreModule), confirmando boot saudável do processo.

Não encontrei uma segunda ocorrência do reason `Failed` para este ou outro pod do namespace na janela consultada (±1h ao redor de `first_seen`); os campos garantidos pelo achado permanecem `observed_count: 2` para a janela 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) até 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z).

## Evidência

- Evento Kubernetes "Failed: Error: failed to sync secret cache: timed out waiting for the condition" para o pod `medprev-rest-api-pp-5bb99996f6-czl5v` — [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20Failed&from_ts=1788808256645&to_ts=1789153856645&live=false); confirmado também por consulta direta `source:kubernetes kube_namespace:medprev-rest-api pod_name:medprev-rest-api-pp-5bb99996f6-czl5v` (from `1789109407000` to `1789113007000`), que devolveu 3 eventos.
- Recuperação em 1s: evento "Created/Pulled/Started" para o mesmo pod, mesma consulta acima.
- Logs de aplicação do mesmo pod na janela `1789109407000`–`1789113007000` filtrados por `status:(warn OR error)`: 7 logs, todos `warn` de serialização NestJS, 0 logs `error`.
- Ausência de spans instrumentados: `aggregate_spans` com `query: "service:medprev-rest-api"` na janela `1789107607000`–`1789114807000` devolveu `total_buckets: 0` — sem dados de span/trace para correlacionar `@error.handling`/`@http.status_code` nesse intervalo.
- Consulta ampla `source:kubernetes env:production status:warn kube_namespace:medprev-rest-api Failed` na janela completa do achado devolveu 286 eventos totais (texto livre "Failed", que também casa com mensagens "probe failed" de outros pods/deployments do mesmo namespace) — número não comparável a `observed_count: 2`, que é filtrado por Reason exato, não por texto livre.

## Ação recomendada

Não é necessária ação de código: trate como ruído de infraestrutura (timeout transitório do kubelet ao montar secrets, autorrecuperado). Se o padrão se repetir com frequência crescente, investigar latência do secrets provider (CSI driver / Kubernetes Secrets Store) no node `ip-10-0-3-54`.

## Corpo da issue

### Descrição do incidente
No namespace `medprev-rest-api` do cluster `eks-medprev-online-prd`, o pod `medprev-rest-api-pp-5bb99996f6-czl5v` recebeu um evento Kubernetes `Failed` do kubelet ("Error: failed to sync secret cache: timed out waiting for the condition") durante sua inicialização. Nenhum impacto observável foi identificado: o container foi criado e iniciado com sucesso 1 segundo depois, e a aplicação completou o boot normalmente.

### Causa raiz
**Ruído operacional**, não bug de aplicação — 0 logs `error` e 0 spans com falha correlacionados ao pod nessa janela (consulta a `aggregate_spans` devolveu 0 buckets, sem instrumentação/dados de APM disponíveis para esse serviço no intervalo). O evento é um timeout pontual do kubelet ao sincronizar o cache de secrets no momento do agendamento do pod, autorrecuperado em 1 segundo, seguido de boot saudável da aplicação (confirmado por logs).

### Linha do tempo
1. 04:18:54 11/09/2026 BRT (epoch 1789111134000 · 2026-09-11T07:18:54.000Z) — Pod agendado + início do pull de imagem `medprev-rest-api:9ff86a72`.
2. 04:20:07 11/09/2026 BRT (epoch 1789111207000 · 2026-09-11T07:20:07.000Z) — Evento `Failed`: timeout do kubelet sincronizando secrets.
3. 04:20:08 11/09/2026 BRT (epoch 1789111208000 · 2026-09-11T07:20:08.000Z) — Container criado/pulled/iniciado com sucesso.
4. 04:20:50 11/09/2026 BRT (epoch 1789111250000 · 2026-09-11T07:20:50.000Z)–04:20:51 11/09/2026 BRT (epoch 1789111251000 · 2026-09-11T07:20:51.000Z) — Logs de aplicação confirmam boot normal (warnings benignos de serialização NestJS).

### Evidências
- [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20Failed&from_ts=1788808256645&to_ts=1789153856645&live=false)
- Consulta direta: `source:kubernetes kube_namespace:medprev-rest-api pod_name:medprev-rest-api-pp-5bb99996f6-czl5v` (from `1789109407000` to `1789113007000`) — 3 eventos, incluindo o `Failed` e a recuperação em 1s.
- Consulta de logs: `kube_namespace:medprev-rest-api pod_name:medprev-rest-api-pp-5bb99996f6-czl5v status:(warn OR error)` (from `1789109407000` to `1789113007000`) — 7 logs, todos `warn`, 0 `error`.
- Consulta de spans: `aggregate_spans` com `query: "service:medprev-rest-api"` (from `1789107607000` to `1789114807000`) — 0 buckets (sem dados de APM no período).

### Ação recomendada
`target_repo`: infra — sem repositório de código de aplicação diretamente responsável; ação operacional em `Medprev/medprev-cloud-iac` (configuração do CSI/Secrets Store provider e/ou kubelet do node pool `default` no cluster `eks-medprev-online-prd`), caso a recorrência aumente. Nenhuma mudança de código é necessária em `Medprev/medprev-rest-api` hoje. Validação: monitorar a frequência do reason `Failed` com essa mensagem específica ("failed to sync secret cache") no namespace; se ultrapassar eventos isolados (ex.: >1/dia) ou deixar de autorrecuperar em <5s, escalar para o time de plataforma investigar o secrets provider.

### Volume
`observed_count: 2` na janela 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) até 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z). Consulta direta ao evento específico do pod (janela mais estreita, ±1h ao redor de `first_seen`) encontrou apenas 1 ocorrência do reason `Failed`; a segunda ocorrência contada em `observed_count` não foi localizada com as consultas feitas.

### Severidade e criticidade
`severity: medium` do achado. Avaliação de criticidade (inferência): **baixa** — evento único, autorrecuperado em 1 segundo, sem log de erro de aplicação, sem indício de crash loop ou impacto a usuários na janela investigada.
