---
fingerprint: k8s-eks-medprev-online-prd-Unhealthy-nginx-gateway-fabric
source: kubernetes
reason: Unhealthy
novelty: new
service: nginx-gateway-fabric
environment: production
window:
  from: 1788803749711
  to: 1789149349711
observed:
  count: 82
  first_seen: 1788840178000
  last_seen: 1789120698000
severity: medium
state: discarded
cost:
  input_tokens: 507040
  output_tokens: 11727
  cache_read_input_tokens: 382558
  cache_creation_input_tokens: 124472
  duration_s: 129.506
  usd: 0.6963006
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Anginx-gateway-fabric%20Unhealthy&from_ts=1788803749711&to_ts=1789149349711&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Anginx-gateway-fabric%20Unhealthy&from_ts=1788803749711&to_ts=1789149349711&live=false

## Causa raiz

O achado é sobre o `nginx-gateway-fabric` (namespace `nginx-gateway-fabric`, cluster `eks-medprev-online-prd`), reportando falhas de readiness probe (`Unhealthy`) na porta interna 8081 (`/readyz`) desde 01:02:58 08/09/2026 BRT (epoch 1788840178000 · 2026-09-08T04:02:58.000Z). **Isto é RUÍDO**: os 82 eventos se distribuem por 46 pods distintos, no máximo 4 ocorrências por pod (a maioria com 1-2), e não há um pod específico falhando de forma persistente. Consultando `source:kubernetes kube_namespace:nginx-gateway-fabric (Killing OR Evicted)` na mesma janela, encontrei 69 eventos de Karpenter fazendo consolidação de nós (`Evicted: Underutilized` seguido de `Killing: Stopping container`) — o mesmo volume de churn que explica as falhas de probe: o pod é escolhido para terminação, o kubelet continua batendo no `/readyz` durante o grace period, e a conexão é recusada porque o container já está parando. Exemplo direto, mesmo pod (`nginx-gateway-fabric-nginx-7b6778b985-lgwvd`): `Killing` às 21:16:22 09/09/2026 BRT (epoch 1788999382000 · 2026-09-10T00:16:22.000Z), `Evicted: Underutilized` às 21:16:23 09/09/2026 BRT (epoch 1788999383000 · 2026-09-10T00:16:23.000Z), e as falhas de readiness reportadas às 21:16:29 09/09/2026 BRT (epoch 1788999389000 · 2026-09-10T00:16:29.000Z), 21:16:39 09/09/2026 BRT (epoch 1788999399000 · 2026-09-10T00:16:39.000Z) e 21:16:49 09/09/2026 BRT (epoch 1788999409000 · 2026-09-10T00:16:49.000Z) — exatamente a janela de shutdown do pod.

Não há spans APM para `service:nginx-gateway-fabric` na janela (`aggregate_spans` retornou 0 buckets) — o gateway não é instrumentado, então a classificação handled/unhandled não se aplica a este componente; a classificação sinal/ruído aqui vem da correlação evento-a-evento acima, não de span attributes.

Durante a mesma investigação, ao consultar os logs de acesso do serviço (`service:nginx-gateway-fabric status:error`, 822.345 ocorrências de 29.512.123 logs totais na janela — 2,8%), encontrei um problema real e não relacionado ao probe: rajadas de `502`/`504`/`upstream timed out (110: Operation timed out)` apontando para o upstream `medprev-web-app-test_medprev-web-app-test-frontend_80` (host `alpha.medprev.online`, IPs `10.0.0.115:8080`, `10.0.1.115:8080`, `10.0.10.34:8080`, `10.0.0.187:8080`, `10.0.3.52:8080`), concentradas em janelas específicas (ex.: 08:42:35 10/09/2026 BRT (epoch 1789040555000 · 2026-09-10T11:42:35.000Z)–17:26:25 10/09/2026 BRT (epoch 1789071985000 · 2026-09-10T20:26:25.000Z), 21:42:57 10/09/2026 BRT (epoch 1789087377000 · 2026-09-11T00:42:57.000Z)–04:13:44 11/09/2026 BRT (epoch 1789110824000 · 2026-09-11T07:13:44.000Z), 09:53:43 11/09/2026 BRT (epoch 1789131223000 · 2026-09-11T12:53:43.000Z)–14:23:41 11/09/2026 BRT (epoch 1789147421000 · 2026-09-11T17:23:41.000Z)). Isso é o defeito real a reportar, não o `Unhealthy` original.

## Linha do tempo

- 01:02:58 08/09/2026 BRT (epoch 1788840178000 · 2026-09-08T04:02:58.000Z) — primeira ocorrência do achado: `Unhealthy: Readiness probe failed` no pod `nginx-gateway-fabric-nginx-7b6778b985-m2xgk` (`connection refused` na porta 8081). Query: `source:kubernetes env:production status:warn kube_namespace:nginx-gateway-fabric Unhealthy`.
- 01:03:08 08/09/2026 BRT (epoch 1788840188000 · 2026-09-08T04:03:08.000Z) — segunda falha de probe no mesmo pod, 10s depois (retry padrão do kubelet).
- 21:16:22 09/09/2026 BRT (epoch 1788999382000 · 2026-09-10T00:16:22.000Z) — Karpenter emite `Killing: Stopping container nginx` no pod `lgwvd`.
- 21:16:23 09/09/2026 BRT (epoch 1788999383000 · 2026-09-10T00:16:23.000Z) — Karpenter emite `8x Evicted: Underutilized` para o mesmo pod `lgwvd` (consolidação de nó).
- 21:16:29 09/09/2026 BRT (epoch 1788999389000 · 2026-09-10T00:16:29.000Z), 21:16:39 09/09/2026 BRT (epoch 1788999399000 · 2026-09-10T00:16:39.000Z), 21:16:49 09/09/2026 BRT (epoch 1788999409000 · 2026-09-10T00:16:49.000Z) — três falhas sucessivas de readiness probe no pod `lgwvd`, já em terminação — a mesma janela do `Killing`/`Evicted` acima.
- 07:44:55 09/09/2026 BRT (epoch 1788950695000 · 2026-09-09T10:44:55.000Z) — variante do sintoma: `HTTP probe failed with statuscode: 500` no pod `dbhnn` (em vez de `connection refused`), mesmo padrão de churn.
- 06:57:51 11/09/2026 BRT (epoch 1789120671000 · 2026-09-11T09:57:51.000Z) — última correlação observada: `Evicted: Underutilized` + `Killing` no pod `twpkh`.
- 06:58:18 11/09/2026 BRT (epoch 1789120698000 · 2026-09-11T09:58:18.000Z) — `last_seen` do achado (06:58:18 11/09/2026 BRT (epoch 1789120698000 · 2026-09-11T09:58:18.000Z)), consistente com o encerramento do ciclo de consolidação acima.

Os 82 eventos entre 01:02:58 08/09/2026 BRT (epoch 1788840178000 · 2026-09-08T04:02:58.000Z) e 06:58:18 11/09/2026 BRT (epoch 1789120698000 · 2026-09-11T09:58:18.000Z) seguem o mesmo padrão: pico de consolidação Karpenter → probe falha durante shutdown → pod substituído. Não peguei todos os 82 individualmente (a consulta paginaria demais); os campos do achado (`window_from`, `window_to`, `first_seen`, `last_seen`) garantem os limites da janela usados aqui.

## Evidência

- Achado original: 82 ocorrências entre 14:55:49 07/09/2026 BRT (epoch 1788803749711 · 2026-09-07T17:55:49.711Z) e 14:55:49 11/09/2026 BRT (epoch 1789149349711 · 2026-09-11T17:55:49.711Z) — [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Anginx-gateway-fabric%20Unhealthy&from_ts=1788803749711&to_ts=1789149349711&live=false).
- Confirmação independente: `aggregate_events` na mesma query/janela devolveu 82 eventos somados em 46 pods distintos, máximo 4 por pod — consistente com `observed_count`, sem divergência de janela a explicar.
- Correlação de causa: `search_datadog_events` com `source:kubernetes env:production kube_namespace:nginx-gateway-fabric (Killing OR BackOff OR OOMKilling OR NodeNotReady OR Evicted)` na mesma janela devolveu 69 eventos, dominados por `Killing`/`Evicted: Underutilized` do Karpenter.
- Ausência de instrumentação: `aggregate_spans` com `service:nginx-gateway-fabric` na mesma janela devolveu 0 buckets — sem spans APM para classificar handled/unhandled neste componente.
- Volume de tráfego normal: `search_datadog_logs` com `kube_namespace:nginx-gateway-fabric` mostrou 29.512.017 logs na janela, amostra com status `ok` e respostas HTTP 200 — tráfego seguindo normalmente durante o período do achado.
- Defeito real correlacionado: `analyze_datadog_logs` (`service:nginx-gateway-fabric`, mesma janela) — breakdown por status: `ok`=25.751.255, `notice`=1.877.250, `info`=866.463, `error`=822.345, `warn`=194.809, `critical`=1 (total ~29,5M).
- Padrão dos erros: `search_datadog_logs` com `use_log_patterns:true` sobre `service:nginx-gateway-fabric status:error` — os clusters de maior volume (168, 147, 124, 122, 106... ocorrências) são todos `502`/`504`/`upstream timed out (110: Operation timed out)` contra o upstream `medprev-web-app-test_medprev-web-app-test-frontend_80` / host `alpha.medprev.online`.

## Ação recomendada

Nenhuma ação é necessária sobre o `Unhealthy` em si — é ruído esperado de consolidação de nós pelo Karpenter. A ação real é investigar os timeouts de upstream para `medprev-web-app-test` via `alpha.medprev.online`, que respondem por 2,8% dos logs do gateway na janela.

## Corpo da issue

### Descrição do incidente
O `Unhealthy` (readiness probe failure na porta 8081) reportado para `nginx-gateway-fabric` no cluster `eks-medprev-online-prd` não é uma falha do gateway: é o efeito colateral esperado da consolidação de nós feita pelo Karpenter (`Evicted: Underutilized` + `Killing`), que reagenda pods do gateway continuamente. Nenhum impacto observável para o usuário foi encontrado atrelado a esse sintoma — o tráfego HTTP seguiu normal (200 OK) durante toda a janela.

Investigando os logs do mesmo serviço na mesma janela, encontrei um problema real e distinto: rajadas de erro `502`/`504`/`upstream timed out (110: Operation timed out)` do gateway ao proxyar para o upstream `medprev-web-app-test_medprev-web-app-test-frontend_80` (host `alpha.medprev.online`), concentradas em três janelas de horas ao longo de 07–11/09/2026.

### Causa raiz
RUÍDO — o `Unhealthy` do achado original é churn de infraestrutura: 82 falhas de probe espalhadas por 46 pods distintos (máx. 4 por pod), coincidindo evento a evento com 69 `Killing`/`Evicted: Underutilized` do Karpenter na mesma janela e namespace (evidência de trace de eventos, pod `lgwvd`: `Killing`/`Evicted` às 2026-09-10T00:16:22-23Z, falhas de probe às 00:16:29/39/49Z). Sem spans APM para este serviço, então a classificação handled/unhandled não se aplica; a conclusão de ruído vem da correlação de eventos.

Causa raiz do defeito real correlacionado (timeouts de upstream) **não determinada** — as consultas mostraram o sintoma (502/504/timeout de conexão para `medprev-web-app-test` em `alpha.medprev.online`) mas não investiguei a causa do lado do upstream (não há spans do gateway, e o upstream `medprev-web-app-test` está fora do escopo deste achado de Kubernetes).

### Linha do tempo
- 01:02:58 08/09/2026 BRT (epoch 1788840178000 · 2026-09-08T04:02:58.000Z) — primeira falha de probe do achado (pod `m2xgk`, connection refused).
- 21:16:22 09/09/2026 BRT (epoch 1788999382000 · 2026-09-10T00:16:22.000Z) — Karpenter `Killing` no pod `lgwvd`.
- 21:16:23 09/09/2026 BRT (epoch 1788999383000 · 2026-09-10T00:16:23.000Z) — Karpenter `Evicted: Underutilized` (8x) no pod `lgwvd`.
- 21:16:29 09/09/2026 BRT (epoch 1788999389000 · 2026-09-10T00:16:29.000Z) / 00:16:39Z / 00:16:49Z — três falhas de readiness probe no pod `lgwvd`, durante seu shutdown.
- 07:44:55 09/09/2026 BRT (epoch 1788950695000 · 2026-09-09T10:44:55.000Z) — variante do sintoma: `HTTP probe failed with statuscode: 500` no pod `dbhnn`.
- 08:42:35 10/09/2026 BRT (epoch 1789040555000 · 2026-09-10T11:42:35.000Z)–20:26:25Z, 21:42:57 10/09/2026 BRT (epoch 1789087377000 · 2026-09-11T00:42:57.000Z)–07:13:44Z, 09:53:43 11/09/2026 BRT (epoch 1789131223000 · 2026-09-11T12:53:43.000Z)–17:23:41Z — três rajadas de erro 502/504/timeout do gateway contra o upstream `medprev-web-app-test` (achado correlacionado, fora do escopo do `Unhealthy` original).
- 06:57:51 11/09/2026 BRT (epoch 1789120671000 · 2026-09-11T09:57:51.000Z)–09:58:18Z — última correlação Killing/Evicted (pod `twpkh`) e `last_seen` do achado.

### Evidências
- [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Anginx-gateway-fabric%20Unhealthy&from_ts=1788803749711&to_ts=1789149349711&live=false) — 82 eventos.
- Consulta `source:kubernetes env:production kube_namespace:nginx-gateway-fabric (Killing OR BackOff OR OOMKilling OR NodeNotReady OR Evicted)`, mesma janela — 69 eventos, dominados por Karpenter.
- Consulta `aggregate_spans` `service:nginx-gateway-fabric`, mesma janela — 0 buckets (sem instrumentação APM).
- Consulta `analyze_datadog_logs` (SQL `SELECT status, count(*) FROM logs GROUP BY status`, filtro `service:nginx-gateway-fabric`, mesma janela) — error=822.345 de ~29,5M logs totais.
- Consulta `search_datadog_logs` com `use_log_patterns:true`, `service:nginx-gateway-fabric status:error`, mesma janela — clusters dominantes de 502/504/upstream timeout contra `medprev-web-app-test`/`alpha.medprev.online`.

### Ação recomendada
Infra — sem repositório de código para o `Unhealthy` em si; nenhuma mudança é necessária no `nginx-gateway-fabric` ou na configuração do probe. Para o defeito real: abrir investigação separada sobre o serviço/upstream `medprev-web-app-test` (host `alpha.medprev.online`, porta 8080) quanto aos timeouts de conexão e leitura de header (`110: Operation timed out`) nas três janelas listadas acima — verificar saturação/latência do backend `medprev-web-app-test-frontend` nesses horários. Validar a correção observando se `service:nginx-gateway-fabric status:error` com o padrão `upstream timed out ... alpha.medprev.online` cai a zero nas próximas rajadas equivalentes.

### Volume
`observed_count`: 82 ocorrências entre 14:55:49 07/09/2026 BRT (epoch 1788803749711 · 2026-09-07T17:55:49.711Z) e 14:55:49 11/09/2026 BRT (epoch 1789149349711 · 2026-09-11T17:55:49.711Z). Consulta direta via `aggregate_events` na mesma janela confirmou o mesmo total (82), sem divergência.

### Severidade e criticidade
`severity` do achado: `medium` — não se aplica ao `Unhealthy` em si, que é ruído de infraestrutura sem impacto observável. Para o defeito real encontrado (timeouts de upstream para `medprev-web-app-test`): criticidade **inferência minha**, não dado direto do achado — avalio como potencialmente maior que `medium`, já que 2,8% dos logs do gateway na janela são erros de upstream em rajadas concentradas, o que pode representar degradação real de resposta para usuários acessando via `alpha.medprev.online` nesses períodos.
