---
fingerprint: k8s-eks-medprev-online-prd-Unhealthy-medprev-institucional-cms
source: kubernetes
reason: Unhealthy
novelty: new
service: medprev-institucional-cms
environment: production
window:
  from: 1788806810930
  to: 1789152410930
observed:
  count: 56
  first_seen: 1788840195000
  last_seen: 1789149724000
severity: medium
state: new
cost:
  input_tokens: 460210
  output_tokens: 9334
  cache_read_input_tokens: 354635
  cache_creation_input_tokens: 105565
  duration_s: 103.989
  usd: 0.591205
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-institucional-cms%20Unhealthy&from_ts=1788806810930&to_ts=1789152410930&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-institucional-cms%20Unhealthy&from_ts=1788806810930&to_ts=1789152410930&live=false

## Causa raiz

`medprev-institucional-cms` (Strapi CMS) trava no probe de inicialização: o kubelet mata o processo `strapi start` com SIGTERM antes de ele conseguir abrir a porta `1337`/`_health`, gerando os eventos `Unhealthy` — isso é **SINAL**, não ruído: os logs de aplicação do próprio serviço registram, no mesmo instante de cada evento, a sequência `npm error signal SIGTERM` → `npm error command sh -c strapi start` → `npm error command failed`, ou seja, o processo é interrompido de fora, não uma falha de negócio tratada pelo código. Não foi possível medir a divisão `handled`/`unhandled` via `aggregate_spans` porque o serviço não tem nenhum span de APM na janela (`aggregate_spans` retornou 0 buckets) — não há instrumentação de tracing para este serviço, então essa métrica específica fica como "não determinada", mas a evidência de log + eventos kubelet já basta para classificar como falha real.

O padrão está piorando dentro da própria janela de coleta: 4 ocorrências em 08/09, 7 em 09/09, 14 em 10/09 e 31 em 11/09 (agregação por dia, mesma janela do achado). A partir de 10/09 o sintoma também passa a atingir o **readiness probe**, não só o startup probe, indicando que o tempo de boot do Strapi está ficando mais lento ou mais instável ao longo do período. A versão do deployment (`0b8867e4`) permanece a mesma do início ao fim da janela — não há deploy novo correlacionado, então a causa não é uma regressão de código recém-publicada, e sim um startup probe (ou o próprio tempo de boot do Strapi) mal dimensionado para esse serviço.

## Linha do tempo

- 01:00:43 08/09/2026 BRT (epoch 1788840043000 · 2026-09-08T04:00:43.000Z) — rollout do Deployment `medprev-institucional-cms` (versão `0b8867e4`) inicia, `kube_condition_available:false`.
- 01:03:00 08/09/2026 BRT (epoch 1788840180000 · 2026-09-08T04:03:00.000Z) — log de aplicação do pod `-4kltm`: sequência `npm error signal SIGTERM` / `npm error command sh -c strapi start` / `npm error command failed` — o processo `strapi start` é encerrado à força.
- 01:03:15 08/09/2026 BRT (epoch 1788840195000 · 2026-09-08T04:03:15.000Z) — primeiro evento **Unhealthy** da janela: `Startup probe failed: dial tcp 10.0.3.128:1337: connect: connection refused` (pod `-4kltm`), consulta `source:kubernetes env:production status:warn kube_namespace:medprev-institucional-cms Unhealthy` — corresponde ao `first_seen` do achado: 01:03:15 08/09/2026 BRT (epoch 1788840195000 · 2026-09-08T04:03:15.000Z).
- 01:07:14 08/09/2026 BRT (epoch 1788840434000 · 2026-09-08T04:07:14.000Z) — rollout reporta `kube_condition_available:true` — pod finalmente sobe, mas repete o padrão em novos pods/rollouts adiante.
- 08/09: 4 ocorrências do dia (agregação diária, mesma query, mesma janela).
- 09/09: 7 ocorrências — pods `-mx4tm`, `-s54bk`, `-kk7pd`, mesmo padrão de `Startup probe failed` em `connection refused`.
- 09/09→10/09: 14 ocorrências — pods `-j5xh2`, `-l2mkc`, `-7j69w`, `-58k8h`, `-6dmxw`, `-fsrk5`, `-s9tg7`.
- 01:24:09 10/09/2026 BRT (epoch 1789014249000 · 2026-09-10T04:24:09.000Z) — primeira mudança de padrão: `Unhealthy: Readiness probe failed` (não mais só startup) no pod `-6dmxw` — sintoma passa a afetar também o probe de prontidão.
- 10/09→11/09: 31 ocorrências, o maior volume diário da janela — pods `-qpx8w`, `-c7lmn`, `-zqmp6`, mesma mensagem de `connection refused` na porta 1337.
- 15:02:04 11/09/2026 BRT (epoch 1789149724000 · 2026-09-11T18:02:04.000Z) — última ocorrência da janela, `last_seen` do achado: 15:02:04 11/09/2026 BRT (epoch 1789149724000 · 2026-09-11T18:02:04.000Z).
- Ao longo de toda a janela, a `version:0b8867e4` do Deployment não muda em nenhum dos ~49 eventos `source:change_tracking` capturados — os rollouts repetidos são reinícios da mesma versão, não deploys de código novo.

## Evidência

- 56 eventos `Unhealthy` entre 15:46:50 07/09/2026 BRT (epoch 1788806810930 · 2026-09-07T18:46:50.930Z) e 15:46:50 11/09/2026 BRT (epoch 1789152410930 · 2026-09-11T18:46:50.930Z): [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-institucional-cms%20Unhealthy&from_ts=1788806810930&to_ts=1789152410930&live=false).
- Distribuição diária das ocorrências (4 / 7 / 14 / 31, crescente) — `aggregate_events` com `query: "source:kubernetes env:production kube_namespace:medprev-institucional-cms Unhealthy"`, `group_by.interval: 86400000`, mesma janela acima.
- Todas as mensagens dos 56 eventos consultados são `Startup probe failed` (a maioria) ou, a partir de 10/09, `Readiness probe failed`, sempre `dial tcp <ip>:1337: connect: connection refused` — mesma query acima.
- Correlação de log de aplicação: `search_datadog_logs` com `service:medprev-institucional-cms env:production status:error "npm error"`, mesma janela — 120 logs retornados, todos do padrão `npm error path /usr/src/app` → `npm error command sh -c strapi start` → `npm error signal SIGTERM` → `npm error command failed`, com timestamps coincidindo (±15s) com os eventos `Unhealthy`.
- `analyze_datadog_logs`/`search_datadog_logs` com `use_log_patterns:true` sobre `status:(error OR warn)`: 8 padrões únicos no total, dominados por ruído de `npm notice`/`npm error`, sem nenhum log de aplicação (Strapi) fora do ciclo de boot — ou seja, o serviço nunca chega a rodar de fato antes de ser morto.
- `aggregate_spans` sobre `service:medprev-institucional-cms env:production`, mesma janela: **0 buckets** — nenhum span de APM. Consulta rodada, resultado vazio; não é possível medir `@error.handling` para este serviço.
- `search_datadog_events` com `source:change_tracking service:medprev-institucional-cms`, mesma janela: 49 eventos de rollout, todos com `version:0b8867e4` — nenhuma mudança de versão dentro da janela.

## Ação recomendada

Aumentar o `startupProbe.failureThreshold`/`periodSeconds` (ou `initialDelaySeconds`) do Deployment `medprev-institucional-cms` para dar tempo real de boot ao Strapi antes do kubelet enviar SIGTERM, e investigar por que o boot está ficando mais lento ao longo da semana (volume crescente de 4→31/dia).

## Corpo da issue

### Descrição do incidente
O serviço `medprev-institucional-cms` (Strapi CMS, cluster `eks-medprev-online-prd`) está em ciclo repetido de falha do probe de Kubernetes desde 2026-09-08: o kubelet mata o processo `strapi start` com SIGTERM antes de ele conseguir escutar na porta `1337` (`/_health`), gerando eventos `Unhealthy` que reiniciam o pod. O volume diário está crescendo (4→7→14→31 ocorrências/dia dentro da janela observada) e, a partir de 2026-09-10, o sintoma passou a atingir também o readiness probe, não só o startup probe — indicando piora progressiva do tempo de boot ou da estabilidade de inicialização. Impacto observável: reinícios frequentes de pods do CMS institucional, risco de indisponibilidade intermitente do serviço.

### Causa raiz
SINAL confirmado por log de aplicação (não há métrica handled/unhandled disponível: `aggregate_spans` no serviço retornou 0 buckets, sem instrumentação de APM). Os logs do próprio container mostram, no mesmo instante de cada evento `Unhealthy`, a sequência `npm error signal SIGTERM` → `npm error command sh -c strapi start` → `npm error command failed`: o processo é interrompido de fora antes de terminar o boot. A versão do Deployment (`0b8867e4`) não mudou em nenhum dos 49 eventos de rollout da janela, descartando deploy de código novo como causa; o problema é o dimensionamento do startup/readiness probe frente ao tempo real de boot do Strapi, que está piorando ao longo dos dias.

### Linha do tempo
- 2026-09-08 04:00:43 UTC — rollout do Deployment inicia (versão `0b8867e4`).
- 2026-09-08 04:03:00 UTC — log do pod `-4kltm`: `npm error signal SIGTERM` / `command sh -c strapi start` / `command failed`.
- 2026-09-08 04:03:15 UTC — primeiro evento `Unhealthy: Startup probe failed` da janela (= `first_seen` do achado).
- 08/09: 4 ocorrências; 09/09: 7; 10/09: 14; 11/09: 31 (agregação diária, mesma query).
- 2026-09-10 04:24:09 UTC — primeira ocorrência de `Readiness probe failed` (antes só era startup probe).
- 2026-09-11 18:02:04 UTC — última ocorrência da janela (= `last_seen` do achado).
- Ao longo de toda a janela: 49 eventos `source:change_tracking` de rollout, todos com `version:0b8867e4` — sem deploy de código novo.

### Evidências
- Events Explorer (todas as ocorrências `Unhealthy`, janela fixa): https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-institucional-cms%20Unhealthy&from_ts=1788806810930&to_ts=1789152410930&live=false
- Logs de aplicação (npm/strapi, correlação com os probes): consulta `service:medprev-institucional-cms env:production status:error "npm error"`, janela 1788806810930–1789152410930 — 120 logs, padrão `npm error signal SIGTERM`/`command failed`.
- Spans/APM: consulta `service:medprev-institucional-cms env:production`, `aggregate_spans` agrupado por `@error.handling`/`@http.status_code`, janela 1788806810930–1789152410930 — 0 buckets (sem instrumentação).
- Eventos de deploy: consulta `source:change_tracking service:medprev-institucional-cms`, mesma janela — 49 rollouts, versão `0b8867e4` constante.

### Ação recomendada
Repositório: `Medprev/medprev-institucional-cms`. Ajustar a configuração de `startupProbe` (e/ou `readinessProbe`) do Deployment/Helm chart do serviço — aumentar `failureThreshold` e/ou `periodSeconds`/`initialDelaySeconds` de forma que o tempo total tolerado cubra o boot real do Strapi antes de o kubelet enviar SIGTERM ao processo `strapi start`. Paralelamente, investigar no próprio processo Strapi (logs de boot, migrações, plugins carregados) por que o tempo de inicialização está aumentando dia a dia (4→31 ocorrências). Validar consultando novamente `source:kubernetes env:production status:warn kube_namespace:medprev-institucional-cms Unhealthy` numa janela equivalente após o ajuste e confirmando queda a zero (ou volume estável e baixo) nas 48h seguintes ao deploy da correção.

### Volume
56 ocorrências entre 15:46:50 07/09/2026 BRT (epoch 1788806810930 · 2026-09-07T18:46:50.930Z) e 15:46:50 11/09/2026 BRT (epoch 1789152410930 · 2026-09-11T18:46:50.930Z) — `observed_count` do achado, mesmo total confirmado pela consulta direta ao Events Explorer na mesma janela.

### Severidade e criticidade
`severity` do achado: `medium`. Avaliação de criticidade (inferência): o padrão é real e crescente (4→31/dia), e a partir de 10/09 já afeta o readiness probe — se a tendência continuar, o risco é de indisponibilidade intermitente do CMS institucional para leitura/edição de conteúdo, o que justifica tratar como prioridade média-alta antes que a taxa de falha do readiness comece a tirar pods de rotação de forma sustentada.
