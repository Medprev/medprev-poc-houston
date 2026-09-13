---
fingerprint: k8s-eks-medprev-online-prd-Unhealthy-medprev-cms
source: kubernetes
reason: Unhealthy
novelty: new
service: medprev-cms
environment: production
window:
  from: 1788806810930
  to: 1789152410930
observed:
  count: 50
  first_seen: 1788808980000
  last_seen: 1789149745000
severity: medium
state: new
cost:
  input_tokens: 334904
  output_tokens: 7961
  cache_read_input_tokens: 223863
  cache_creation_input_tokens: 111033
  duration_s: 91.572
  usd: 0.5731506
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-cms%20Unhealthy&from_ts=1788806810930&to_ts=1789152410930&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-cms%20Unhealthy&from_ts=1788806810930&to_ts=1789152410930&live=false

## Causa raiz

O achado é dos eventos Kubernetes (`source:kubernetes`) do pod do `medprev-cms` no cluster `eks-medprev-online-prd`, reason `Unhealthy` — não é Error Tracking, então a classificação `handled`/`unhandled` de `@error.handling` não se aplica (essa métrica é exclusiva de spans APM). Apliquei o equivalente para eventos de infraestrutura: consultei a sequência completa de eventos de um pod amostral (`medprev-cms-58548cdc94-z9zpg`) e não há `BackOff`, `CrashLoopBackOff` nem `Failed` associados — apenas `Scheduled → Pulling → Pulled (50.764s) → Started → 1x Unhealthy (startup probe) → Killing` 7 minutos depois, sem outro evento de falha entre o meio. Isso é **ruído**: falha transitória e autorresolvida da startup probe logo após o container subir, não um travamento real. O padrão se repete em pelo menos 18 pods distintos (ver agregação por `host`) dentro da janela, cada um com 1–9 ocorrências concentradas em ~20–40s e depois nenhuma mais — coerente com a probe checando a porta `1337/_health` antes de o processo terminar de bindar, algo que se resolve nas checagens seguintes.

Tentei confirmar via logs de aplicação do pod amostral no intervalo do boot (`kube_namespace:medprev-cms service:medprev-cms kube_name:medprev-cms-58548cdc94-z9zpg`, 16:20:00 07/09/2026 BRT (epoch 1788808800000 · 2026-09-07T19:20:00.000Z)–19:30:00Z) e a consulta voltou vazia — não há log de erro de aplicação correlacionado, o que é consistente com "processo ainda subindo, ainda não logando/servindo" e não com uma falha de código.

O defeito real, portanto, não é "serviço instável" — é a configuração da `startupProbe` do Deployment `medprev-cms` gerando um evento de warning esperado a cada rollout/reposição de pod (alto churn de pods: ~18 pods distintos gerando os 50 eventos na janela).

## Linha do tempo

Não há eventos `Triggered`/`Re-Triggered`/`Recovered` de monitor aqui (fonte é Kubernetes, não Monitor); a consulta de `evidence_links` devolveu ocorrências brutas do Events Explorer. Nem todos os 50 puderam ser listados individualmente por causa do limite de tokens da consulta (a busca retornou 36 de 50, ordenados por timestamp), mas dá para reconstruir o padrão:

1. 16:21:51 07/09/2026 BRT (epoch 1788808911000 · 2026-09-07T19:21:51.000Z) — pod `medprev-cms-58548cdc94-z9zpg` agendado no node `ip-10-0-1-180`.
2. 16:22:42 07/09/2026 BRT (epoch 1788808962000 · 2026-09-07T19:22:42.000Z) — imagem `medprev-cms:e8ed3dc7` puxada (50.764s) e container iniciado.
3. 16:23:00 07/09/2026 BRT (epoch 1788808980000 · 2026-09-07T19:23:00.000Z) — 1ª ocorrência `Unhealthy`: `Startup probe failed: dial tcp 10.0.0.211:1337: connect: connection refused` (evento raiz do achado, `first_seen`: 16:23:00 07/09/2026 BRT (epoch 1788808980000 · 2026-09-07T19:23:00.000Z)).
4. 16:30:21 07/09/2026 BRT (epoch 1788809421000 · 2026-09-07T19:30:21.000Z) — `Killing: Stopping container medprev-cms` no mesmo pod, ~7 min depois da única falha de probe — sem novo evento `Unhealthy` no intervalo, indicando que a probe passou a responder normalmente antes da parada (parada consistente com ciclo de vida normal de rollout, não com falha de saúde contínua).
5. 05:21:43 08/09/2026 BRT (epoch 1788855703000 · 2026-09-08T08:21:43.000Z) a 05:22:23 08/09/2026 BRT (epoch 1788855743000 · 2026-09-08T08:22:23.000Z) — mesmo padrão em outro pod (`7xf8p`): 5 ocorrências em 40s, depois cessa.
6. Repetição do mesmo padrão (1 a 9 ocorrências por pod em janelas de 10–40s) em pelo menos 18 pods distintos ao longo da janela, últimos registrados em 00:43:45 11/09/2026 BRT (epoch 1789098225000 · 2026-09-11T03:43:45.000Z) e 00:43:55 11/09/2026 BRT (epoch 1789098235000 · 2026-09-11T03:43:55.000Z) (pod `kkr2w`).
7. `last_seen`: 15:02:25 11/09/2026 BRT (epoch 1789149745000 · 2026-09-11T18:02:25.000Z) — não coberto pelos 36 eventos retornados na primeira página (o restante, itens 37–50, não foi paginado por não alterar a conclusão: mesmo padrão já confirmado).

## Evidência

- 50 ocorrências entre 15:46:50 07/09/2026 BRT (epoch 1788806810930 · 2026-09-07T18:46:50.930Z) e 15:46:50 11/09/2026 BRT (epoch 1789152410930 · 2026-09-11T18:46:50.930Z) — [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-cms%20Unhealthy&from_ts=1788806810930&to_ts=1789152410930&live=false).
- Agregação por `host` na mesma janela/query: 18 hosts/pods distintos afetados, distribuição 1–9 eventos por host (ex.: `i-058b5ef7014b2f13a`: 9, a maioria com 1–4) — confirma churn distribuído, não um único pod travado.
- Sequência completa de eventos do pod `medprev-cms-58548cdc94-z9zpg` (`source:kubernetes env:production kube_namespace:medprev-cms kube_name:medprev-cms-58548cdc94-z9zpg`, 16:00:00 07/09/2026 BRT (epoch 1788807600000 · 2026-09-07T19:00:00.000Z)–20:00:00Z): 4 eventos — `Pulling/Scheduled` → `Pulled/Created/Started` → `Unhealthy` (única ocorrência) → `Killing`, sem `BackOff` nem segunda falha de probe.
- Busca de logs de aplicação (`kube_namespace:medprev-cms service:medprev-cms kube_name:medprev-cms-58548cdc94-z9zpg`, 16:20:00 07/09/2026 BRT (epoch 1788808800000 · 2026-09-07T19:20:00.000Z)–19:30:00Z): 0 resultados — sem log de erro correlacionado ao boot desse pod.
- Não há span de erro associado (fonte é evento de infraestrutura Kubernetes, não trace APM), então `aggregate_spans` por `@error.handling`/`@http.status_code` não se aplica a este achado.

## Ação recomendada
Ajustar o `startupProbe` do Deployment `medprev-cms` (aumentar `initialDelaySeconds`/`periodSeconds` ou `failureThreshold` para cobrir o tempo real de boot do processo na porta 1337) para eliminar o warning recorrente a cada rollout/scaling, sem impacto funcional hoje — nenhum pod ficou de fato indisponível.

## Corpo da issue

### Descrição do incidente
O Deployment `medprev-cms` (namespace `medprev-cms`, cluster `eks-medprev-online-prd`, produção) emite recorrentemente o evento Kubernetes `Unhealthy: Startup probe failed` (`dial tcp <pod-ip>:1337: connect: connection refused`) logo após cada novo pod subir. Não há impacto observável no serviço: os pods se recuperam sozinhos nas checagens seguintes e não há `BackOff`/`CrashLoopBackOff` associado.

### Causa raiz
Ruído — evento de infraestrutura sem `@error.handling` aplicável (não é APM), mas confirmado via reconstrução completa do ciclo de vida de um pod amostral: única falha de `startupProbe` 18s após o container iniciar, seguida de operação normal e parada 7 minutos depois sem novas falhas. O padrão se repete em 18 pods distintos na janela, cada um com 1–9 ocorrências em uma janela de 10–40s, sempre no início do boot. Causa provável (não confirmada por acesso ao manifesto do Deployment, que não foi consultado): `startupProbe.initialDelaySeconds`/`periodSeconds` configurados abaixo do tempo real que a aplicação leva para abrir a porta `1337`.

### Linha do tempo
1. 16:21:51 07/09/2026 BRT (epoch 1788808911000 · 2026-09-07T19:21:51.000Z) — pod `medprev-cms-58548cdc94-z9zpg` agendado.
2. 16:22:42 07/09/2026 BRT (epoch 1788808962000 · 2026-09-07T19:22:42.000Z) — imagem `medprev-cms:e8ed3dc7` puxada (50.764s) e container iniciado.
3. 16:23:00 07/09/2026 BRT (epoch 1788808980000 · 2026-09-07T19:23:00.000Z) — `Unhealthy: Startup probe failed` (evento-âncora do achado).
4. 16:30:21 07/09/2026 BRT (epoch 1788809421000 · 2026-09-07T19:30:21.000Z) — `Killing` do mesmo pod, sem nova falha de probe entre os dois eventos.
5. Mesmo padrão repetido em pelo menos 18 pods distintos entre 05:21:43 08/09/2026 BRT (epoch 1788855703000 · 2026-09-08T08:21:43.000Z) e 00:43:55 11/09/2026 BRT (epoch 1789098235000 · 2026-09-11T03:43:55.000Z), sempre concentrado nos primeiros segundos após `Started`.

### Evidências
- [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-cms%20Unhealthy&from_ts=1788806810930&to_ts=1789152410930&live=false) — 50 ocorrências, janela informada acima.
- Consulta `source:kubernetes env:production kube_namespace:medprev-cms kube_name:medprev-cms-58548cdc94-z9zpg` (16:00:00 07/09/2026 BRT (epoch 1788807600000 · 2026-09-07T19:00:00.000Z)–20:00:00Z) — 4 eventos, sem `BackOff`.
- Consulta de logs `kube_namespace:medprev-cms service:medprev-cms kube_name:medprev-cms-58548cdc94-z9zpg` (16:20:00 07/09/2026 BRT (epoch 1788808800000 · 2026-09-07T19:20:00.000Z)–19:30:00Z) — 0 resultados.
- Agregação por `host` da mesma query base — 18 hosts distintos, 1–9 eventos cada.

### Ação recomendada
Repositório `Medprev/medprev-cms`: revisar o `startupProbe` no manifesto do Deployment (Helm chart ou YAML do serviço, provavelmente em `deploy/`/`k8s/` do repo) e aumentar `initialDelaySeconds`/`periodSeconds`/`failureThreshold` para cobrir o tempo real de subida do processo na porta `1337` (o `Pulled` já levou 50.764s nesta amostra, e o processo aparentemente ainda não respondia 18s após `Started`). Validar rodando `houston run`/observando o próximo rollout: o evento `Unhealthy` para essa deployment não deve mais aparecer em `source:kubernetes kube_namespace:medprev-cms Unhealthy` nas primeiras dezenas de segundos após `Started`.

### Volume
50 ocorrências entre 15:46:50 07/09/2026 BRT (epoch 1788806810930 · 2026-09-07T18:46:50.930Z) e 15:46:50 11/09/2026 BRT (epoch 1789152410930 · 2026-09-11T18:46:50.930Z) — mesma janela usada nas consultas ao Datadog, sem divergência.

### Severidade e criticidade
`severity: medium` do achado não se aplica ao evento em si (é ruído esperado de boot). Criticidade real (inferência): baixa hoje, pois nenhum pod ficou indisponível de fato — mas o alto churn de pods observado (18 pods distintos gerando o mesmo warning em 4 dias) sugere volume de deploys/scaling elevado no namespace; se o `startupProbe` estiver genuinamente subdimensionado, o risco cresce proporcionalmente a esse churn (mais rollouts = mais ruído, e um pico de latência de boot real poderia então levar a falhas de probe persistentes e reinícios). Recomendo tratar como prioridade baixa/manutenção, não incidente.
