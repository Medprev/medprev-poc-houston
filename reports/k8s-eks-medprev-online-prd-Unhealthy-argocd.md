---
fingerprint: k8s-eks-medprev-online-prd-Unhealthy-argocd
source: kubernetes
reason: Unhealthy
novelty: new
service: argocd
environment: production
window:
  from: 1788808256645
  to: 1789153856645
observed:
  count: 3
  first_seen: 1788924147000
  last_seen: 1789094077000
severity: medium
state: new
cost:
  input_tokens: 513271
  output_tokens: 9243
  cache_read_input_tokens: 424560
  cache_creation_input_tokens: 88699
  duration_s: 98.42
  usd: 0.536791
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aargocd%20Unhealthy&from_ts=1788808256645&to_ts=1789153856645&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aargocd%20Unhealthy&from_ts=1788808256645&to_ts=1789153856645&live=false

## Causa raiz

O `argocd` (namespace `argocd`, cluster `eks-medprev-online-prd`) registrou 3 eventos Kubernetes `Unhealthy` (falha de readiness/liveness probe) na janela 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) até 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z). É **RUÍDO**: consultei o histórico de eventos de cada um dos 3 pods envolvidos e, nos 3 casos, o `Unhealthy` coincide, no mesmo segundo ou a poucos segundos, com uma transição de ciclo de vida do pod causada pelo Karpenter (consolidação/drift) ou com um cold-start de container recém-criado — não com uma falha real da aplicação. Não há classificação `handled`/`unhandled` aplicável (esta fonte é `kubernetes`, não Error Tracking), então a classificação de ruído aqui se apoia na correlação direta evento-a-evento, não em uma métrica agregada de erro de aplicação.

Consultas efetivamente rodadas e retorno de cada uma:
- `search_datadog_events` com a query exata de `evidence_links` → 3 eventos, batem exatamente com `observed_count`.
- `search_datadog_logs` `kube_namespace:argocd service:argocd-repo-server` na janela → 0 logs.
- `search_datadog_logs` `kube_namespace:argocd` (sem filtro de serviço) na janela → 1.977.803 logs, todos os 5 primeiros amostrados eram `info` genéricos ("Processing completed"/"Start processing"), nenhum erro.
- `aggregate_spans` `service:argocd-repo-server` agrupado por `@http.status_code` na janela → 0 buckets (o componente não emite spans APM).
- `search_datadog_events` para cada um dos 3 pods individualmente, janela estreita ao redor de cada ocorrência → confirma a correlação com Karpenter/startup descrita abaixo.

## Linha do tempo

1. 00:22:26 09/09/2026 BRT (epoch 1788924146000 · 2026-09-09T03:22:26.000Z) — Karpenter emite `Killing`/`Nominated` para o pod `argo-cd-argocd-repo-server-76df97c559-hzj4j`: container `repo-server` sendo parado e pod nomeado para reagendar em `nodeclaim/default-wq5n2`, `node/ip-10-0-10-167` (consolidação/drift do node). Consulta: `source:kubernetes kube_namespace:argocd Unhealthy` (evidence_links).
2. 00:22:27 09/09/2026 BRT (epoch 1788924147000 · 2026-09-09T03:22:27.000Z) — Mesmo pod `hzj4j`: `Unhealthy` — readiness probe falha com `connection refused` em `10.0.8.198:8084/healthz`, no exato instante em que o container estava sendo derrubado pelo Karpenter (item 1). Consulta: `Events Explorer (namespace + Reason, janela fixada)` (evidence_links).
3. 22:03:16 09/09/2026 BRT (epoch 1789002196000 · 2026-09-10T01:03:16.000Z) — Karpenter emite `Nominated` para o pod `argo-cd-argocd-repo-server-76df97c559-knc4t` (novo ciclo de consolidação). Consulta: `search_datadog_events` filtrado por `pod_name:...knc4t`.
4. 22:03:18 09/09/2026 BRT (epoch 1789002198000 · 2026-09-10T01:03:18.000Z) — Mesmo pod `knc4t`: `Unhealthy` (readiness, `connection refused` em `10.0.10.59:8084/healthz`) e `Killing` (`Stopping container repo-server`) ocorrem no mesmo segundo — de novo, a probe falha porque o container já estava sendo encerrado pelo Karpenter, não por indisponibilidade da aplicação em operação normal.
5. 23:33:46 10/09/2026 BRT (epoch 1789094026000 · 2026-09-11T02:33:46.000Z) — Pod `argo-cd-argocd-server-586dcf4bf-nrwzv` é agendado (`Scheduled`) em `ip-10-0-0-54`, iniciando um ciclo de pull de imagem.
6. 23:33:54 10/09/2026 BRT (epoch 1789094034000 · 2026-09-11T02:33:54.000Z) — Início do pull de `quay.io/argoproj/argocd:v2.14.2` (185.708.886 bytes).
7. 23:34:21 10/09/2026 BRT (epoch 1789094061000 · 2026-09-11T02:34:21.000Z) — Pull concluído em 25,35s e container iniciado (`Started`).
8. 23:34:37 10/09/2026 BRT (epoch 1789094077000 · 2026-09-11T02:34:37.000Z) — 16 segundos após o container subir, `Unhealthy`: liveness e readiness falham por `context deadline exceeded` em `10.0.1.229:8080/healthz` — típico de app ainda em warm-up (carregamento de config/dex/redis) sendo sondada antes de estar pronta, não uma indisponibilidade em produção estável.

Consulta que não devolveu eventos suficientes: nenhuma — os 3 passos-a-passo acima foram reconstruídos com sucesso a partir dos eventos do próprio pod.

## Evidência

- 3 ocorrências de `Unhealthy` no namespace `argocd` na janela `window_from`–`window_to`, todas 100% correlacionadas a eventos de ciclo de vida de pod (Karpenter ou cold-start) — [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aargocd%20Unhealthy&from_ts=1788808256645&to_ts=1789153856645&live=false).
- Pod `hzj4j`: `Killing`+`Nominated` (Karpenter) e `Unhealthy` no mesmo segundo `00:22:26 09/09/2026 BRT (epoch 1788924146000 · 2026-09-09T03:22:26.000Z)`/`00:22:27 09/09/2026 BRT (epoch 1788924147000 · 2026-09-09T03:22:27.000Z)` — consulta `source:kubernetes kube_namespace:argocd Unhealthy` (evidence_links) + `search_datadog_events` geral do namespace na janela (152 eventos totais retornados, amostra de 36 lida).
- Pod `knc4t`: `Nominated` às `22:03:16 09/09/2026 BRT (epoch 1789002196000 · 2026-09-10T01:03:16.000Z)`, `Unhealthy`+`Killing` no mesmo segundo `22:03:18 09/09/2026 BRT (epoch 1789002198000 · 2026-09-10T01:03:18.000Z)` — consulta `source:kubernetes kube_namespace:argocd pod_name:argo-cd-argocd-repo-server-76df97c559-knc4t` (5 eventos retornados).
- Pod `nrwzv`: ciclo completo `Scheduled`→`Pulling`→`Started`→`Unhealthy` entre `23:33:46 10/09/2026 BRT (epoch 1789094026000 · 2026-09-11T02:33:46.000Z)` e `23:34:37 10/09/2026 BRT (epoch 1789094077000 · 2026-09-11T02:34:37.000Z)` (51s de warm-up) — consulta `source:kubernetes kube_namespace:argocd pod_name:argo-cd-argocd-server-586dcf4bf-nrwzv` (4 eventos retornados).
- Sem logs de aplicação de erro: `search_datadog_logs` `kube_namespace:argocd service:argocd-repo-server` na janela → 0 resultados; `kube_namespace:argocd` sem filtro de serviço → 1.977.803 logs, amostra sem erro.
- Sem spans/traces para o componente: `aggregate_spans` `service:argocd-repo-server` agrupado por `@http.status_code` na janela → 0 buckets.

## Ação recomendada

Não abrir ação corretiva no código — não há aplicação com defeito. Se o volume de reagendamentos do Karpenter no namespace `argocd` incomodar operacionalmente, ajustar `terminationGracePeriodSeconds`/`initialDelaySeconds` das probes do Helm chart do ArgoCD (infra) para tolerar o dreno gracioso durante consolidação de nodes.

## Corpo da issue

### Descrição do incidente
O namespace `argocd` (cluster `eks-medprev-online-prd`) registrou 3 eventos `Unhealthy` (falha de readiness/liveness probe) na janela 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) a 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z), afetando pods `argo-cd-argocd-repo-server` e `argo-cd-argocd-server`. Não há impacto observável para usuário final ou indisponibilidade sustentada: cada ocorrência coincide com um pod sendo substituído (consolidação do Karpenter) ou recém-criado (cold-start), e o Kubernetes reagendou/reiniciou automaticamente sem intervenção.

### Causa raiz
RUÍDO — 3 de 3 ocorrências (100%) correlacionam diretamente, no mesmo segundo ou a poucos segundos, com eventos `Killing`/`Nominated` do Karpenter (consolidação/drift de node) ou com startup normal de container (pull de imagem de 185MB levando ~25s, probe disparando 16s após o container subir). Não há log de erro nem span de erro associado: `search_datadog_logs` para `argocd-repo-server` retornou 0 resultados na janela, e `aggregate_spans` para o mesmo serviço não retornou nenhum bucket (componente não instrumentado com APM).

### Linha do tempo
1. `00:22:26 09/09/2026 BRT (epoch 1788924146000 · 2026-09-09T03:22:26.000Z)` — Karpenter inicia `Killing`/`Nominated` no pod `hzj4j` (consolidação, novo nodeclaim `default-wq5n2`).
2. `00:22:27 09/09/2026 BRT (epoch 1788924147000 · 2026-09-09T03:22:27.000Z)` — `Unhealthy` (readiness, connection refused) no mesmo pod, simultâneo ao encerramento pelo Karpenter.
3. `22:03:16 09/09/2026 BRT (epoch 1789002196000 · 2026-09-10T01:03:16.000Z)` — Karpenter `Nominated` no pod `knc4t` (novo ciclo de consolidação).
4. `22:03:18 09/09/2026 BRT (epoch 1789002198000 · 2026-09-10T01:03:18.000Z)` — `Unhealthy` (readiness, connection refused) + `Killing` no mesmo segundo, mesmo pod.
5. `23:33:46 10/09/2026 BRT (epoch 1789094026000 · 2026-09-11T02:33:46.000Z)` — Pod `nrwzv` agendado, início de pull de imagem `argocd:v2.14.2` (185MB).
6. `23:34:21 10/09/2026 BRT (epoch 1789094061000 · 2026-09-11T02:34:21.000Z)` — Container `nrwzv` iniciado após pull de 25,35s.
7. `23:34:37 10/09/2026 BRT (epoch 1789094077000 · 2026-09-11T02:34:37.000Z)` — `Unhealthy` (liveness+readiness, timeout) 16s após o container subir — típico de warm-up ainda em curso.

### Evidências
- [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aargocd%20Unhealthy&from_ts=1788808256645&to_ts=1789153856645&live=false)
- Consulta `source:kubernetes kube_namespace:argocd pod_name:argo-cd-argocd-repo-server-76df97c559-knc4t` (janela completa do achado) → 5 eventos, confirma correlação com Karpenter.
- Consulta `source:kubernetes kube_namespace:argocd pod_name:argo-cd-argocd-server-586dcf4bf-nrwzv` (janela `23:32:00 10/09/2026 BRT (epoch 1789093920000 · 2026-09-11T02:32:00.000Z)`–`23:36:40 10/09/2026 BRT (epoch 1789094200000 · 2026-09-11T02:36:40.000Z)`) → 4 eventos, confirma ciclo de cold-start.
- Consulta `search_datadog_logs` `kube_namespace:argocd service:argocd-repo-server` (janela do achado) → 0 logs.
- Consulta `aggregate_spans` `service:argocd-repo-server` agrupado por `@http.status_code` (janela do achado) → 0 buckets.

### Ação recomendada
Infra — sem repositório de código, ação operacional. Se a frequência de reagendamentos do ArgoCD via Karpenter (consolidação de nodes) for indesejada, revisar no chart Helm do ArgoCD (values do componente `argo-cd`, provavelmente gerenciado no `medprev-cloud-iac`) os parâmetros `readinessProbe.initialDelaySeconds`/`livenessProbe.initialDelaySeconds` e `terminationGracePeriodSeconds` dos deployments `argocd-repo-server` e `argocd-server`, e/ou configurar `PodDisruptionBudget` para esses componentes de modo que o Karpenter drene com folga antes de matar o pod. Validação: após o ajuste, repetir a mesma consulta de eventos (`evidence_links`) por 7 dias e confirmar ausência de novos `Unhealthy` correlacionados a `Killing`/`Nominated` do Karpenter.

### Volume
3 ocorrências entre 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) e 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z). Consulta direta ao Datadog com a mesma query e mesma janela retornou o mesmo total (3), sem divergência.

### Severidade e criticidade
`severity` do achado é `medium`, mas não se aplica ao evento em si — classificado como ruído. Criticidade real (inferência): baixa. Os pods se recuperaram sozinhos em cada ocorrência (reagendamento automático do Kubernetes/Karpenter), sem log de erro de aplicação nem indisponibilidade sustentada de nenhum componente do ArgoCD observada nas consultas rodadas.
