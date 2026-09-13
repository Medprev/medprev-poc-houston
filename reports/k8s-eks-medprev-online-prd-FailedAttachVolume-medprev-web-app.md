---
fingerprint: k8s-eks-medprev-online-prd-FailedAttachVolume-medprev-web-app
source: kubernetes
reason: FailedAttachVolume
novelty: new
service: medprev-web-app
environment: production
window:
  from: 1788808256645
  to: 1789153856645
observed:
  count: 1
  first_seen: 1788924843000
  last_seen: 1788924843000
severity: medium
state: new
cost:
  input_tokens: 341739
  output_tokens: 9807
  cache_read_input_tokens: 251241
  cache_creation_input_tokens: 90490
  duration_s: 103.227
  usd: 0.5149682
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-web-app%20FailedAttachVolume&from_ts=1788808256645&to_ts=1789153856645&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-web-app%20FailedAttachVolume&from_ts=1788808256645&to_ts=1789153856645&live=false

## Causa raiz

O evento é da namespace `medprev-web-app` no cluster `eks-medprev-online-prd`, workload `medprev-web-app-redis-master-0` (um Redis single-replica, StatefulSet, com volume EBS `pvc-ac28668e-ab07-4ae2-8160-eec6e73f899d`). É **ruído operacional autorresolvido**, não uma falha persistente: a linha do tempo consultada mostra o Karpenter substituindo o nó onde o pod rodava (`ip-10-0-11-5`) por um novo nó (`ip-10-0-8-39`); o attach/detach controller tentou anexar o volume EBS no novo nó antes do nó antigo liberar (Multi-Attach error, `status:warn`, não `error`), e o próprio Kubernetes corrigiu isso em 13 segundos — `SuccessfulAttachVolume` às 00:34:16 09/09/2026 BRT (epoch 1788924856000 · 2026-09-09T03:34:16.000Z) e container rodando às 00:34:29 09/09/2026 BRT (epoch 1788924869000 · 2026-09-09T03:34:29.000Z). Não há classificação `@error.handling` aplicável aqui porque este não é um achado de Error Tracking com spans de aplicação — a busca de spans em `service:medprev-web-app-redis-master` no período retornou **0 spans** (Redis não é instrumentado com APM, esperado para um datastore), e a busca ampliada por `service:medprev-web-app*` no mesmo período só encontrou spans do `medprev-web-app-backend-graphql` (3.323, 100% `handled`), que não têm relação com este evento de volume.

O defeito real não é o erro de attach em si (efêmero, autocorrigido), mas a **ausência de proteção contra disrupção do Karpenter** para um StatefulSet single-replica com armazenamento EBS (ReadWriteOnce) — cada rotação/consolidação de nó feita pelo Karpenter nesse pod arrisca repetir essa janela de indisponibilidade do Redis (readiness probe cancelada, container killed) e depende da corrida attach/detach terminar bem.

Consultas efetivamente rodadas (todas permitidas, nenhuma "fora de escopo"):
- Events Explorer com a query exata do achado, janela completa (`window_from`–`window_to`): 1 evento (o próprio finding).
- Events Explorer `kube_namespace:medprev-web-app` numa janela ampla de +/-4h: 173 eventos, nenhum outro `FailedAttachVolume`.
- Events Explorer restrito a `kube_name:medprev-web-app-redis-master-0` numa janela de ±1h ao redor do achado: 7 eventos — a linha do tempo abaixo.
- `aggregate_spans` em `service:medprev-web-app-redis-master`: 0 spans.
- `aggregate_spans` em `service:medprev-web-app*` agrupado por serviço/`@error.handling`: só `medprev-web-app-backend-graphql`, 3.323 `handled`, 0 `unhandled`.
- `search_datadog_logs` em `pod_name:medprev-web-app-redis-master-0`: 438 logs na janela ±4h, amostra sem nenhuma linha de erro — só atividade normal de rewrite de AOF.

## Linha do tempo

1. 00:25:09 09/09/2026 BRT (epoch 1788924309000 · 2026-09-09T03:25:09.000Z) — Karpenter nomina o pod para `nodeclaim/default-mz7js` (nó `ip-10-0-10-78`) — primeira tentativa de realocação (evento `Nominated`, consulta `kube_name:medprev-web-app-redis-master-0`).
2. 00:33:14 09/09/2026 BRT (epoch 1788924794000 · 2026-09-09T03:33:14.000Z) — Karpenter renomina o pod para `nodeclaim/default-tjpbp` (nó `ip-10-0-10-11`), enquanto o pod ainda rodava no nó antigo `ip-10-0-11-5` — indício de consolidação/rotação de nó em andamento.
3. 00:34:01 09/09/2026 BRT (epoch 1788924841000 · 2026-09-09T03:34:01.000Z) — kubelet no nó antigo (`ip-10-0-11-5`) emite `Killing: Stopping container redis`.
4. 00:34:02 09/09/2026 BRT (epoch 1788924842000 · 2026-09-09T03:34:02.000Z) — readiness probe do pod é cancelada (`context canceled`) no mesmo nó — consequência direta do container sendo finalizado.
5. 00:34:03 09/09/2026 BRT (epoch 1788924843000 · 2026-09-09T03:34:03.000Z) — **o achado**: `attachdetach-controller` reporta `FailedAttachVolume` (Multi-Attach) para o volume, ao tentar anexar no novo nó (`ip-10-0-8-39`) antes do detach do nó antigo se completar.
6. 00:34:16 09/09/2026 BRT (epoch 1788924856000 · 2026-09-09T03:34:16.000Z) — pod agendado com sucesso em `ip-10-0-8-39` e `SuccessfulAttachVolume` reportado — a corrida se resolveu, 13s depois do erro.
7. 00:34:29 09/09/2026 BRT (epoch 1788924869000 · 2026-09-09T03:34:29.000Z) — container `redis` recriado, imagem `bitnami/redis:8.4` puxada e iniciada — pod voltou a operar normalmente.

Não foram encontradas outras ocorrências de `FailedAttachVolume` para este workload na janela ampla de ±4h nem no `observed_count` da coleta (ver seção Volume).

## Evidência

- Evento original do achado (Multi-Attach, `status:warn`, `kube_name:medprev-web-app-redis-master-0`): [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-web-app%20FailedAttachVolume&from_ts=1788808256645&to_ts=1789153856645&live=false).
- Nenhum outro `FailedAttachVolume` no mesmo namespace numa janela de ±4h ao redor de 00:34:03 09/09/2026 BRT (epoch 1788924843000 · 2026-09-09T03:34:03.000Z): consulta `source:kubernetes kube_namespace:medprev-web-app` de 1788910843000 a 1788938843000 → 173 eventos totais, sem outra ocorrência de `FailedAttachVolume`.
- Sequência de disrupção/recuperação do pod específico: consulta `source:kubernetes kube_namespace:medprev-web-app kube_name:medprev-web-app-redis-master-0` de 1788922000000 a 1788930000000 → 7 eventos (listados na linha do tempo acima).
- Ausência de instrumentação APM no Redis: `aggregate_spans` com `query:"service:medprev-web-app-redis-master"` no mesmo período → 0 spans.
- Nenhum erro de aplicação correlacionado: `aggregate_spans` com `query:"service:medprev-web-app*"` agrupado por `service`/`@error.handling` no mesmo período → só `medprev-web-app-backend-graphql`, 3.323 `handled`, 0 `unhandled`.
- Logs do pod normais antes/depois do incidente: `search_datadog_logs` com `kube_namespace:medprev-web-app pod_name:medprev-web-app-redis-master-0` no mesmo período → 438 logs, amostra sem erros (só rewrite de AOF em background).

## Ação recomendada

Proteger o pod `medprev-web-app-redis-master-0` (StatefulSet single-replica, EBS) contra disrupção de nó pelo Karpenter, para eliminar a janela de corrida attach/detach e a indisponibilidade momentânea do Redis durante consolidação de nós.

## Corpo da issue

### Descrição do incidente
O pod `medprev-web-app-redis-master-0` (Redis, StatefulSet single-replica com volume EBS, namespace `medprev-web-app`, cluster `eks-medprev-online-prd`) foi finalizado e recriado num nó diferente por ação do Karpenter, e durante a troca de nó o Kubernetes tentou anexar o volume EBS no novo nó antes do nó antigo liberá-lo, gerando um evento `FailedAttachVolume` (Multi-Attach). O evento ocorreu uma única vez, em 00:34:03 09/09/2026 BRT (epoch 1788924843000 · 2026-09-09T03:34:03.000Z), e se autorresolveu em 13 segundos. Impacto observável: o container `redis` foi finalizado e o readiness probe foi cancelado durante a janela de troca de nó, causando indisponibilidade momentânea do Redis (impacto exato em segundos não determinado com precisão — entre `Killing` às 00:34:01 09/09/2026 BRT (epoch 1788924841000 · 2026-09-09T03:34:01.000Z) e o container voltar a rodar às 00:34:29 09/09/2026 BRT (epoch 1788924869000 · 2026-09-09T03:34:29.000Z), ~28s).

### Causa raiz
Ruído: o `FailedAttachVolume` em si é um evento `status:warn` autorresolvido, sem evidência de falha persistente — 0 spans de aplicação e 0 logs de erro correlacionados nas consultas rodadas. A causa da disrupção foi rotação/consolidação de nó pelo Karpenter (`Nominated` às 00:25:09 09/09/2026 BRT (epoch 1788924309000 · 2026-09-09T03:25:09.000Z) e 00:33:14 09/09/2026 BRT (epoch 1788924794000 · 2026-09-09T03:33:14.000Z)) atingindo um StatefulSet single-replica com volume EBS ReadWriteOnce, sem proteção contra disrupção — o defeito real a corrigir é essa ausência de proteção, não o erro de attach.

### Linha do tempo
1. 00:25:09 09/09/2026 BRT (epoch 1788924309000 · 2026-09-09T03:25:09.000Z) — Karpenter nomina o pod para outro nó (`default-mz7js`).
2. 00:33:14 09/09/2026 BRT (epoch 1788924794000 · 2026-09-09T03:33:14.000Z) — Karpenter renomina o pod para `default-tjpbp` (nó `ip-10-0-10-11`), pod ainda no nó antigo `ip-10-0-11-5`.
3. 00:34:01 09/09/2026 BRT (epoch 1788924841000 · 2026-09-09T03:34:01.000Z) — kubelet finaliza o container `redis` no nó antigo.
4. 00:34:02 09/09/2026 BRT (epoch 1788924842000 · 2026-09-09T03:34:02.000Z) — readiness probe cancelada (`context canceled`).
5. 00:34:03 09/09/2026 BRT (epoch 1788924843000 · 2026-09-09T03:34:03.000Z) — `FailedAttachVolume` (Multi-Attach) ao tentar anexar o volume no novo nó `ip-10-0-8-39`.
6. 00:34:16 09/09/2026 BRT (epoch 1788924856000 · 2026-09-09T03:34:16.000Z) — pod agendado em `ip-10-0-8-39` e volume anexado com sucesso.
7. 00:34:29 09/09/2026 BRT (epoch 1788924869000 · 2026-09-09T03:34:29.000Z) — container `redis` recriado e rodando.

### Evidências
- [Events Explorer (evento original)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-web-app%20FailedAttachVolume&from_ts=1788808256645&to_ts=1789153856645&live=false)
- Consulta `source:kubernetes kube_namespace:medprev-web-app` (±4h): 173 eventos, sem outro `FailedAttachVolume`.
- Consulta `source:kubernetes kube_namespace:medprev-web-app kube_name:medprev-web-app-redis-master-0` (±1h): 7 eventos, linha do tempo completa acima.
- `aggregate_spans query:"service:medprev-web-app-redis-master"`: 0 spans.
- `aggregate_spans query:"service:medprev-web-app*"` agrupado por `service`/`@error.handling`: só `backend-graphql`, 100% `handled`.
- `search_datadog_logs query:"kube_namespace:medprev-web-app pod_name:medprev-web-app-redis-master-0"`: 438 logs na janela, sem erros.

### Ação recomendada
Repositório: `Medprev/medprev-web-app`. No manifesto/values Helm que configura o StatefulSet `medprev-web-app-redis-master` (subchart bitnami/redis), adicionar a anotação `karpenter.sh/do-not-disrupt: "true"` no template do pod (ou configurar um `nodeSelector`/taint dedicado que exclua esse pod da consolidação do Karpenter), para impedir que o Karpenter finalize esse pod single-replica durante rotação/consolidação de nós. Validar monitorando, por pelo menos 7 dias após o deploy, que não há novos eventos `FailedAttachVolume` nem `Killing`/`Unhealthy` para `medprev-web-app-redis-master-0` correlacionados a eventos `Nominated` do Karpenter na mesma janela.

### Volume
`observed_count: 1`, medido na janela `window_from` (16:10:56 07/09/2026 BRT · 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z)) a `window_to` (16:10:56 11/09/2026 BRT · 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z)). Consulta própria ampliada (±4h ao redor de `first_seen`, janela distinta e mais estreita) também retornou apenas 1 ocorrência desse Reason para o pod.

### Severidade e criticidade
`severity: medium` do achado não se aplica ao erro de attach em si, que foi autorresolvido em 13s sem evidência de impacto de dados ou erro de aplicação. Criticidade do defeito real (inferência): **média** — um StatefulSet single-replica sem proteção contra disrupção do Karpenter é um ponto único de falha que pode gerar indisponibilidade repetida do Redis a cada rotação de nó; se o Redis for usado como cache posso ser tolerável, mas se guarda estado não recuperável (sessão, filas), a criticidade sobe — isso não foi possível determinar a partir do achado ou das consultas rodadas.
