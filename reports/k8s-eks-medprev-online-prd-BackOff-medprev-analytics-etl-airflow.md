---
fingerprint: k8s-eks-medprev-online-prd-BackOff-medprev-analytics-etl-airflow
source: kubernetes
reason: BackOff
novelty: new
service: medprev-analytics-etl-airflow
environment: production
window:
  from: 1788808256645
  to: 1789153856645
observed:
  count: 3
  first_seen: 1788954694000
  last_seen: 1788954805000
severity: medium
state: new
cost:
  input_tokens: 646636
  output_tokens: 9368
  cache_read_input_tokens: 576842
  cache_creation_input_tokens: 69778
  duration_s: 108.466
  usd: 0.49285940000000006
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-analytics-etl-airflow%20BackOff&from_ts=1788808256645&to_ts=1789153856645&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-analytics-etl-airflow%20BackOff&from_ts=1788808256645&to_ts=1789153856645&live=false

Empty — no other message types exist in that window beyond the ones already enumerated. Vou fechar a investigação com o que foi apurado.

## Causa raiz

O achado é do namespace `medprev-analytics-etl-airflow` (cluster `eks-medprev-online-prd`), reason `BackOff` — não é o serviço de aplicação em si, mas o container sidecar `git-sync` (que sincroniza DAGs do Airflow a partir de um repositório git) entrando em `CrashLoopBackOff` nos pods `medprev-analytics-etl-airflow-main-triggerer-0` e `medprev-analytics-etl-airflow-main-dag-processor-56668c4f5p2v62`. Não há spans APM para `service:medprev-analytics-etl-airflow` na janela consultada (`aggregate_spans` retornou 0 buckets), então a classificação `handled`/`unhandled` de erro tracing não se aplica aqui — este achado é de evento de infraestrutura Kubernetes, não de exceção de aplicação instrumentada. Pela contagem de logs do próprio `git-sync`, a mensagem terminal `too many failures, aborting` aparece de forma repetida (2 ocorrências na janela estreita de 11:51:00–11:51:40 UTC, mais recorrências em outras janelas do host) intercalada com ciclos completos de reinício bem-sucedido (`starting up` → `updated successfully`), o que indica **sinal real de instabilidade**, não ruído: o container está de fato falhando e se recuperando em loop, consumindo restarts.

Causa raiz exata do porquê o `git-sync` acumula falhas (autenticação, rede, rate limit do provedor git, etc.) **não determinada** pelas evidências consultadas — o `git-sync` não expõe, nos logs coletados, a mensagem de erro individual de cada tentativa fracassada, apenas o agregado `too many failures, aborting` após esgotar as tentativas internas. Consultas efetivamente rodadas:
- Logs `container_name:git-sync ... (error* OR fail* OR fatal*)` excluindo avisos de depreciação, janela 11:50:00–11:51:40 UTC → só devolveu as duas ocorrências de `too many failures, aborting`.
- Logs sem filtro de status, mesma janela, excluindo depreciação → devolveu 10 registros: o ciclo completo de restart (`detected pid 1` → `starting up` → `git version 2.39.5` → `serving HTTP` → `update required` → `updated successfully`) intercalado entre as duas mensagens de falha — nenhuma linha nomeia a causa da falha individual.
- Logs excluindo todas as mensagens já vistas, janela ampliada para 1788950000000–1788954700000 → 0 resultados (vazio: confirma que não há mensagem de erro adicional de nível mais granular indexada para esse container/pod na janela).
- `aggregate_spans` para `service:medprev-analytics-etl-airflow` na janela do achado → 0 buckets (sem spans APM, componente não instrumentado/sem service map de traces).
- `aggregate_events` agrupando por `kube_reason` no mesmo namespace/janela → 0 buckets (facet não populado dessa forma nesse index de eventos).

## Linha do tempo

- 08:51:05 09/09/2026 BRT (epoch 1788954665000 · 2026-09-09T11:51:05.000Z) — `git-sync` no pod `medprev-analytics-etl-airflow-main-triggerer-0` registra `too many failures, aborting` (log `service:git-sync`, `status:error`, host `i-07aa79ff3b225aa0a`).
- 08:51:11 09/09/2026 BRT (epoch 1788954671000 · 2026-09-09T11:51:11.000Z) — container reinicia: `detected pid 1, running init handler` → `starting up` (versão `v4.4.2`, `git version 2.39.5`) → `serving HTTP` → `update required` → `updated successfully` (mesmo pod/host).
- 08:51:34 09/09/2026 BRT (epoch 1788954694000 · 2026-09-09T11:51:34.000Z) — Kubelet emite o evento `BackOff`: "Back-off restarting failed container git-sync in pod medprev-analytics-etl-airflow-main-triggerer-0" (primeira ocorrência do achado, `first_seen`: 08:51:34 09/09/2026 BRT (epoch 1788954694000 · 2026-09-09T11:51:34.000Z)). No mesmo instante, o log do `git-sync` volta a registrar `too many failures, aborting`.
- 08:52:57 09/09/2026 BRT (epoch 1788954777000 · 2026-09-09T11:52:57.000Z) — segundo evento `BackOff`, desta vez no pod `medprev-analytics-etl-airflow-main-dag-processor-56668c4f5p2v62`, mesmo container `git-sync`, mesma mensagem de kubelet.
- 08:53:25 09/09/2026 BRT (epoch 1788954805000 · 2026-09-09T11:53:25.000Z) — terceiro evento `BackOff`, novamente no pod `medprev-analytics-etl-airflow-main-triggerer-0` — coincide com `last_seen`: 08:53:25 09/09/2026 BRT (epoch 1788954805000 · 2026-09-09T11:53:25.000Z).

Todas as 3 ocorrências do achado (`observed_count: 3`) caem dentro de ~2 minutos, entre `first_seen` e `last_seen` acima, e dentro da janela de coleta window_from: 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) e window_to: 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z).

## Evidência

- 3 eventos Kubernetes `BackOff` no namespace `medprev-analytics-etl-airflow`, todos com container `git-sync`, entre 11:51:34Z e 11:53:25Z de 09/09/2026 — [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-analytics-etl-airflow%20BackOff&from_ts=1788808256645&to_ts=1789153856645&live=false).
- Logs `service:git-sync` com a mensagem terminal `too many failures, aborting` no mesmo host/pod, coincidindo com os dois primeiros eventos `BackOff` — consulta: `kube_namespace:medprev-analytics-etl-airflow container_name:git-sync pod_name:medprev-analytics-etl-airflow-main-triggerer-0 (error* OR fail* OR fatal*) -message:"has been deprecated" -message:"was overridden"`, janela 1788954000000–1788954700000 → 2 registros.
- Ciclo completo de reinício do `git-sync` (versão `v4.4.2`, git `2.39.5`) entre as duas falhas, incluindo um `updated successfully` — consulta: mesma acima sem filtro de error/fail, janela 1788953700000–1788954700000 → 10 registros.
- Nenhuma mensagem de erro adicional/mais granular do `git-sync` na janela ampliada — consulta excluindo todas as mensagens já identificadas, janela 1788950000000–1788954700000 → 0 registros (vazio).
- Sem spans APM para `service:medprev-analytics-etl-airflow` na janela do achado — `aggregate_spans` query `service:medprev-analytics-etl-airflow`, from 1788808256645 to 1789153856645 → 0 buckets.
- 232 logs com `status:error` para `container_name:git-sync` na janela total do achado, mas a amostra inspecionada mostrou que a maioria são avisos de depreciação de variável de ambiente (`env $X has been deprecated`), não falhas reais — consulta: `kube_namespace:medprev-analytics-etl-airflow container_name:git-sync status:error`, janela completa do achado → 232 registros, primeiros 5 inspecionados eram depreciação.

## Ação recomendada

Como `target_repo` é nulo (componente de infraestrutura sem repositório de código próprio), a ação é operacional: revisar a configuração do sidecar `git-sync` do Airflow (Helm values/manifesto do deploy `medprev-analytics-etl-airflow`) quanto a credenciais/URL do repositório git e timeouts, e correlacionar com logs de rede do nó `ip-10-0-8-39` no mesmo intervalo, já que os logs indexados do `git-sync` não expõem a causa granular de cada tentativa fracassada.

## Corpo da issue

### Descrição do incidente
O container sidecar `git-sync` (sincronização de DAGs) dos pods `medprev-analytics-etl-airflow-main-triggerer-0` e `medprev-analytics-etl-airflow-main-dag-processor-*`, no namespace `medprev-analytics-etl-airflow` (cluster `eks-medprev-online-prd`), entrou em `CrashLoopBackOff` por volta de 08:51:34 09/09/2026 BRT (epoch 1788954694000 · 2026-09-09T11:51:34.000Z), com reinícios sucessivos em menos de 2 minutos. Impacto observável: risco de atraso na sincronização de DAGs do Airflow enquanto o sidecar reinicia repetidamente, ainda que o processo tenha se recuperado sozinho em cada ciclo (`updated successfully` registrado após cada restart).

### Causa raiz
Sinal real, não ruído: o próprio `git-sync` registra a mensagem terminal `too many failures, aborting` duas vezes na janela de ~30s analisada, intercalada com um ciclo completo de reinício bem-sucedido — não é uma exceção de negócio tratada, é uma falha de sincronização que esgota as tentativas internas do binário. Causa granular (autenticação, rede, rate limit do host git) **não determinada**: os logs indexados do `git-sync` não incluem a mensagem de erro de cada tentativa individual antes de "too many failures, aborting", e uma busca mais ampla (janela 1788950000000–1788954700000) não retornou nenhuma mensagem adicional.

### Linha do tempo
- 08:51:05 09/09/2026 BRT (epoch 1788954665000 · 2026-09-09T11:51:05.000Z) — `git-sync` registra `too many failures, aborting` no pod `triggerer-0`.
- 08:51:11 09/09/2026 BRT (epoch 1788954671000 · 2026-09-09T11:51:11.000Z) — container reinicia e completa um ciclo `starting up` → `updated successfully`.
- 08:51:34 09/09/2026 BRT (epoch 1788954694000 · 2026-09-09T11:51:34.000Z) — evento Kubelet `BackOff` no pod `triggerer-0`; log do `git-sync` repete `too many failures, aborting` no mesmo instante.
- 08:52:57 09/09/2026 BRT (epoch 1788954777000 · 2026-09-09T11:52:57.000Z) — evento `BackOff` no pod `main-dag-processor-56668c4f5p2v62`, mesmo container.
- 08:53:25 09/09/2026 BRT (epoch 1788954805000 · 2026-09-09T11:53:25.000Z) — evento `BackOff` no pod `triggerer-0` (coincide com `last_seen` do achado).

### Evidências
- Events Explorer (3 eventos BackOff, janela fixada): https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-analytics-etl-airflow%20BackOff&from_ts=1788808256645&to_ts=1789153856645&live=false
- Consulta de logs (falha terminal do git-sync): `kube_namespace:medprev-analytics-etl-airflow container_name:git-sync pod_name:medprev-analytics-etl-airflow-main-triggerer-0 (error* OR fail* OR fatal*) -message:"has been deprecated" -message:"was overridden"`, 1788954000000–1788954700000 → 2 registros.
- Consulta de logs (ciclo de restart completo): mesma query sem filtro error/fail, 1788953700000–1788954700000 → 10 registros.
- Consulta de logs (busca ampliada, nenhum erro adicional): exclui todas as mensagens já vistas, 1788950000000–1788954700000 → 0 registros.
- `aggregate_spans` `service:medprev-analytics-etl-airflow`, janela completa do achado → 0 buckets (sem instrumentação APM).

### Ação recomendada
Infra — sem repositório de código, ação operacional: revisar no manifesto/Helm chart de deploy do Airflow (`medprev-analytics-etl-airflow`) a configuração do container `git-sync` — variáveis `GITSYNC_REPO`/`GIT_SYNC_REPO` (ambas presentes e conflitantes nos logs, uma delas sobrescrevendo a outra — sinal de manifesto usando nomenclatura antiga e nova da mesma env var), credenciais/chave SSH e timeout de sync. Validar a correção observando, na mesma query de eventos usada aqui (`source:kubernetes env:production status:warn kube_namespace:medprev-analytics-etl-airflow BackOff`), ausência de novos eventos `BackOff` para `git-sync` por pelo menos um ciclo completo de sincronização de DAGs (recomendado: 24h).

### Volume
3 ocorrências entre window_from: 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) e window_to: 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z) (`observed_count`). Não foi feita consulta com janela ou filtro diferente para o total de eventos BackOff.

### Severidade e criticidade
`severity` do achado: `medium`. Criticidade para o negócio (inferência): moderada — um sidecar de sincronização de DAGs em CrashLoopBackOff intermitente, mas que se recupera sozinho a cada ciclo, tende a causar atraso na propagação de novas DAGs/alterações no Airflow, não indisponibilidade total do serviço; risco maior se a taxa de falha aumentar ao ponto de o sync nunca completar com sucesso.
