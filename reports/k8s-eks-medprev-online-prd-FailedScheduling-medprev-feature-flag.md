---
fingerprint: k8s-eks-medprev-online-prd-FailedScheduling-medprev-feature-flag
source: kubernetes
reason: FailedScheduling
novelty: new
service: medprev-feature-flag
environment: production
window:
  from: 1788808256645
  to: 1789153856645
observed:
  count: 6
  first_seen: 1789003701000
  last_seen: 1789014857000
severity: medium
state: new
cost:
  input_tokens: 223041
  output_tokens: 9900
  cache_read_input_tokens: 146194
  cache_creation_input_tokens: 76841
  duration_s: 99.102
  usd: 0.4402788
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-feature-flag%20FailedScheduling&from_ts=1788808256645&to_ts=1789153856645&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-feature-flag%20FailedScheduling&from_ts=1788808256645&to_ts=1789153856645&live=false

## Causa raiz

O achado é um evento `FailedScheduling` do Kubernetes no namespace `medprev-feature-flag` (pod `medprev-feature-flag-flipt-*`, cluster `eks-medprev-online-prd`), reportado pelo `default-scheduler`. Consultando o Events Explorer com a própria query do achado (`source:kubernetes env:production status:warn kube_namespace:medprev-feature-flag FailedScheduling`, janela 07/09 16:10:56 BRT a 11/09 16:10:56 BRT) obtive exatamente 6 eventos — o mesmo `observed_count`. Ampliando a busca para todos os eventos do namespace ao redor de `first_seen`/`last_seen` (07:00 a 11:00 UTC de 10/09), reconstruí dois episódios completos e idênticos em forma: Karpenter mata o pod antigo, indica (`Nominated`) o novo node/nodeclaim, o `ReplicaSet` cria o pod substituto, o `default-scheduler` emite 2–3 `FailedScheduling` (0/11–0/13 nodes disponíveis por CPU/memória/taint insuficientes) enquanto o novo node ainda não existe, e ~51–53s depois o pod é `Scheduled`, a imagem é puxada e o container inicia — sem `CrashLoopBackOff`, `OOMKilled` ou qualquer outro evento de falha do pod em nenhum dos dois episódios.

Classificação: **ruído para o evento `FailedScheduling` em si** — é o comportamento esperado do ciclo de substituição de node do Karpenter (retry automático do scheduler até o novo node ficar pronto), não uma falha de aplicação. Não consigo aplicar a métrica `handled`/`unhandled` porque `aggregate_spans` para `service:medprev-feature-flag` na janela do achado devolveu **0 buckets** (nenhum span/trace de APM existe para esse serviço) e `search_datadog_logs` para `service:medprev-feature-flag env:production` na janela `first_seen`–`last_seen` devolveu **0 logs** — o Flipt aqui roda como imagem de terceiro (`docker.flipt.io/flipt/flipt:v1.50.0`) sem instrumentação de APM/logging integrada ao Datadog, então não há telemetria de aplicação para classificar o erro por esse eixo; a classificação acima se apoia inteiramente no trace de eventos do Kubernetes.

O que a investigação encontra de fato relevante é outro problema, correlacionado no trace de eventos: em ambos os episódios o pod `flipt` roda como **réplica única** — não há um segundo pod `Ready` durante a janela de retry — e o cluster não tem capacidade de node sobressalente pronta (o scheduler precisa esperar o Karpenter provisionar um node novo do zero, ~51–53s, antes de conseguir agendar o substituto). Isso é uma janela real de indisponibilidade do serviço `medprev-feature-flag`, não o evento `FailedScheduling` reportado.

## Linha do tempo

**Episódio 1 — pod `medprev-feature-flag-flipt-5bcdcc6946-l7c64`:**
1. 22:28:20 09/09/2026 BRT (epoch 1789003700000 · 2026-09-10T01:28:20.000Z) Karpenter: `Killing` — parando o container `flipt` do pod antigo; `Nominated` — pod deve agendar em `nodeclaim/default-qnmn8`, node `ip-10-0-0-200...` (consulta: evento kubernetes no namespace, `kube_name:...-l7c64`).
2. 22:28:21 09/09/2026 BRT (epoch 1789003701000 · 2026-09-10T01:28:21.000Z) ReplicaSet `medprev-feature-flag-flipt-5bcdcc6946`: `SuccessfulCreate` do pod `l7c64`.
3. 22:28:21 09/09/2026 BRT (epoch 1789003701000 · 2026-09-10T01:28:21.000Z) `default-scheduler`: `FailedScheduling` — 0/11 nodes disponíveis (1 memória insuficiente, 3 com taint não tolerado, 8 CPU insuficiente) — este é o `first_seen` do achado.
4. 22:28:22 09/09/2026 BRT (epoch 1789003702000 · 2026-09-10T01:28:22.000Z) Karpenter: `Nominated` — pod deve agendar em `nodeclaim/default-qnmn8`.
5. 22:28:46 09/09/2026 BRT (epoch 1789003726000 · 2026-09-10T01:28:46.000Z) `default-scheduler`: dois `FailedScheduling` no mesmo evento — 0/11 e depois 0/12 nodes disponíveis (novo node ainda provisionando).
6. 22:29:07 09/09/2026 BRT (epoch 1789003747000 · 2026-09-10T01:29:07.000Z) `taint-eviction-controller`: `TaintManagerEviction` — cancela a remoção do pod `l7c64` (node já apto).
7. 22:29:13 09/09/2026 BRT (epoch 1789003753000 · 2026-09-10T01:29:13.000Z) `default-scheduler`: `Scheduled` com sucesso em `ip-10-0-1-40`; imagem `flipt:v1.50.0` puxada em 6.508s; container `Created`/`Started`.

**Episódio 2 — pod `medprev-feature-flag-flipt-5bcdcc6946-q9wx6`:**
8. 01:33:51 10/09/2026 BRT (epoch 1789014831000 · 2026-09-10T04:33:51.000Z) Karpenter: `Killing` do container `flipt` antigo; `Nominated` — schedule em `nodeclaim/default-8hnd4`, node `ip-10-0-11-130...`.
9. 01:33:52 10/09/2026 BRT (epoch 1789014832000 · 2026-09-10T04:33:52.000Z) ReplicaSet: `SuccessfulCreate` do pod `q9wx6`; `default-scheduler`: `FailedScheduling` — 0/12 nodes disponíveis.
10. 01:33:53 10/09/2026 BRT (epoch 1789014833000 · 2026-09-10T04:33:53.000Z) Karpenter: `Nominated` — `nodeclaim/default-8tfmv`.
11. 01:34:17 10/09/2026 BRT (epoch 1789014857000 · 2026-09-10T04:34:17.000Z) `default-scheduler`: dois `FailedScheduling` no mesmo evento — 0/12 e depois 0/13 nodes disponíveis — este é o `last_seen` do achado.
12. 01:34:35 10/09/2026 BRT (epoch 1789014875000 · 2026-09-10T04:34:35.000Z) `taint-eviction-controller`: `TaintManagerEviction` — cancela remoção do pod `q9wx6`.
13. 01:34:42 10/09/2026 BRT (epoch 1789014882000 · 2026-09-10T04:34:42.000Z) `default-scheduler`: `Scheduled` com sucesso em `ip-10-0-1-39`; imagem puxada em 5.946s; container `Created`/`Started`.

Cada episódio dura ~51–53s do `Killing` inicial ao `Started` final, sem eventos de falha do pod entre os dois marcos.

## Evidência

- 6 eventos `FailedScheduling` no namespace `medprev-feature-flag`, janela 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) a 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z) — https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-feature-flag%20FailedScheduling&from_ts=1788808256645&to_ts=1789153856645&live=false
- Reconstrução completa dos dois episódios (16 eventos: `Killing`, `Nominated`, `SuccessfulCreate`, `FailedScheduling`, `TaintManagerEviction`, `Scheduled`/`Pulled`/`Created`/`Started`) — consulta: `source:kubernetes kube_namespace:medprev-feature-flag`, de 01:26:40 10/09/2026 BRT (epoch 1789014400000 · 2026-09-10T04:26:40.000Z) a 01:36:40 10/09/2026 BRT (epoch 1789015000000 · 2026-09-10T04:36:40.000Z) (não há `evidence_link` pronto para esta consulta ampliada; é a mesma janela do namespace, sem o filtro `FailedScheduling`).
- Nenhum log de aplicação indexado: `service:medprev-feature-flag env:production`, 22:28:21 09/09/2026 BRT a 01:34:17 10/09/2026 BRT — 0 resultados.
- Nenhum span de APM: `aggregate_spans` com `query: service:medprev-feature-flag`, mesma janela do achado (`window_from`–`window_to`) — 0 buckets, portanto o par `@error.handling`/`@http.status_code` não pôde ser computado.
- Ambos os episódios se resolveram por conta própria em ~51–53s (Karpenter provisionando node novo), sem `CrashLoopBackOff` ou `OOMKilled` no trace de eventos.

## Ação recomendada
Tratar o `FailedScheduling` em si como ruído (não abrir ação de correção de código para ele); investigar/mitigar a janela real de indisponibilidade de ~51–53s por réplica única durante substituição de node do Karpenter.

## Corpo da issue

### Descrição do incidente
O serviço `medprev-feature-flag` (componente `flipt`, namespace `medprev-feature-flag`, cluster `eks-medprev-online-prd`) roda como pod único (réplica=1). Duas vezes em 2026-09-10 (madrugada), o Karpenter substituiu o node que hospedava esse pod (drift/consolidação), e o pod substituto ficou ~51–53s sem conseguir ser agendado (`FailedScheduling`) porque não havia node com capacidade livre — o Karpenter precisou provisionar um node novo do zero. Nesses ~51–53s não havia nenhuma réplica `Ready` do `flipt`, o que é indisponibilidade real do serviço, ainda que curta.

### Causa raiz
Ruído para o evento em si: 6/6 ocorrências de `FailedScheduling` no achado fazem parte do ciclo normal de substituição de node do Karpenter (retry do scheduler até o node novo ficar pronto), resolvendo-se sozinhas em ambos os episódios sem falha de pod. Causa raiz do defeito real (indisponibilidade transitória) **não determinada com certeza absoluta, mas fortemente indicada pelas evidências**: réplica única do `flipt` sem capacidade de node de reserva, então cada substituição de node do Karpenter gera uma janela sem pod pronto. Não há telemetria de aplicação (0 logs, 0 spans) para confirmar impacto no consumidor do serviço durante essa janela.

### Linha do tempo
Ver `## Linha do tempo` acima — dois episódios idênticos (pods `l7c64` em 22:28:20 09/09/2026 BRT (epoch 1789003700000 · 2026-09-10T01:28:20.000Z)–22:29:13 09/09/2026 BRT (epoch 1789003753000 · 2026-09-10T01:29:13.000Z) e `q9wx6` em 01:33:51 10/09/2026 BRT (epoch 1789014831000 · 2026-09-10T04:33:51.000Z)–01:34:42 10/09/2026 BRT (epoch 1789014882000 · 2026-09-10T04:34:42.000Z)), cada um: Karpenter mata pod antigo → `FailedScheduling` (2–3x) enquanto novo node sobe → `Scheduled`/`Started` em ~51–53s.

### Evidências
- Events Explorer, `FailedScheduling` no namespace (janela do achado): https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-feature-flag%20FailedScheduling&from_ts=1788808256645&to_ts=1789153856645&live=false
- Consulta ampliada (sem filtro `FailedScheduling`) que reconstruiu os 16 eventos dos dois episódios: `source:kubernetes kube_namespace:medprev-feature-flag`, 01:26:40 10/09/2026 BRT (epoch 1789014400000 · 2026-09-10T04:26:40.000Z)–01:36:40 10/09/2026 BRT (epoch 1789015000000 · 2026-09-10T04:36:40.000Z).
- `service:medprev-feature-flag env:production`, 2026-09-09T22:28:21 (BRT) a 2026-09-10T01:34:17 (BRT) → 0 logs.
- `aggregate_spans query:service:medprev-feature-flag`, janela do achado → 0 buckets (sem APM).

### Ação recomendada
Repositório: `Medprev/medprev-feature-flag` (deployment do `flipt`, `values`/manifesto do Helm/Kustomize que define `replicas`). Ação concreta: (1) aumentar `replicas` do deployment `medprev-feature-flag-flipt` de 1 para 2+ para que sempre exista uma réplica `Ready` durante substituição de node; (2) adicionar um `PodDisruptionBudget` (`minAvailable: 1`) para o mesmo deployment; (3), se a IaC permitir (repo de infra, fora do escopo deste `target_repo`), avaliar `do-not-disrupt`/buffer de capacidade no nodepool do Karpenter para reduzir o tempo de provisionamento de node novo. Validação: após o deploy, provocar (ou aguardar) uma nova substituição de node do Karpenter e confirmar via Events Explorer que não há mais janela sem pod `Ready` do `flipt` (`kubectl get pods -n medprev-feature-flag -w` durante o drift, ou `@kube_replica_set` com 0 pods `Ready` na aba de métricas de infraestrutura).

### Volume
6 ocorrências entre 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) e 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z) — coincide com a contagem obtida na consulta direta ao Datadog na mesma janela.

### Severidade e criticidade
`severity` do achado: `medium` — mas essa severidade não se aplica ao evento `FailedScheduling` em si, classificado como ruído. Criticidade do defeito real encontrado (réplica única + janela de indisponibilidade de ~51–53s a cada substituição de node): **inferência minha**, não dado direto do achado — considero criticidade baixa-a-média para o negócio: impacto limitado a requisições de feature-flag durante uma janela curta e pouco frequente (2 ocorrências em ~3h dentro de uma janela de 4 dias), mas potencialmente maior se `medprev-feature-flag` for consultado de forma síncrona e bloqueante por outros serviços críticos — isso não foi possível confirmar pela ausência de logs/spans de aplicação.
