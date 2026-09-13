---
fingerprint: k8s-eks-medprev-online-prd-FailedAttachVolume-medprev-rest-api
source: kubernetes
reason: FailedAttachVolume
novelty: new
service: medprev-rest-api
environment: production
window:
  from: 1788808256645
  to: 1789153856645
observed:
  count: 5
  first_seen: 1788924034000
  last_seen: 1789087465000
severity: medium
state: new
cost:
  input_tokens: 531762
  output_tokens: 11517
  cache_read_input_tokens: 435206
  cache_creation_input_tokens: 96544
  duration_s: 118.375
  usd: 0.5930852
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20FailedAttachVolume&from_ts=1788808256645&to_ts=1789153856645&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20FailedAttachVolume&from_ts=1788808256645&to_ts=1789153856645&live=false

## Causa raiz

O serviço afetado é `medprev-rest-api` (especificamente a réplica única `medprev-rest-api-redis-master-0`, um Redis master em StatefulSet com volume EBS `pvc-d74d321a-fe98-452b-b702-372dc225ff60`, `ReadWriteOnce`) no cluster `eks-medprev-online-prd`. O padrão, confirmado consultando os próprios eventos do pod (não apenas o achado), é: o Karpenter decide consolidar/rotacionar o node onde o pod está rodando, nomeia o pod para um node novo, o kubelet mata o container no node antigo, mas o `attachdetach-controller` ainda não concluiu o *detach* do volume EBS do node antigo quando o novo node tenta o *attach* — gerando o erro `FailedAttachVolume` (Multi-Attach). Isso se autorresolve em segundos: no ciclo consultado, `FailedAttachVolume` às 00:20:34 09/09/2026 BRT (epoch 1788924034000 · 2026-09-09T03:20:34.000Z) foi seguido por `SuccessfulAttachVolume` às 00:20:53 09/09/2026 BRT (epoch 1788924053000 · 2026-09-09T03:20:53.000Z) (~19s), e um segundo ciclo no mesmo dia teve `FailedAttachVolume` às 00:29:19 09/09/2026 BRT (epoch 1788924559000 · 2026-09-09T03:29:19.000Z) e `SuccessfulAttachVolume` às 00:29:27 09/09/2026 BRT (epoch 1788924567000 · 2026-09-09T03:29:27.000Z) (~8s).

Isto é **sinal, não ruído**: consultei os logs de aplicação (`analyze_datadog_logs`, filtro `service:medprev-rest-api`, padrão `Redis is not ready%`) e obtive **1356** ocorrências do warning "Redis is not ready (status: reconnecting)" na janela de 07/09/2026 16:10:56 BRT (epoch 1788808256645 · 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z)) a 11/09/2026 16:10:56 BRT (epoch 1789153856645 · 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z)) — a mesma janela do achado. Além disso, agregando os spans do serviço (`aggregate_spans`, `service:medprev-rest-api`, agrupado por `@http.status_code`) na janela de 12 minutos em torno do primeiro ciclo (00:19:00 09/09/2026 BRT (epoch 1788923940000 · 2026-09-09T03:19:00.000Z)–03:31:00Z), houve **5 respostas HTTP 500** em 1175 requisições totais nessa janela — impacto real, embora pequeno e transitório, e não um evento meramente cosmético no Error Tracking.

## Linha do tempo

Consultei a `query` de `evidence_links` (Events Explorer) e obtive as 5 ocorrências dentro da janela de coleta; para a primeira, ampliei a janela (±10–15 min) para reconstruir a causa:

1. 00:20:31 09/09/2026 BRT (epoch 1788924031000 · 2026-09-09T03:20:31.000Z) — Karpenter emite `Nominated`: pod deve ser agendado no `nodeclaim/default-jrlxb` (`node/ip-10-0-3-55`), sinalizando início da consolidação do node anterior (`ip-10-0-3-235`).
2. 00:20:33 09/09/2026 BRT (epoch 1788924033000 · 2026-09-09T03:20:33.000Z) — kubelet emite `Killing`: container `redis` parado no node antigo (`ip-10-0-3-235`).
3. 00:20:34 09/09/2026 BRT (epoch 1788924034000 · 2026-09-09T03:20:34.000Z) — `attachdetach-controller` emite `FailedAttachVolume` (1ª ocorrência do achado): Multi-Attach do volume `pvc-d74d321a-fe98-452b-b702-372dc225ff60`, pois ainda anexado ao node antigo.
4. 00:20:34 09/09/2026 BRT (epoch 1788924034000 · 2026-09-09T03:20:34.000Z) — scheduler confirma `Scheduled` no novo node `ip-10-0-3-55`.
5. 00:20:53 09/09/2026 BRT (epoch 1788924053000 · 2026-09-09T03:20:53.000Z) — `SuccessfulAttachVolume`: volume finalmente anexado ao novo node (~19s de atraso).
6. 00:21:04 09/09/2026 BRT (epoch 1788924064000 · 2026-09-09T03:21:04.000Z) — container recriado e iniciado no novo node.
7. 00:29:17 09/09/2026 BRT (epoch 1788924557000 · 2026-09-09T03:29:17.000Z) — kubelet emite novo `Killing` (segundo reagendamento, 9 min depois, node `ip-10-0-3-55` → outro node).
8. 00:29:19 09/09/2026 BRT (epoch 1788924559000 · 2026-09-09T03:29:19.000Z) — `FailedAttachVolume` (2ª ocorrência do achado), mesmo padrão Multi-Attach.
9. 00:29:27 09/09/2026 BRT (epoch 1788924567000 · 2026-09-09T03:29:27.000Z) — `SuccessfulAttachVolume` (~8s de atraso), `Scheduled` em `ip-10-0-1-42`.
10. 00:29:46 09/09/2026 BRT (epoch 1788924586000 · 2026-09-09T03:29:46.000Z) — container recriado e iniciado.
11. 07:01:43 09/09/2026 BRT (epoch 1788948103000 · 2026-09-09T10:01:43.000Z) — `FailedAttachVolume` (3ª ocorrência do achado, node `ip-10-0-3-247`) — não consultei o ciclo completo de recuperação deste; a janela de retorno (`SuccessfulAttachVolume`) para esta e as duas ocorrências seguintes não foi verificada, então não afirmo o tempo de resolução.
12. 01:55:15 10/09/2026 BRT (epoch 1789016115000 · 2026-09-10T04:55:15.000Z) — `FailedAttachVolume` (4ª ocorrência do achado, node `ip-10-0-0-54`) — recuperação não verificada.
13. 21:23:28 10/09/2026 BRT (epoch 1789086208000 · 2026-09-11T00:23:28.000Z) — `FailedAttachVolume` (5ª ocorrência do achado, node `ip-10-0-1-50`) — recuperação não verificada.
14. 21:44:25 10/09/2026 BRT (epoch 1789087465000 · 2026-09-11T00:44:25.000Z) — `FailedAttachVolume` — esta é a `last_seen` do achado (21:44:25 10/09/2026 BRT (epoch 1789087465000 · 2026-09-11T00:44:25.000Z)), node `ip-10-0-0-113` — recuperação não verificada.

`first_seen` do histórico completo do achado é 00:20:34 09/09/2026 BRT (epoch 1788924034000 · 2026-09-09T03:20:34.000Z), coincidente com a primeira ocorrência listada acima (a mesma janela cobre o histórico completo neste caso).

## Evidência

- 5 ocorrências de `FailedAttachVolume` dentro de 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) a 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z), todas no mesmo volume/pod: [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20FailedAttachVolume&from_ts=1788808256645&to_ts=1789153856645&live=false).
- Sequência causal completa (Nominated → Killing → FailedAttachVolume → Scheduled → SuccessfulAttachVolume → container recriado) para os dois primeiros ciclos: consulta `source:kubernetes kube_namespace:medprev-rest-api pod_name:medprev-rest-api-redis-master-0`, janela 00:00:00 09/09/2026 BRT (epoch 1788922800000 · 2026-09-09T03:00:00.000Z)–03:40:00Z, retornou 10 eventos.
- Consolidação/rotação de nodes pelo Karpenter no mesmo intervalo (`Nominated`, `Unconsolidatable`, `DisruptionBlocked`): consulta `source:kubernetes karpenter_nodepool:default reporting_controller:karpenter`, janela 00:00:00 09/09/2026 BRT (epoch 1788922800000 · 2026-09-09T03:00:00.000Z)–03:30:00Z, retornou 159 eventos (159 no total do namespace/cluster, não filtrados só ao pod Redis).
- Impacto de aplicação — reconexões de Redis: `analyze_datadog_logs`, `filter: service:medprev-rest-api`, `sql_query: SELECT count(*) FROM logs WHERE message LIKE 'Redis is not ready%'`, mesma janela do achado → **1356** ocorrências.
- Impacto de aplicação — erros HTTP: `aggregate_spans`, `query: service:medprev-rest-api`, `group_by: @http.status_code`, janela 00:19:00 09/09/2026 BRT (epoch 1788923940000 · 2026-09-09T03:19:00.000Z)–03:31:00Z → **500: 5**, 200: 832, 304: 196, 404: 86, 201: 45, 401: 9, 204: 2 (total 1175).
- Tentativa de classificar reasons agregados via `aggregate_events` (`group_by: reason`) retornou 0 buckets — o campo `reason` não é agregável diretamente nesta fonte; não repeti a mesma pergunta de outras formas.

## Ação recomendada

Migrar o Redis master para um volume/estratégia tolerante a rotação de nodes (ex.: EBS CSI com `WaitForFirstConsumer` + `terminationGracePeriodSeconds` maior, ou anotação Karpenter `do-not-disrupt` no pod StatefulSet do Redis, ou mover para um addon gerenciado como ElastiCache) para eliminar a janela de Multi-Attach durante consolidação; não há mudança de código de aplicação necessária, é infraestrutura.

## Corpo da issue

### Descrição do incidente
O pod `medprev-rest-api-redis-master-0` (Redis master, réplica única, volume EBS `pvc-d74d321a-fe98-452b-b702-372dc225ff60`, `ReadWriteOnce`) no cluster `eks-medprev-online-prd` sofre erros `FailedAttachVolume` (Multi-Attach) sempre que o Karpenter reagenda o pod para outro node durante consolidação. Isso já ocorreu 5 vezes na janela de 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) a 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z). Impacto observável: 1356 warnings de "Redis is not ready (reconnecting)" no serviço `medprev-rest-api` na mesma janela, e 5 respostas HTTP 500 em uma janela de 12 minutos ao redor do primeiro ciclo (00:19:00 09/09/2026 BRT (epoch 1788923940000 · 2026-09-09T03:19:00.000Z)–03:31:00Z).

### Causa raiz
Sinal real, não ruído: 5 respostas 500 confirmadas via spans em uma única janela de 12 minutos, mais 1356 reconexões de Redis logadas na janela do achado. Causa confirmada por evidência primária: o Karpenter consolida/rotaciona o node do pod (`Nominated` → kubelet `Killing`), mas o `attachdetach-controller` ainda não concluiu o detach do EBS quando o novo node tenta o attach, gerando o Multi-Attach. O erro se autorresolve em 8–19s (attach bem-sucedido logo em seguida), mas cada ciclo derruba e reconecta o Redis, gerando os warnings e os 5xx observados.

### Linha do tempo
1. 00:20:31 09/09/2026 BRT (epoch 1788924031000 · 2026-09-09T03:20:31.000Z) Karpenter `Nominated` — pod deve mover para `nodeclaim/default-jrlxb` (`ip-10-0-3-55`).
2. 00:20:33 09/09/2026 BRT (epoch 1788924033000 · 2026-09-09T03:20:33.000Z) kubelet `Killing` — container `redis` parado no node antigo.
3. 00:20:34 09/09/2026 BRT (epoch 1788924034000 · 2026-09-09T03:20:34.000Z) `FailedAttachVolume` — Multi-Attach do volume `pvc-d74d321a-fe98-452b-b702-372dc225ff60`.
4. 00:20:53 09/09/2026 BRT (epoch 1788924053000 · 2026-09-09T03:20:53.000Z) `SuccessfulAttachVolume` — volume anexado ao novo node (~19s depois).
5. 00:21:04 09/09/2026 BRT (epoch 1788924064000 · 2026-09-09T03:21:04.000Z) Container recriado e iniciado no novo node.
6. 00:29:17 09/09/2026 BRT (epoch 1788924557000 · 2026-09-09T03:29:17.000Z) Segundo ciclo: kubelet `Killing` novamente, 9 minutos depois.
7. 00:29:19 09/09/2026 BRT (epoch 1788924559000 · 2026-09-09T03:29:19.000Z) `FailedAttachVolume` novamente.
8. 00:29:27 09/09/2026 BRT (epoch 1788924567000 · 2026-09-09T03:29:27.000Z) `SuccessfulAttachVolume` (~8s depois).
9. 07:01:43 09/09/2026 BRT (epoch 1788948103000 · 2026-09-09T10:01:43.000Z), 01:55:15 10/09/2026 BRT (epoch 1789016115000 · 2026-09-10T04:55:15.000Z), 21:23:28 10/09/2026 BRT (epoch 1789086208000 · 2026-09-11T00:23:28.000Z), 21:44:25 10/09/2026 BRT (epoch 1789087465000 · 2026-09-11T00:44:25.000Z) — demais ocorrências de `FailedAttachVolume` do achado; recuperação (`SuccessfulAttachVolume`) não verificada para estas quatro.

### Evidências
- [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-rest-api%20FailedAttachVolume&from_ts=1788808256645&to_ts=1789153856645&live=false)
- Consulta: `source:kubernetes kube_namespace:medprev-rest-api pod_name:medprev-rest-api-redis-master-0`, janela 00:00:00 09/09/2026 BRT (epoch 1788922800000 · 2026-09-09T03:00:00.000Z)–03:40:00Z → 10 eventos (sequência causal completa).
- Consulta: `source:kubernetes karpenter_nodepool:default reporting_controller:karpenter`, janela 00:00:00 09/09/2026 BRT (epoch 1788922800000 · 2026-09-09T03:00:00.000Z)–03:30:00Z → 159 eventos (atividade de consolidação do Karpenter).
- Consulta: `analyze_datadog_logs`, `service:medprev-rest-api`, `message LIKE 'Redis is not ready%'`, janela do achado → 1356 logs.
- Consulta: `aggregate_spans`, `service:medprev-rest-api`, agrupado por `@http.status_code`, janela 00:19:00 09/09/2026 BRT (epoch 1788923940000 · 2026-09-09T03:19:00.000Z)–03:31:00Z → 500: 5 (de 1175 total).

### Ação recomendada
Repositório: `Medprev/medprev-rest-api` (a mudança é de manifesto/Helm chart do Redis, não de código de aplicação). Ação: adicionar a anotação `karpenter.sh/do-not-disrupt: "true"` (ou equivalente PodDisruptionBudget que bloqueie a consolidação) ao pod/StatefulSet `medprev-rest-api-redis-master-0`, ou avaliar migração para um serviço gerenciado (ElastiCache) que não dependa de EBS `ReadWriteOnce` single-attach. Validação: após o deploy, confirmar por 7 dias que a query de eventos acima (`FailedAttachVolume` neste namespace) retorna 0 ocorrências e que o count de logs `Redis is not ready` cai a zero nas janelas sem deploy/restart manual.

### Volume
5 ocorrências na janela do achado (16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) a 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z)); consulta direta ao Datadog na mesma janela e query confirmou o mesmo total de 5.

### Severidade e criticidade
`severity` do achado: `medium`. Avaliação (inferência): criticidade real é maior que `medium` para o negócio, pois o Redis master é ponto único (réplica única) usado por `medprev-rest-api`, e cada ciclo de reschedule já produziu 500s reais para usuários, ainda que em volume baixo (5 em 12 min); a recorrência (5 vezes em 4 dias) sugere que o problema tende a se repetir a cada consolidação do Karpenter até ser corrigido.
