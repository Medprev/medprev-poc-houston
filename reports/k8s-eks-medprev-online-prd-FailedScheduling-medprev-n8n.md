---
fingerprint: k8s-eks-medprev-online-prd-FailedScheduling-medprev-n8n
source: kubernetes
reason: FailedScheduling
novelty: new
service: medprev-n8n
environment: production
window:
  from: 1788808256645
  to: 1789153856645
observed:
  count: 3
  first_seen: 1789087464000
  last_seen: 1789087491000
severity: medium
state: new
cost:
  input_tokens: 348718
  output_tokens: 10034
  cache_read_input_tokens: 281462
  cache_creation_input_tokens: 67246
  duration_s: 104.485
  usd: 0.4302844
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-n8n%20FailedScheduling&from_ts=1788808256645&to_ts=1789153856645&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-n8n%20FailedScheduling&from_ts=1788808256645&to_ts=1789153856645&live=false

## Causa raiz

O achado é um evento `FailedScheduling` no namespace `medprev-n8n` do cluster `eks-medprev-online-prd`. Consultando o Datadog diretamente, confirmo que o evento é **RUÍDO**: os 3 eventos são scheduling waits transitórios durante um rollout de deploy Helm do Deployment `medprev-n8n`, resolvidos automaticamente pelo Karpenter provisionando um novo nó — não há falha de aplicação, timeout perene nem indisponibilidade não resolvida. Não existe classificação `handled`/`unhandled` aplicável aqui (essa métrica é de spans de erro de aplicação, não de eventos de scheduling do Kubernetes); a evidência de "esperado" vem do próprio trace de eventos do pod, que mostra o ciclo completo Kill → FailedScheduling → Nominated → Scheduled → Started em sequência normal de rollout.

O que de fato vale investigar, achado correlacionado no mesmo trace: o rollout do Deployment iniciado às 21:44:45 10/09/2026 BRT (epoch 1789087485000 · 2026-09-11T00:44:45.000Z) (evento `change_tracking`, `identified_changes:9`) só chegou a `kube_condition_available:true` às 21:50:46 10/09/2026 BRT (epoch 1789087846000 · 2026-09-11T00:50:46.000Z) — quase 6 minutos depois. A maior parte desse tempo (3m35s) foi o pull da imagem `n8n:2.13.0` (277.493.888 bytes) no nó novo provisionado pelo Karpenter, que não tinha a imagem em cache. Esse é o problema real: cada deploy que força scale-up de nó paga esse custo de pull "a frio", estendendo a janela de indisponibilidade do pod único de `medprev-n8n`.

Consultas rodadas e o que retornaram:
- `search_datadog_logs` `service:medprev-n8n` na janela do achado → 0 logs.
- `search_datadog_spans` `service:medprev-n8n status:error` na janela do achado → 0 spans (serviço não emite APM).
- `search_datadog_events` com a query exata do achado → 3 eventos, confirmando `observed_count`.
- `aggregate_events` de `FailedScheduling` cluster-wide agrupado por `kube_namespace` na mesma janela → `medprev-n8n` teve o menor volume (3) entre 7 namespaces afetados (`medprev-web-app`: 143, `medprev-rest-api`: 79, `medprev-analytics-etl-airflow`: 30, `medprev-feature-flag`: 6, `medprev-cms`: 3, `medprev-institucional-cms`: 3) — indício de pressão de capacidade cluster-wide, não um problema isolado de `medprev-n8n`.
- `search_datadog_events` no pod/namespace na janela do rollout → 19 eventos, usados para montar a linha do tempo abaixo.
- `search_datadog_events` `source:change_tracking` no namespace → 8 deploys de Deployment/StatefulSet, confirmando o gatilho do rollout.

## Linha do tempo

- 21:44:22 10/09/2026 BRT (epoch 1789087462000 · 2026-09-11T00:44:22.000Z) — Karpenter emite `Killing` (parando containers `n8n-main` e `redis`) e `Nominated` para `nodeclaim/default-vxxmz` — início do rollout do pod antigo.
- 21:44:23 10/09/2026 BRT (epoch 1789087463000 · 2026-09-11T00:44:23.000Z) — `SuccessfulCreate` cria o novo pod `medprev-n8n-dcc8d6554-9887n`; kubelet reporta `Unhealthy` readiness no pod antigo (esperado, container em finalização).
- 21:44:24 10/09/2026 BRT (epoch 1789087464000 · 2026-09-11T00:44:24.000Z) — Primeiro `FailedScheduling`: "0/11 nodes are available: 2 Insufficient memory, 3 node(s) had untolerated taint(s), 8 Insufficient cpu" (consulta: `source:kubernetes env:production status:warn kube_namespace:medprev-n8n FailedScheduling`); no mesmo segundo, Karpenter já emite `Nominated: nodeclaim/default-7k6ff`.
- 21:44:25 10/09/2026 BRT (epoch 1789087465000 · 2026-09-11T00:44:25.000Z) — `SuccessfulCreate` do pod do StatefulSet `medprev-n8n-redis-master`.
- 21:44:27 10/09/2026 BRT (epoch 1789087467000 · 2026-09-11T00:44:27.000Z) — Pod do Redis é `Scheduled` no nó `ip-10-0-0-113` e inicia `Pulling` da imagem.
- 21:44:45 10/09/2026 BRT (epoch 1789087485000 · 2026-09-11T00:44:45.000Z) — Evento `change_tracking` confirma: Deployment `medprev-n8n` atualizado, `identified_changes:9`, `kube_condition_available:false`.
- 21:44:51 10/09/2026 BRT (epoch 1789087491000 · 2026-09-11T00:44:51.000Z) — Segundo/terceiro `FailedScheduling` (0/12 nós, mesmas razões) — mesmo pod, ainda aguardando o nó novo do Karpenter.
- 21:45:12 10/09/2026 BRT (epoch 1789087512000 · 2026-09-11T00:45:12.000Z) — Pod principal é `Scheduled` no nó `ip-10-0-1-103` (nó provisionado pelo Karpenter) e inicia `Pulling` da imagem `node:20-alpine`; `TaintManagerEviction` cancela a remoção do pod.
- 21:45:18 10/09/2026 BRT (epoch 1789087518000 · 2026-09-11T00:45:18.000Z) — Container init `node:20-alpine` criado, pulado (6.3s) e iniciado.
- 21:45:47 10/09/2026 BRT (epoch 1789087547000 · 2026-09-11T00:45:47.000Z) — Início do `Pulling` da imagem principal `n8nio/n8n:2.13.0` (277.493.888 bytes).
- 21:49:23 10/09/2026 BRT (epoch 1789087763000 · 2026-09-11T00:49:23.000Z) — Imagem `n8n:2.13.0` pulled após **3m35s**; container criado e iniciado.
- 21:49:31 10/09/2026 BRT (epoch 1789087771000 · 2026-09-11T00:49:31.000Z) a 21:50:15 10/09/2026 BRT (epoch 1789087815000 · 2026-09-11T00:50:15.000Z) — Falhas sucessivas de liveness/readiness (`connection refused` → HTTP 503 → timeout) enquanto a aplicação n8n sobe — comportamento esperado de boot.
- 21:50:46 10/09/2026 BRT (epoch 1789087846000 · 2026-09-11T00:50:46.000Z) — Evento `change_tracking` confirma `kube_condition_available:true`: rollout do Deployment concluído, ~6min02s após o início do `Killing`.

## Evidência

- 3 eventos `FailedScheduling` na janela 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) – 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z), confirmando `observed_count`: [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-n8n%20FailedScheduling&from_ts=1788808256645&to_ts=1789153856645&live=false).
- Ausência de logs de aplicação: `search_datadog_logs` com `service:medprev-n8n` na mesma janela → 0 resultados (query executada diretamente, sem link dedicado no achado).
- Ausência de spans de erro: `search_datadog_spans` com `service:medprev-n8n status:error` na mesma janela → 0 resultados (query executada diretamente, sem link dedicado no achado); confirma que o serviço não emite APM ou não teve erros de request.
- Distribuição cluster-wide de `FailedScheduling` por namespace na mesma janela (`aggregate_events`, `group_by: kube_namespace`) → `medprev-n8n` com o menor volume (3) frente a `medprev-web-app` (143), `medprev-rest-api` (79) e `medprev-analytics-etl-airflow` (30) — consulta direta, sem link dedicado.
- Sequência completa de eventos do pod/namespace (`search_datadog_events`, query `kube_namespace:medprev-n8n (source:kubernetes OR karpenter OR scale)`) → 19 eventos, usados na linha do tempo acima — consulta direta, sem link dedicado.
- Deploys confirmados via `source:change_tracking` no namespace → 8 eventos de atualização de Deployment/StatefulSet, incluindo o rollout de 21:44:45 10/09/2026 BRT (epoch 1789087485000 · 2026-09-11T00:44:45.000Z) a 21:50:46 10/09/2026 BRT (epoch 1789087846000 · 2026-09-11T00:50:46.000Z) — consulta direta, sem link dedicado.

## Ação recomendada

Não há ação de código a tomar sobre o `FailedScheduling` em si (é ruído esperado de rollout). Recomenda-se investigar, na infraestrutura, o pré-cache/pré-pull da imagem `n8nio/n8n` nos nós do node pool padrão do Karpenter (ou usar `imagePullPolicy`/warm pool) para reduzir a janela de indisponibilidade de ~6 minutos observada a cada deploy do pod único de `medprev-n8n`.

## Corpo da issue

### Descrição do incidente
Durante um rollout de deploy do Helm chart `medprev-n8n` (namespace `medprev-n8n`, cluster `eks-medprev-online-prd`), o pod único da aplicação ficou indisponível por aproximadamente 6 minutos, entre a finalização do pod antigo e o novo pod ficar pronto (`kube_condition_available: true`). A maior parte desse tempo (3m35s) foi consumida pelo pull "a frio" da imagem `n8nio/n8n:2.13.0` (277 MB) em um nó novo provisionado pelo Karpenter, que não tinha a imagem em cache. Como `medprev-n8n` não tem réplica adicional, esse é um período de indisponibilidade total do serviço a cada deploy que force scale-up de nó.

### Causa raiz
RUÍDO quanto ao evento original: os 3 `FailedScheduling` são scheduling waits transitórios (~27–48s) resolvidos automaticamente pelo Karpenter, sem indisponibilidade não explicada — não há métrica `handled`/`unhandled` aplicável (evento de infraestrutura, não span de aplicação), e `search_datadog_logs`/`search_datadog_spans` para `service:medprev-n8n` na janela retornaram 0 resultados, ou seja, nenhum erro de aplicação correlacionado. O problema real, correlacionado no mesmo trace de eventos, é o tempo de pull de imagem sem cache em nó novo, que estende a janela de indisponibilidade do pod único a cada deploy.

### Linha do tempo
1. 21:44:22 10/09/2026 BRT (epoch 1789087462000 · 2026-09-11T00:44:22.000Z) — Karpenter mata os containers do pod antigo (`Killing`) e nomina novo nó (`nodeclaim/default-vxxmz`).
2. 21:44:24 10/09/2026 BRT (epoch 1789087464000 · 2026-09-11T00:44:24.000Z) — Primeiro `FailedScheduling` (0/11 nós disponíveis: memória, taints, CPU insuficientes); Karpenter já renomina para `nodeclaim/default-7k6ff` no mesmo segundo.
3. 21:44:45 10/09/2026 BRT (epoch 1789087485000 · 2026-09-11T00:44:45.000Z) — `change_tracking` confirma início do rollout do Deployment (`identified_changes:9`, `available:false`).
4. 21:44:51 10/09/2026 BRT (epoch 1789087491000 · 2026-09-11T00:44:51.000Z) — Segundo/terceiro `FailedScheduling` (0/12 nós), mesmo pod.
5. 21:45:12 10/09/2026 BRT (epoch 1789087512000 · 2026-09-11T00:45:12.000Z) — Pod agendado no nó novo provisionado pelo Karpenter (`ip-10-0-1-103`).
6. 21:45:47 10/09/2026 BRT (epoch 1789087547000 · 2026-09-11T00:45:47.000Z) — Início do pull da imagem `n8nio/n8n:2.13.0` (277.493.888 bytes).
7. 21:49:23 10/09/2026 BRT (epoch 1789087763000 · 2026-09-11T00:49:23.000Z) — Imagem pulled após 3m35s; container iniciado.
8. 21:49:31 10/09/2026 BRT (epoch 1789087771000 · 2026-09-11T00:49:31.000Z)–21:50:15 10/09/2026 BRT (epoch 1789087815000 · 2026-09-11T00:50:15.000Z) — Falhas de liveness/readiness durante boot da aplicação (esperado).
9. 21:50:46 10/09/2026 BRT (epoch 1789087846000 · 2026-09-11T00:50:46.000Z) — `change_tracking` confirma `available:true`: rollout concluído, ~6min02s após o início.

### Evidências
- Events Explorer do achado (3 ocorrências de `FailedScheduling` na janela): https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-n8n%20FailedScheduling&from_ts=1788808256645&to_ts=1789153856645&live=false
- Query direta (sem link dedicado): `service:medprev-n8n` em `search_datadog_logs`, janela do achado → 0 logs.
- Query direta (sem link dedicado): `service:medprev-n8n status:error` em `search_datadog_spans`, janela do achado → 0 spans.
- Query direta (sem link dedicado): `aggregate_events` de `FailedScheduling` cluster-wide agrupado por `kube_namespace`, janela do achado → 7 namespaces afetados, `medprev-n8n` com o menor volume (3).
- Query direta (sem link dedicado): `search_datadog_events` `kube_namespace:medprev-n8n (source:kubernetes OR karpenter OR scale)`, 21:43:20 10/09/2026 BRT (epoch 1789087400000 · 2026-09-11T00:43:20.000Z)–21:53:20 10/09/2026 BRT (epoch 1789088000000 · 2026-09-11T00:53:20.000Z) → 19 eventos (base da linha do tempo).
- Query direta (sem link dedicado): `search_datadog_events` `source:change_tracking (medprev-n8n OR n8n)` → 8 eventos de deploy, confirmando o rollout responsável.

### Ação recomendada
Infra — sem repositório de código, ação operacional: no chart Helm/values de `medprev-n8n` (ou na configuração do node pool `default` do Karpenter em `eks-medprev-online-prd`), habilitar pré-pull/warm-cache da imagem `n8nio/n8n:2.13.0` nos nós do pool (ex.: `DaemonSet` de pré-pull, ou nó pré-aquecido) para eliminar o pull a frio de 277 MB a cada scale-up de nó. Validar medindo, no próximo rollout, o tempo entre `Killing` e `kube_condition_available:true` via `source:change_tracking` — meta: reduzir a janela de indisponibilidade de ~6 minutos para o tempo de boot da aplicação sem o pull de imagem (segundos, não minutos).

### Volume
`observed_count`: 3 ocorrências de `FailedScheduling` entre 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) e 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z). Consulta direta ao Datadog com a mesma query e janela confirmou o mesmo total (3) — sem divergência.

### Severidade e criticidade
`severity` do achado: `medium` — não se aplica ao evento `FailedScheduling` em si, que é ruído esperado de rollout. Para o defeito real encontrado (indisponibilidade de ~6 minutos por pull de imagem a frio em cada deploy de um pod único, sem réplica): criticidade **inferência minha** — moderada a alta, pois `medprev-n8n` parece rodar sem réplica (um único ReplicaSet/pod visto nos eventos), então cada deploy interrompe totalmente as execuções de workflow do n8n por vários minutos.
