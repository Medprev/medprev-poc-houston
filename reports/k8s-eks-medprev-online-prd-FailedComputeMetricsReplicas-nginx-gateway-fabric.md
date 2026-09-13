---
fingerprint: k8s-eks-medprev-online-prd-FailedComputeMetricsReplicas-nginx-gateway-fabric
source: kubernetes
reason: FailedComputeMetricsReplicas
novelty: new
service: nginx-gateway-fabric
environment: production
window:
  from: 1788808256645
  to: 1789153856645
observed:
  count: 14
  first_seen: 1788924183000
  last_seen: 1789086458000
severity: medium
state: new
cost:
  input_tokens: 508261
  output_tokens: 11687
  cache_read_input_tokens: 430241
  cache_creation_input_tokens: 78008
  duration_s: 126.255
  usd: 0.5196682
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Anginx-gateway-fabric%20FailedComputeMetricsReplicas&from_ts=1788808256645&to_ts=1789153856645&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Anginx-gateway-fabric%20FailedComputeMetricsReplicas&from_ts=1788808256645&to_ts=1789153856645&live=false

## Causa raiz

O serviço afetado é `nginx-gateway-fabric-nginx` (o HorizontalPodAutoscaler do namespace `nginx-gateway-fabric`, cluster `eks-medprev-online-prd`), e o achado é **sintoma de um problema de infraestrutura cluster-wide, não de um bug no serviço**: o `metrics-server` do cluster está falhando repetidamente ao raspar (scrape) métricas dos kubelets dos nós via `/metrics/resource`. Confirmei isso consultando os logs do próprio `metrics-server` (`kube_namespace:kube-system service:metrics-server`) na mesma janela: **23.920 logs de erro** no total, com o padrão dominante `"Failed to scrape node" ... context deadline exceeded` ocorrendo **4.628 vezes** entre 17:17:17 07/09/2026 BRT (epoch 1788812237173 · 2026-09-07T20:17:17.173Z) e 16:07:12 11/09/2026 BRT (epoch 1789153632745 · 2026-09-11T19:07:12.745Z) — ou seja, atravessa toda a janela de coleta e continua depois dela. Há também 210 ocorrências de `dial tcp ... i/o timeout`, 48 de `remote error: tls: internal error` e 10 de `connection refused`, todas do mesmo scraper.

Isso é **sinal, não ruído**: os 14 eventos do achado (`FailedComputeMetricsReplicas`/`FailedGetResourceMetric`) são apenas a fração desse problema que atingiu o HPA de `nginx-gateway-fabric`. No mesmo intervalo, o mesmo tipo de evento ocorreu em **8 namespaces diferentes** (219 eventos no total — `medprev-rest-api`: 75, `medprev-face-liveness-app`: 46, `medprev-web-app`: 32, `medprev-cms`: 17, `medprev-institucional-cms`: 14, `medprev-metabase`: 14, `nginx-gateway-fabric`: 14, `medprev-analytics-etl-airflow`: 7), confirmando que a causa é o `metrics-server`/comunicação com kubelets, não algo específico do gateway nginx.

A causa raiz **exata** de por que o `metrics-server` não consegue raspar os kubelets (rede, throttling, kubelet sobrecarregado, churn de nós do Karpenter, timeout de scrape mal dimensionado) **não foi determinada** pelas consultas rodadas — os padrões de erro (`context deadline exceeded`, `i/o timeout`, `connection refused`, `tls: internal error`) são consistentes tanto com problema de rede/conectividade quanto com kubelets sobrecarregados, e nenhuma consulta adicional foi feita para isolar qual dessas é a causa primária (não há trace/span aplicável a este achado, que é de Kubernetes events + logs, não de APM). Consultas efetivamente rodadas e resultado de cada uma:
- Events Explorer com a query do achado, janela completa → 14 eventos (bate com `observed_count`).
- Mesmo evento agregado por `host` → 2 nós distintos (`i-07aa79ff3b225aa0a`: 12, `i-05d938105c83b3ba7`: 2) — não é falha de um único nó.
- Mesmo tipo de evento agregado por `kube_namespace`, mesma janela → 219 eventos em 8 namespaces (não isolado a `nginx-gateway-fabric`).
- Logs `service:metrics-server`, mesma janela → 23.920 logs, 100% status `error`.
- Clustering de padrões desses logs → dominado por falhas de scrape ao kubelet (ver acima).
- Checagem de eventos `FailedComputeMetricsReplicas` na última hora (`now-1h` a `now`) → 0 eventos, ou seja, não está disparando neste exato momento, embora os logs de erro do `metrics-server` continuassem até perto do fim da janela.

## Linha do tempo

1. 17:17:17 07/09/2026 BRT (epoch 1788812237173 · 2026-09-07T20:17:17.173Z) — início do padrão dominante de erro no `metrics-server` (`Failed to scrape node ... context deadline exceeded`), antes mesmo do primeiro evento do HPA nesta janela.
2. 00:23:03 09/09/2026 BRT (epoch 1788924183000 · 2026-09-09T03:23:03.000Z) — primeira ocorrência de `FailedComputeMetricsReplicas` no HPA `nginx-gateway-fabric-nginx` dentro da janela (`first_seen`), no nó `ip-10-0-10-78`.
3. 00:23:18 09/09/2026 BRT (epoch 1788924198000 · 2026-09-09T03:23:18.000Z) — 2ª ocorrência, mesmo nó, 15s depois.
4. 00:33:19 09/09/2026 BRT (epoch 1788924799000 · 2026-09-09T03:33:19.000Z) — 3ª ocorrência.
5. 00:33:34 09/09/2026 BRT (epoch 1788924814000 · 2026-09-09T03:33:34.000Z) — 4ª ocorrência, agora no nó `ip-10-0-8-39`.
6. 03:45:31 09/09/2026 BRT (epoch 1788936331000 · 2026-09-09T06:45:31.000Z) — 5ª ocorrência.
7. 03:45:46 09/09/2026 BRT (epoch 1788936346000 · 2026-09-09T06:45:46.000Z) — 6ª ocorrência.
8. 07:35:42 09/09/2026 BRT (epoch 1788950142000 · 2026-09-09T10:35:42.000Z) — 7ª ocorrência.
9. 07:35:57 09/09/2026 BRT (epoch 1788950157000 · 2026-09-09T10:35:57.000Z) — 8ª ocorrência.
10. 07:36:12 09/09/2026 BRT (epoch 1788950172000 · 2026-09-09T10:36:12.000Z) — 9ª ocorrência.
11. 07:54:44 09/09/2026 BRT (epoch 1788951284000 · 2026-09-09T10:54:44.000Z) — 10ª ocorrência.
12. 07:54:59 09/09/2026 BRT (epoch 1788951299000 · 2026-09-09T10:54:59.000Z) — 11ª ocorrência.
13. 21:27:08 10/09/2026 BRT (epoch 1789086428000 · 2026-09-11T00:27:08.000Z) — 12ª ocorrência (gap de ~1,5 dia desde a anterior).
14. 21:27:23 10/09/2026 BRT (epoch 1789086443000 · 2026-09-11T00:27:23.000Z) — 13ª ocorrência.
15. 21:27:38 10/09/2026 BRT (epoch 1789086458000 · 2026-09-11T00:27:38.000Z) — 14ª e última ocorrência (`last_seen`); a mensagem muda de "server is currently unable to handle the request" para `"no metrics returned from resource metrics API"`, indicando uma falha ligeiramente diferente (ausência de dado, não indisponibilidade do endpoint).
16. 16:07:12 11/09/2026 BRT (epoch 1789153632745 · 2026-09-11T19:07:12.745Z) — último log de erro do `metrics-server` (`context deadline exceeded`) visto na janela, mostrando que a causa de fundo seguiu ativa mesmo após o HPA parar de reportar o evento.
17. Checagem em `now-1h`–`now`: nenhum novo evento `FailedComputeMetricsReplicas` no cluster — não está disparando neste momento.

## Evidência

- 14 eventos `FailedComputeMetricsReplicas`/`FailedGetResourceMetric` do HPA `nginx-gateway-fabric-nginx` na janela `window_from`–`window_to`, batendo com `observed_count`: [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Anginx-gateway-fabric%20FailedComputeMetricsReplicas&from_ts=1788808256645&to_ts=1789153856645&live=false).
- Distribuição por host (2 nós, 12 e 2 eventos) — consulta: `aggregate_events` sobre a mesma query, `group_by: host`, janela `1788808256645`–`1789153856645`.
- O mesmo tipo de evento ocorre em 8 namespaces na mesma janela (219 eventos totais, 14 dos quais são `nginx-gateway-fabric`) — consulta: `aggregate_events` com `source:kubernetes env:production status:warn FailedComputeMetricsReplicas`, `group_by: kube_namespace`, mesma janela.
- 23.920 logs de erro do `metrics-server` na mesma janela, status 100% `error` — consulta: `service:metrics-server kube_namespace:kube-system`, `analyze_datadog_logs` (`GROUP BY status`), mesma janela; [Logs Explorer](https://app.datadoghq.com/logs?from_ts=1788808256645&live=false&query=kube_namespace%3Akube-system+service%3Ametrics-server&stream_sort=desc&to_ts=1789153856645).
- Padrão dominante de falha (`Failed to scrape node ... context deadline exceeded`, 4.628 ocorrências) e variantes (`i/o timeout`: 210, `tls: internal error`: 48, `connection refused`: 10) — consulta: `search_datadog_logs` com `use_log_patterns:true` sobre `service:metrics-server status:error`, mesma janela; [Logs Explorer (patterns)](https://app.datadoghq.com/logs?clustering_pattern_field_path=message&from_ts=1788808256645&live=false&query=kube_namespace%3Akube-system+service%3Ametrics-server+status%3Aerror&stream_sort=desc&to_ts=1789153856645&viz=pattern).
- Nenhum evento `FailedComputeMetricsReplicas` na última hora (`now-1h`–`now`) — consulta vazia, registrada: não está ativo neste exato momento.

## Ação recomendada

Ação é operacional/infra: investigar a saúde do `metrics-server` e a conectividade `metrics-server → kubelet:10250` no cluster `eks-medprev-online-prd` (recursos do pod, timeout de scrape, e possível throttling/latência de rede entre nós), já que o impacto não é específico de `nginx-gateway-fabric` e sim cluster-wide.

## Corpo da issue

### Descrição do incidente
O `metrics-server` do cluster `eks-medprev-online-prd` está falhando repetidamente ao coletar métricas de recursos (CPU/memória) dos kubelets via `/metrics/resource`, causando eventos `FailedComputeMetricsReplicas`/`FailedGetResourceMetric` em múltiplos HorizontalPodAutoscalers. No HPA `nginx-gateway-fabric-nginx` (namespace `nginx-gateway-fabric`) isso gerou 14 eventos entre `first_seen` (00:23:03 09/09/2026 BRT, epoch 1788924183000 · 00:23:03 09/09/2026 BRT (epoch 1788924183000 · 2026-09-09T03:23:03.000Z)) e `last_seen` (21:27:38 10/09/2026 BRT, epoch 1789086458000 · 21:27:38 10/09/2026 BRT (epoch 1789086458000 · 2026-09-11T00:27:38.000Z)). Impacto observável: durante essas janelas, o HPA não consegue calcular réplicas com base em CPU/memória, ficando sem sinal para escalar o `nginx-gateway-fabric-nginx` (o gateway de entrada do tráfego).

### Causa raiz
Sinal, não ruído — confirmado por 23.920 logs de erro do próprio `metrics-server` na mesma janela (100% status `error`), com 4.628 ocorrências do padrão dominante `"Failed to scrape node" ... context deadline exceeded` cobrindo toda a janela e o mesmo problema afetando 8 namespaces distintos (219 eventos `FailedComputeMetricsReplicas` no total, não só os 14 de `nginx-gateway-fabric`). A causa primária exata (rede entre `metrics-server` e kubelets, kubelet sobrecarregado, timeout de scrape mal dimensionado, ou churn de nós do Karpenter) **não foi determinada** — nenhuma consulta adicional isolou qual desses fatores é o gatilho.

### Linha do tempo
- 17:17:17 07/09/2026 BRT (epoch 1788812237173 · 2026-09-07T20:17:17.173Z): início do padrão dominante de erro no `metrics-server` (antes do primeiro evento do HPA na janela).
- 00:23:03 09/09/2026 BRT (epoch 1788924183000 · 2026-09-09T03:23:03.000Z) a 07:54:59 09/09/2026 BRT (epoch 1788951299000 · 2026-09-09T10:54:59.000Z): 11 ocorrências de `FailedComputeMetricsReplicas` no HPA, distribuídas entre os nós `ip-10-0-10-78` e `ip-10-0-8-39`.
- 21:27:08 10/09/2026 BRT (epoch 1789086428000 · 2026-09-11T00:27:08.000Z), 21:27:23 10/09/2026 BRT (epoch 1789086443000 · 2026-09-11T00:27:23.000Z), 21:27:38 10/09/2026 BRT (epoch 1789086458000 · 2026-09-11T00:27:38.000Z): últimas 3 ocorrências; a última muda a mensagem de erro para `"no metrics returned from resource metrics API"`.
- 16:07:12 11/09/2026 BRT (epoch 1789153632745 · 2026-09-11T19:07:12.745Z): último log de erro de scrape do `metrics-server` visto na janela — a causa de fundo seguiu ativa após o HPA parar de reportar o evento.
- Checagem em `now-1h`–`now`: nenhum evento novo — não está disparando no momento da investigação.

### Evidências
- [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Anginx-gateway-fabric%20FailedComputeMetricsReplicas&from_ts=1788808256645&to_ts=1789153856645&live=false)
- [Logs Explorer — metrics-server, mesma janela](https://app.datadoghq.com/logs?from_ts=1788808256645&live=false&query=kube_namespace%3Akube-system+service%3Ametrics-server&stream_sort=desc&to_ts=1789153856645)
- [Logs Explorer — padrões de erro do metrics-server](https://app.datadoghq.com/logs?clustering_pattern_field_path=message&from_ts=1788808256645&live=false&query=kube_namespace%3Akube-system+service%3Ametrics-server+status%3Aerror&stream_sort=desc&to_ts=1789153856645&viz=pattern)
- Consulta `aggregate_events` (`group_by: kube_namespace`, mesma janela) confirmando o problema em 8 namespaces, 219 eventos.

### Ação recomendada
Infra — sem repositório de código, ação operacional. Componente afetado: deployment `metrics-server` no namespace `kube-system` do cluster `eks-medprev-online-prd`. Ação: (1) checar recursos (CPU/memória, throttling) e réplicas do pod `metrics-server`; (2) revisar/aumentar `--kubelet-request-timeout` (padrão 10s, causa provável dos "context deadline exceeded"); (3) checar conectividade/latência de rede entre o nó do `metrics-server` e os kubelets na porta 10250, incluindo possível impacto de rotação de nós pelo Karpenter. Validação: após o ajuste, confirmar que a contagem de logs de erro `service:metrics-server` cai a zero (ou próximo) numa janela de 24h subsequente, e que não há novos eventos `FailedComputeMetricsReplicas` nos 8 namespaces afetados.

### Volume
14 ocorrências entre 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) e 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z), para o fingerprint específico de `nginx-gateway-fabric`. Consultando o Datadog na mesma janela, mas sem o filtro de namespace, o total do mesmo tipo de evento no cluster é 219 (`medprev-rest-api`: 75, `medprev-face-liveness-app`: 46, `medprev-web-app`: 32, `medprev-cms`: 17, `medprev-institucional-cms`: 14, `medprev-metabase`: 14, `nginx-gateway-fabric`: 14, `medprev-analytics-etl-airflow`: 7).

### Severidade e criticidade
`severity` do achado: `medium`. Como o achado foi classificado como sinal real (metrics-server falhando cluster-wide), a `severity: medium` do achado individual de `nginx-gateway-fabric` **subestima** o problema real: a criticidade correta é do defeito cluster-wide no `metrics-server`, que compromete o autoscaling baseado em CPU/memória de pelo menos 8 serviços simultaneamente — incluindo `medprev-rest-api` (75 eventos) e `medprev-web-app` (32 eventos), possivelmente mais críticos que o gateway nginx. Essa avaliação de criticidade de negócio é **inferência**: as consultas confirmam o volume e a abrangência do problema, mas não medem diretamente impacto em usuários finais (ex.: latência ou erros 5xx por falta de scale-out); nenhuma consulta de tráfego/latência foi rodada para isso.
