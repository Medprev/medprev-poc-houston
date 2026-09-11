---
fingerprint: k8s-eks-medprev-online-prd-FailedDaemonPod-kube-system
source: kubernetes
reason: FailedDaemonPod
novelty: new
service: kube-system
environment: production
window:
  from: 1788722645625
  to: 1789068245625
observed:
  count: 391
  first_seen: 1788726612000
  last_seen: 1789037150000
severity: medium
state: discarded
cost:
  input_tokens: 303366
  output_tokens: 9860
  cache_read_input_tokens: 230205
  cache_creation_input_tokens: 73153
  duration_s: 82.65
  usd: 0.44189900000000004
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Akube-system%20FailedDaemonPod&from_ts=1788722645625&to_ts=1789068245625&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Akube-system%20FailedDaemonPod&from_ts=1788722645625&to_ts=1789068245625&live=false

## Causa raiz

O achado é do Kubernetes, namespace `kube-system`, cluster `eks-medprev-online-prd`, evento `FailedDaemonPod` — "Found failed daemon pod ..., will try to kill it", emitido pelo `daemonset-controller`. Consultando os eventos brutos da janela, o padrão não é específico do `eks-pod-identity-agent` citado em `sample_workload`: agregando por `kube_daemon_set` na mesma janela e query, os 391 eventos se distribuem quase igualmente entre **todos** os DaemonSets de `kube-system` — `aws-node` (81), `efs-csi-node` (81), `kube-proxy` (80), `ebs-csi-node` (79), `eks-pod-identity-agent` (70). Além disso, os eventos chegam em rajadas simultâneas por nó (ex.: todos os 5 DaemonSets do nó `ip-10-0-7-55.sa-east-1.compute.internal` falhando entre 17:30:12 06/09/2026 BRT (epoch 1788726612000 · 2026-09-06T20:30:12.000Z) e 17:30:13 06/09/2026 BRT (epoch 1788726613000 · 2026-09-06T20:30:13.000Z)), e toda tag carrega `karpenter_nodepool:default`. Isso é a assinatura de rotação de nó (o Karpenter substitui/recicla um nó, e o `daemonset-controller` mata os pods órfãos daquele nó antigo antes de recriá-los no novo) — comportamento de auto-cura esperado, não um erro de um componente específico.

Classificação: **provável RUÍDO**, mas não totalmente confirmada — não há campo `@error.handling`/`@http.status_code` aplicável a eventos Kubernetes (essa classificação vale para spans de erro, que este achado não gera), então a inferência é feita pela distribuição uniforme entre DaemonSets e pelo texto do próprio evento ("will try to kill it", ação de controle, não uma falha reportada por um workload). Tentei confirmar isso diretamente com um evento de término/substituição de nó: rodei `source:kubernetes env:production (@reason:NodeNotReady OR @reason:NotReady OR @reason:TerminatingEvictedPod OR karpenter_nodepool:*) status:info kube_node:ip-10-0-7-55.sa-east-1.compute.internal` na janela `1788722345625`–`1788723245625` (15 min ao redor da primeira rajada) e **o resultado voltou vazio** (`count: 0`) — não encontrei o evento de rotação do nó em si nessa janela estreita. Portanto: a causa mais provável é rotação/consolidação de nó pelo Karpenter, mas isso é inferência a partir do padrão observado, não uma correlação direta comprovada com um evento de término de nó.

Consultas efetivamente rodadas e o que devolveram:
- `search_datadog_events` com a query do achado, janela completa: 391 eventos, primeiro em 17:30:12 06/09/2026 BRT (epoch 1788726612000 · 2026-09-06T20:30:12.000Z).
- `aggregate_events` agrupado por `host` + intervalo diário: confirma 391 no total, concentrados em 2 hosts (`i-05d938105c83b3ba7`: 44+69+48+13; `i-07aa79ff3b225aa0a`: 119+98).
- `aggregate_events` agrupado por `kube_daemon_set`: distribuição quase uniforme entre os 5 DaemonSets (evidência contra causa específica de um único componente).
- `search_datadog_logs` para `eks-pod-identity-agent` na janela: 460 logs, mas nenhum é log de erro de aplicação — são apenas linhas de inicialização do processo (args/executable path), sem stack trace ou falha; não explicam a causa.
- `search_datadog_events` por evento de rotação de nó em janela estreita: vazio (0 resultados) — não determinei o evento exato de substituição do nó.

## Linha do tempo

1. 17:30:12 06/09/2026 BRT (epoch 1788726612000 · 2026-09-06T20:30:12.000Z) — primeiro `FailedDaemonPod` da janela: pod `kube-system/eks-pod-identity-agent-qpzpf` no nó `ip-10-0-7-55.sa-east-1.compute.internal` (query: `source:kubernetes env:production status:warn kube_namespace:kube-system FailedDaemonPod`).
2. 17:30:13 06/09/2026 BRT (epoch 1788726613000 · 2026-09-06T20:30:13.000Z) — no mesmo nó, falha em cascata dos demais DaemonSets: `efs-csi-node` (2 pods), `aws-node` (2 pods), `ebs-csi-node` (2 pods), `kube-proxy` (2 pods) — todos no intervalo de 1 segundo, mesma query.
3. 19:18:03 06/09/2026 BRT (epoch 1788733083000 · 2026-09-06T22:18:03.000Z)–19:18:04 06/09/2026 BRT (epoch 1788733084000 · 2026-09-06T22:18:04.000Z) — nova rajada, agora no nó `ip-10-0-5-245.sa-east-1.compute.internal`: `eks-pod-identity-agent`, `ebs-csi-node`, `aws-node`, `kube-proxy`, `efs-csi-node`.
4. 20:30:15 06/09/2026 BRT (epoch 1788737415000 · 2026-09-06T23:30:15.000Z)–20:30:16 06/09/2026 BRT (epoch 1788737416000 · 2026-09-06T23:30:16.000Z) — rajada no nó `ip-10-0-0-128.sa-east-1.compute.internal`, mesmos 5 DaemonSets.
5. 20:39:13 06/09/2026 BRT (epoch 1788737953000 · 2026-09-06T23:39:13.000Z)–20:39:14 06/09/2026 BRT (epoch 1788737954000 · 2026-09-06T23:39:14.000Z) — rajada no nó `ip-10-0-9-74.sa-east-1.compute.internal`, mesmos 5 DaemonSets.
6. 20:40:31 06/09/2026 BRT (epoch 1788738031000 · 2026-09-06T23:40:31.000Z)–20:40:33 06/09/2026 BRT (epoch 1788738033000 · 2026-09-06T23:40:33.000Z) — rajada no nó `ip-10-0-2-154.sa-east-1.compute.internal`, mesmos 5 DaemonSets.
7. Padrão se repete ao longo da janela (391 ocorrências no total entre 16:24:05 06/09/2026 BRT (epoch 1788722645625 · 2026-09-06T19:24:05.625Z) e 16:24:05 10/09/2026 BRT (epoch 1789068245625 · 2026-09-06T19:24:05.625Z), veja nota abaixo), concentrado em dois hosts segundo a agregação por dia (`i-05d938105c83b3ba7` até 09/09, `i-07aa79ff3b225aa0a` a partir de 09/09).
8. Não foi possível determinar o evento exato de substituição/término do nó que dispara cada rajada — a consulta dedicada a esse evento na janela em torno do primeiro passo voltou vazia.

Nota de correção: a string correta de `window_to` é 16:24:05 10/09/2026 BRT (epoch 1789068245625 · 2026-09-10T19:24:05.625Z) — repito aqui por completo conforme a regra de tempo.

## Evidência

- 391 ocorrências de `FailedDaemonPod` entre 16:24:05 06/09/2026 BRT (epoch 1788722645625 · 2026-09-06T19:24:05.625Z) e 16:24:05 10/09/2026 BRT (epoch 1789068245625 · 2026-09-10T19:24:05.625Z) — [Events Explorer](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Akube-system%20FailedDaemonPod&from_ts=1788722645625&to_ts=1789068245625&live=false).
- Distribuição por DaemonSet quase uniforme (`aws-node`:81, `efs-csi-node`:81, `kube-proxy`:80, `ebs-csi-node`:79, `eks-pod-identity-agent`:70) — consulta `aggregate_events`, mesma query do achado, `group_by: kube_daemon_set`, mesma janela.
- Concentração em 2 hosts por dia (`i-05d938105c83b3ba7`: 44/69/48/13 em 06–09/09; `i-07aa79ff3b225aa0a`: 119/98 em 09–10/09) — consulta `aggregate_events`, `group_by: host` + `interval: 86400000ms`, mesma janela.
- Todos os eventos carregam a tag `karpenter_nodepool:default`, indicando nós gerenciados pelo Karpenter — visível nos eventos retornados por `search_datadog_events` (mesma query).
- Logs do serviço `eks-pod-identity-agent` na janela (460 resultados) contêm apenas linhas de inicialização do binário, sem erro de aplicação — consulta `search_datadog_logs`: `kube_namespace:kube-system (eks-pod-identity-agent OR FailedDaemonPod) status:(warn OR error)`, janela do achado.
- Consulta por evento de rotação/término de nó no nó `ip-10-0-7-55...` em janela de 15 min ao redor da primeira rajada voltou vazia (0 resultados) — não há link pronto para esse dado específico; consulta exata: `source:kubernetes env:production (@reason:NodeNotReady OR @reason:NotReady OR @reason:TerminatingEvictedPod OR karpenter_nodepool:*) status:info kube_node:ip-10-0-7-55.sa-east-1.compute.internal`, de `1788722345625` a `1788723245625`.

## Ação recomendada

Não abrir issue de correção de código — não há `target_repo` (é infraestrutura) e a causa provável é rotação normal de nós pelo Karpenter. Ação operacional: no repositório de infraestrutura (Terraform/EKS), revisar a frequência de consolidação/rotação do `nodepool:default` do Karpenter e confirmar com o time de plataforma se o volume observado (~100/dia nos hosts mais recentes) é o esperado para o tamanho atual do cluster; se não for, ajustar `consolidationPolicy`/`disruption budgets` do NodePool.

## Corpo da issue

### Descrição do incidente
No cluster `eks-medprev-online-prd`, namespace `kube-system`, o evento `FailedDaemonPod` ocorreu 391 vezes entre 16:24:05 06/09/2026 BRT (epoch 1788722645625 · 2026-09-06T19:24:05.625Z) e 16:24:05 10/09/2026 BRT (epoch 1789068245625 · 2026-09-10T19:24:05.625Z), atingindo igualmente todos os DaemonSets de sistema (`aws-node`, `kube-proxy`, `ebs-csi-node`, `efs-csi-node`, `eks-pod-identity-agent`), sempre em rajadas simultâneas por nó. Não há impacto observável de indisponibilidade para usuários: o `daemonset-controller` mata e recria os pods automaticamente. O impacto observável é apenas volume de eventos/ruído no Error Tracking/Events Explorer.

### Causa raiz
Classificação: provável RUÍDO — os 391 eventos se distribuem quase uniformemente entre os 5 DaemonSets de `kube-system` (81/81/80/79/70), o que descarta falha de um componente específico e aponta para rotação de nó gerenciada pelo Karpenter (`karpenter_nodepool:default` em todas as tags). Causa raiz **não determinada com certeza**: uma consulta dedicada a um evento de término/substituição de nó na janela ao redor da primeira rajada não retornou resultado, então a hipótese de rotação de nó não foi confirmada por correlação direta, apenas por padrão estatístico.

### Linha do tempo
- 17:30:12 06/09/2026 BRT (epoch 1788726612000 · 2026-09-06T20:30:12.000Z)–17:30:13 06/09/2026 BRT (epoch 1788726613000 · 2026-09-06T20:30:13.000Z): primeira rajada, nó `ip-10-0-7-55.sa-east-1.compute.internal`, todos os 5 DaemonSets.
- 19:18:03 06/09/2026 BRT (epoch 1788733083000 · 2026-09-06T22:18:03.000Z)–19:18:04 06/09/2026 BRT (epoch 1788733084000 · 2026-09-06T22:18:04.000Z): rajada no nó `ip-10-0-5-245.sa-east-1.compute.internal`.
- 20:30:15 06/09/2026 BRT (epoch 1788737415000 · 2026-09-06T23:30:15.000Z)–20:30:16 06/09/2026 BRT (epoch 1788737416000 · 2026-09-06T23:30:16.000Z): rajada no nó `ip-10-0-0-128.sa-east-1.compute.internal`.
- 20:39:13 06/09/2026 BRT (epoch 1788737953000 · 2026-09-06T23:39:13.000Z)–20:39:14 06/09/2026 BRT (epoch 1788737954000 · 2026-09-06T23:39:14.000Z): rajada no nó `ip-10-0-9-74.sa-east-1.compute.internal`.
- 20:40:31 06/09/2026 BRT (epoch 1788738031000 · 2026-09-06T23:40:31.000Z)–20:40:33 06/09/2026 BRT (epoch 1788738033000 · 2026-09-06T23:40:33.000Z): rajada no nó `ip-10-0-2-154.sa-east-1.compute.internal`.
- Padrão contínuo até 07:45:50 10/09/2026 BRT (epoch 1789037150000 · 2026-09-10T10:45:50.000Z) (`last_seen` do histórico completo do achado, fora da janela de coleta), concentrado em 2 hosts diferentes por período (`i-05d938105c83b3ba7` até 09/09, `i-07aa79ff3b225aa0a` a partir de 09/09).
- Evento de rotação/término do nó não localizado na janela estreita consultada.

### Evidências
- [Events Explorer — 391 ocorrências, janela do achado](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Akube-system%20FailedDaemonPod&from_ts=1788722645625&to_ts=1789068245625&live=false)
- Query `aggregate_events` (`group_by: kube_daemon_set`, mesma janela): distribuição 81/81/80/79/70 entre os 5 DaemonSets.
- Query `aggregate_events` (`group_by: host`, intervalo diário): concentração em 2 hosts, 44/69/48/13 e 119/98 eventos/dia.
- Query `search_datadog_logs` (`kube_namespace:kube-system (eks-pod-identity-agent OR FailedDaemonPod) status:(warn OR error)`, janela do achado): 460 logs, nenhum de erro de aplicação.
- Query `search_datadog_events` (`kube_node:ip-10-0-7-55.sa-east-1.compute.internal`, `1788722345625`–`1788723245625`, buscando `NodeNotReady`/`NotReady`/`TerminatingEvictedPod`/`karpenter_nodepool`): 0 resultados.

### Ação recomendada
Infra — sem repositório de código, ação operacional. No repositório Terraform que provisiona o `eks-medprev-online-prd` (IaC do EKS/Karpenter), revisar a configuração do NodePool `default` (política de `consolidation`/disruption budgets) para confirmar se a taxa de rotação de nós observada (rajadas atingindo 5 DaemonSets por nó, ~100 eventos/dia nos hosts mais recentes) é a esperada. Validar a correção monitorando, por 48h após o ajuste, se o volume de `FailedDaemonPod` na mesma query cai proporcionalmente à redução na taxa de rotação de nós do NodePool.

### Volume
391 ocorrências na janela 16:24:05 06/09/2026 BRT (epoch 1788722645625 · 2026-09-06T19:24:05.625Z) a 16:24:05 10/09/2026 BRT (epoch 1789068245625 · 2026-09-10T19:24:05.625Z) — confirmado por consulta direta ao Events Explorer com a mesma query e mesma janela (mesmo total, sem divergência).

### Severidade e criticidade
A `severity: medium` do achado não se aplica ao evento `FailedDaemonPod` em si, dado que ele é RUÍDO provável (auto-cura esperada do controller). Inferência: a criticidade real, se a hipótese de rotação de nó do Karpenter se confirmar, é baixa — sem impacto a usuários ou dados, apenas custo de observabilidade (volume de eventos). Se a causa não for rotação de nó (não confirmado), a criticidade deve ser reavaliada após localizar o evento de origem correlacionado.
