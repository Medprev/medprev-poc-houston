---
fingerprint: k8s-eks-medprev-online-prd-FailedGetResourceMetric-medprev-analytics-etl-airflow
source: kubernetes
reason: FailedGetResourceMetric
novelty: new
service: medprev-analytics-etl-airflow
environment: production
window:
  from: 1788721546044
  to: 1789067146044
observed:
  count: 1098
  first_seen: 1788721619000
  last_seen: 1789066916000
severity: medium
state: new
cost:
  input_tokens: 492908
  output_tokens: 10457
  cache_read_input_tokens: 388881
  cache_creation_input_tokens: 104017
  duration_s: 105.149
  usd: 0.6031472
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-analytics-etl-airflow%20FailedGetResourceMetric&from_ts=1788721546044&to_ts=1789067146044&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-analytics-etl-airflow%20FailedGetResourceMetric&from_ts=1788721546044&to_ts=1789067146044&live=false

## Causa raiz

O achado é do `HorizontalPodAutoscaler` do namespace `medprev-analytics-etl-airflow` (cluster `eks-medprev-online-prd`), evento `FailedGetResourceMetric`, reportado pelo componente `horizontal-pod-autoscaler`. **É ruído no Error Tracking/eventos de Kubernetes**: todas as 1098 ocorrências consultadas na janela têm mensagem idêntica — `failed to get cpu utilization: missing request for cpu in container worker-log-groomer of Pod medprev-analytics-etl-airflow-main-worker-0` —, cadência estável de ~5 em 5 minutos (72 eventos por bucket de 6h, praticamente constante do início ao fim da janela, ver linha do tempo), e uma consulta ampliada (`now-90d` até o início da janela) devolveu 24.776 ocorrências do mesmo padrão antes mesmo de `window_from` — ou seja, é um estado crônico, não uma regressão. A causa direta e verificada é que o container sidecar `worker-log-groomer` do StatefulSet `medprev-analytics-etl-airflow-main-worker` não declara `resources.requests.cpu`, então o HPA não consegue calcular a porcentagem de utilização de CPU para esse container a cada ciclo de reconciliação e loga o warning — comportamento esperado do HPA diante de uma configuração incompleta, não uma falha transitória. Não há spans de APM para este serviço no período (`aggregate_spans` com `service:medprev-analytics-etl-airflow` devolveu 0 buckets — consulta vazia, registrado), então não foi possível seguir a regra do "trace do próprio erro"; o serviço não é instrumentado com APM.

Ao consultar os logs de aplicação do mesmo namespace/serviço na mesma janela (`search_datadog_logs`, `service:medprev-analytics-etl-airflow kube_namespace:medprev-analytics-etl-airflow status:(warn OR error)`), apareceu um problema real e correlacionado, diferente do achado original: `find: cannot delete '/opt/airflow/logs': Device or resource busy`, status `error`, 758 ocorrências na mesma janela (consulta restrita ao texto exato) — esse é exatamente o job que o container `worker-log-groomer` executa (limpeza periódica de logs do Airflow). Esse é o defeito que vale a pena investigar, não o `FailedGetResourceMetric` em si.

## Linha do tempo

- 16:06:59 06/09/2026 BRT (epoch 1788721619000 · 2026-09-06T19:06:59.000Z) — primeira ocorrência do achado dentro do histórico completo (`first_seen`), evento `FailedGetResourceMetric` do HPA `medprev-analytics-etl-airflow-main-worker`.
- 2026-09-06T18:00 a 2026-09-10T12:00 — volume estável por bucket de 6h (`aggregate_events`, intervalo 6h): 56, 61, 55, 72, 72, 61, 62, 72, 72, 70, 72, 72, 72, 72, 72, 72 ocorrências — sem picos, consistente com um problema crônico de configuração e não com uma degradação pontual.
- 01:35:16 10/09/2026 BRT (epoch 1789014916000 · 2026-09-10T04:35:16.000Z) a 02:16:31 10/09/2026 BRT (epoch 1789017391000 · 2026-09-10T05:16:31.000Z) — múltiplos redeploys do StatefulSet `medprev-analytics-etl-airflow-main-worker`, do StatefulSet `-redis`, do Deployment `-scheduler` e do `-dag-processor` (`source:change_tracking`, `identified_changes` variando de 1 a 9) — nenhum desses redeploys altera a cadência do `FailedGetResourceMetric` no bucket seguinte (72/6h antes e depois), evidenciando que a falta de `resources.requests.cpu` no `worker-log-groomer` não foi tocada por eles.
- 14:26:46 10/09/2026 BRT (epoch 1789061206000 · 2026-09-10T17:26:46.000Z) / 14:26:47 10/09/2026 BRT (epoch 1789061207000 · 2026-09-10T17:26:47.000Z) — novo redeploy do StatefulSet `medprev-analytics-etl-airflow-main-worker` (`identified_changes:1`), também sem efeito no padrão do evento (último bucket completo antes dele, 12:00–18:00, segue com 72 ocorrências).
- 16:00:02 10/09/2026 BRT (epoch 1789066802000 · 2026-09-10T19:00:02.000Z) — log de erro do serviço: `find: cannot delete '/opt/airflow/logs': Device or resource busy`, consulta `service:medprev-analytics-etl-airflow kube_namespace:medprev-analytics-etl-airflow status:error "cannot delete"`, 758 ocorrências na janela.
- 16:01:56 10/09/2026 BRT (epoch 1789066916000 · 2026-09-10T19:01:56.000Z) — última ocorrência do `FailedGetResourceMetric` dentro da janela (coincide com `last_seen` do achado), fim da janela de coleta.

## Evidência

- 1098 ocorrências de `FailedGetResourceMetric` entre `window_from` (16:05:46 06/09/2026 BRT (epoch 1788721546044 · 2026-09-06T19:05:46.044Z)) e `window_to` (16:05:46 10/09/2026 BRT (epoch 1789067146044 · 2026-09-10T19:05:46.044Z)) — [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-analytics-etl-airflow%20FailedGetResourceMetric&from_ts=1788721546044&to_ts=1789067146044&live=false).
- Mensagem idêntica em todas as amostras lidas (25 registros inspecionados diretamente via `search_datadog_events`): "missing request for cpu in container worker-log-groomer of Pod medprev-analytics-etl-airflow-main-worker-0" — mesma consulta acima.
- Volume por bucket de 6h estável (56–72/bucket) ao longo de toda a janela: `aggregate_events`, query `source:kubernetes env:production status:warn kube_namespace:medprev-analytics-etl-airflow FailedGetResourceMetric`, `group_by.interval=21600000`, `from=1788721546044`, `to=1789067146044`.
- O mesmo padrão já ocorria antes do início da janela do achado: 24.776 ocorrências entre `now-90d` e `1788721546044` — `aggregate_events`, mesma query, `from=now-90d`, `to=1788721546044`.
- `aggregate_spans` com `query: service:medprev-analytics-etl-airflow`, `from=1788721546044`, `to=1789067146044` devolveu 0 buckets — serviço sem spans de APM na janela.
- Log de erro correlacionado, 758 ocorrências na janela: `search_datadog_logs`, query `service:medprev-analytics-etl-airflow kube_namespace:medprev-analytics-etl-airflow status:error "cannot delete"`, `from=1788721546044`, `to=1789067146044` — mensagem: "find: cannot delete '/opt/airflow/logs': Device or resource busy".
- Consulta mais ampla de logs `warn`/`error` do mesmo serviço/namespace na janela devolveu 775 ocorrências — `search_datadog_logs`, query `service:medprev-analytics-etl-airflow kube_namespace:medprev-analytics-etl-airflow status:(warn OR error)`, mesma janela.
- Múltiplos redeploys do StatefulSet/Deployment do namespace na janela sem efeito no padrão do achado: `search_datadog_events`, query `source:change_tracking kube_namespace:medprev-analytics-etl-airflow`, mesma janela.

## Ação recomendada

Tratar como duas frentes separadas: (1) ruído no HPA — adicionar `resources.requests.cpu` ao container `worker-log-groomer` no StatefulSet `medprev-analytics-etl-airflow-main-worker` (chart `airflow-1.20.0`) para o HPA conseguir calcular utilização de CPU e parar de logar o warning; (2) investigar separadamente, com prioridade maior, o erro real "Device or resource busy" na limpeza de `/opt/airflow/logs`, que ocorre centenas de vezes na mesma janela e pode indicar deleção concorrente do mesmo diretório por múltiplos processos/pods no mesmo volume.

## Corpo da issue

### Descrição do incidente
O `HorizontalPodAutoscaler` do StatefulSet `medprev-analytics-etl-airflow-main-worker`, namespace `medprev-analytics-etl-airflow`, cluster `eks-medprev-online-prd`, emite continuamente o evento `FailedGetResourceMetric` porque o container sidecar `worker-log-groomer` não declara `resources.requests.cpu`. Sem esse request, o HPA não consegue calcular percentual de utilização de CPU para esse container a cada ciclo de reconciliação (a cada ~5 minutos). Não há impacto funcional direto conhecido — o HPA continua escalando com base nos demais containers do pod —, mas o sinal de autoscaling para esse container fica cego e o volume de eventos infla o Events Explorer.

### Causa raiz
Ruído — 1098 ocorrências na janela consultada (16:05:46 06/09/2026 BRT (epoch 1788721546044 · 2026-09-06T19:05:46.044Z) a 16:05:46 10/09/2026 BRT (epoch 1789067146044 · 2026-09-10T19:05:46.044Z)), todas com a mesma mensagem, cadência estável de ~5 minutos e 24.776 ocorrências do mesmo padrão já registradas antes do início da janela — comportamento esperado do HPA diante de um container sem `resources.requests.cpu`, não uma falha transitória ou regressão. O container afetado é `worker-log-groomer` (falta de request de CPU), causa confirmada diretamente pelo texto do evento, não inferida.

### Linha do tempo
- 16:06:59 06/09/2026 BRT (epoch 1788721619000 · 2026-09-06T19:06:59.000Z) — primeira ocorrência registrada no histórico do achado.
- 2026-09-06T18:00 a 2026-09-10T12:00 — cadência estável (56 a 72 eventos por bucket de 6h), sem picos.
- 01:35:16 10/09/2026 BRT (epoch 1789014916000 · 2026-09-10T04:35:16.000Z) a 02:16:31 10/09/2026 BRT (epoch 1789017391000 · 2026-09-10T05:16:31.000Z) — redeploys de StatefulSet/Deployment no mesmo namespace (`worker`, `redis`, `scheduler`, `dag-processor`) sem efeito na cadência do evento.
- 14:26:46 10/09/2026 BRT (epoch 1789061206000 · 2026-09-10T17:26:46.000Z) / 14:26:47 10/09/2026 BRT (epoch 1789061207000 · 2026-09-10T17:26:47.000Z) — novo redeploy do StatefulSet `medprev-analytics-etl-airflow-main-worker`, também sem efeito.
- 16:00:02 10/09/2026 BRT (epoch 1789066802000 · 2026-09-10T19:00:02.000Z) — log de erro correlacionado do próprio serviço: `find: cannot delete '/opt/airflow/logs': Device or resource busy` (758 ocorrências na janela).
- 16:01:56 10/09/2026 BRT (epoch 1789066916000 · 2026-09-10T19:01:56.000Z) — última ocorrência do `FailedGetResourceMetric` dentro da janela (= `last_seen`).

### Evidências
- [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-analytics-etl-airflow%20FailedGetResourceMetric&from_ts=1788721546044&to_ts=1789067146044&live=false)
- Consulta: `aggregate_events`, `source:kubernetes env:production status:warn kube_namespace:medprev-analytics-etl-airflow FailedGetResourceMetric`, intervalo 6h, mesma janela — volume estável.
- Consulta: `aggregate_events`, mesma query, `from=now-90d` a `to=1788721546044` — 24.776 ocorrências antes da janela.
- Consulta: `aggregate_spans`, `service:medprev-analytics-etl-airflow`, mesma janela — 0 spans.
- Consulta: `search_datadog_logs`, `service:medprev-analytics-etl-airflow kube_namespace:medprev-analytics-etl-airflow status:error "cannot delete"`, mesma janela — 758 ocorrências.
- Consulta: `search_datadog_events`, `source:change_tracking kube_namespace:medprev-analytics-etl-airflow`, mesma janela — redeploys sem correlação.

### Ação recomendada
Repositório: infra — sem repositório de código, ação operacional (`target_repo` é `null`). Ajustar os values do Helm chart `airflow-1.20.0` usado pelo ArgoCD (`argocd.argoproj.io/instance:medprev-analytics-etl-airflow-main`) para declarar `resources.requests.cpu` no container `worker-log-groomer` do StatefulSet `medprev-analytics-etl-airflow-main-worker`. Validar aplicando o valores no ambiente e confirmando, pela mesma query do Events Explorer acima, que a taxa de `FailedGetResourceMetric` cai a zero nas horas seguintes ao deploy. Separadamente — e com prioridade mais alta — abrir investigação específica para o erro `find: cannot delete '/opt/airflow/logs': Device or resource busy`, que se repetiu 758 vezes na mesma janela e sugere concorrência de deleção no mesmo path de log; validar checando se o volume de logs é compartilhado entre múltiplos pods/containers e se `worker-log-groomer` roda concorrente com o processo do worker no mesmo diretório.

### Volume
1098 ocorrências entre 16:05:46 06/09/2026 BRT (epoch 1788721546044 · 2026-09-06T19:05:46.044Z) e 16:05:46 10/09/2026 BRT (epoch 1789067146044 · 2026-09-10T19:05:46.044Z) (`observed_count` do achado, confirmado pela consulta ao Datadog na mesma janela). Consulta ampliada a `now-90d`–`to=1788721546044` (janela anterior à do achado) devolveu 24.776 ocorrências adicionais do mesmo padrão.

### Severidade e criticidade
`severity` do achado: `medium` — mas essa severidade se refere ao `FailedGetResourceMetric`, classificado aqui como ruído, e não se aplica ao evento em si. Para o defeito real encontrado (log-groomer falhando em deletar logs com "Device or resource busy", 758x na janela): criticidade **inferência** — potencialmente média a alta, pois um log-groomer que falha repetidamente pode levar a acúmulo de logs não removidos e esgotamento de disco/volume ao longo do tempo no worker do Airflow; não há neste achado um sinal direto de esgotamento de espaço, então essa consequência ainda não está confirmada e precisa de investigação própria.
