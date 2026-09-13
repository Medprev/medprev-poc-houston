---
fingerprint: k8s-eks-medprev-online-prd-FailedScheduling-medprev-institucional-cms
source: kubernetes
reason: FailedScheduling
novelty: new
service: medprev-institucional-cms
environment: production
window:
  from: 1788808256645
  to: 1789153856645
observed:
  count: 3
  first_seen: 1788840030000
  last_seen: 1788840057000
severity: medium
state: new
cost:
  input_tokens: 314186
  output_tokens: 9517
  cache_read_input_tokens: 229866
  cache_creation_input_tokens: 84312
  duration_s: 105.426
  usd: 0.48308219999999996
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-institucional-cms%20FailedScheduling&from_ts=1788808256645&to_ts=1789153856645&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-institucional-cms%20FailedScheduling&from_ts=1788808256645&to_ts=1789153856645&live=false

## Causa raiz

O achado é do namespace Kubernetes `medprev-institucional-cms`, cluster `eks-medprev-online-prd`, e reflete falhas transitórias de agendamento (`FailedScheduling`) de um único pod (`medprev-institucional-cms-7c467869f9-4kltm`) durante um redeploy automatizado (ArgoCD/Helm) que ocorre diariamente por volta das 04:00 UTC. Consultando o evento `source:change_tracking` do mesmo namespace, o deploy do dia começou em `01:00:29 08/09/2026 BRT (epoch 1788840029000 · 2026-09-08T04:00:29.000Z)` (`kube_condition_available:false`); os três eventos `FailedScheduling` do achado ocorreram em `01:00:30 08/09/2026 BRT (epoch 1788840030000 · 2026-09-08T04:00:30.000Z)`, `01:00:57 08/09/2026 BRT (epoch 1788840057000 · 2026-09-08T04:00:57.000Z)` e `01:00:57 08/09/2026 BRT (epoch 1788840057000 · 2026-09-08T04:00:57.000Z)` (mesmo segundo, dois nós diferentes tentados), todos com a mesma mensagem: `0 Insufficient cpu`/`Insufficient memory`/`untolerated taint(s)`/`topology spread constraints` — ou seja, no instante do deploy não havia node com capacidade livre nos ~10-11 nodes do pool, e a preempção também não achou vítimas. Os logs de aplicação do serviço confirmam autorrecuperação: a própria aplicação (Strapi CMS) subiu e imprimiu seu banner de start ("Welcome back!") em `01:03:22 08/09/2026 BRT (epoch 1788840202000 · 2026-09-08T04:03:22.000Z)`, e o evento de deployment marcou `kube_condition_available:true` em `01:07:14 08/09/2026 BRT (epoch 1788840434000 · 2026-09-08T04:07:14.000Z)` — recuperação completa em menos de 7 minutos, sem intervenção humana (provável provisionamento de novo node pelo Karpenter, `karpenter_nodepool:default`).

Classificação: não há classificação `handled`/`unhandled` aplicável aqui — essa dimensão é exclusiva de Error Tracking (spans de exceção), e este achado é `source:kubernetes`. Como proxy de impacto real, consultei spans de APM do serviço na mesma janela (`aggregate_spans`, query `service:medprev-institucional-cms env:production`, agrupado por `@http.status_code`): **0 buckets retornados** — o serviço não tem spans de APM na janela (sem instrumentação de tracing, ou nenhuma requisição instrumentada), portanto não há como provar impacto em requisições reais a partir de traces. Também busquei logs do serviço na janela completa (`service:medprev-institucional-cms env:production`): **762 logs no total**, dos quais **240 com `status:error`** — mas a única amostra de erro retornada (linha `npm error ... /root/.npm/_logs/...`) é de um evento em `15:02:30 11/09/2026 BRT (epoch 1789149750000 · 2026-09-11T18:02:30.000Z)`, fora da janela do incidente e sem relação aparente com o scheduling (parece ruído de build/init container, não da aplicação em si).

Isto é **sinal fraco/ruído operacional autolimitado**: o evento é real (3 tentativas de agendamento falharam por falta momentânea de capacidade), mas o próprio sistema (Karpenter + Kubernetes) se recuperou sozinho em ~7 minutos sem downtime aparente (a aplicação chegou a subir em ~3 minutos). Não há evidência, nas consultas feitas, de impacto em usuários (sem spans, sem logs de erro de aplicação correlacionados ao horário). O padrão de deploy diário às 04:00 se repete em 07, 08, 09, 10 e 11/09 (56 eventos `change_tracking` no total), mas o `FailedScheduling` só ocorreu na noite de 08/09 — não é recorrente na janela do achado, é um evento isolado.

## Linha do tempo

1. `01:00:29 08/09/2026 BRT (epoch 1788840029000 · 2026-09-08T04:00:29.000Z)` — Deploy do `medprev-institucional-cms` iniciado no cluster `eks-medprev-online-prd` (evento `source:change_tracking`, `identified_changes:9`, `kube_condition_available:false`).
2. `01:00:30 08/09/2026 BRT (epoch 1788840030000 · 2026-09-08T04:00:30.000Z)` — 1ª ocorrência `FailedScheduling`: "0/10 nodes are available: 1 node(s) didn't match pod topology spread constraints, 2 Insufficient memory, 2 node(s) had untolerated taint(s), 7 Insufficient cpu" (node `ip-10-0-10-78`).
3. `01:00:57 08/09/2026 BRT (epoch 1788840057000 · 2026-09-08T04:00:57.000Z)` — 2ª ocorrência `FailedScheduling`: "0/11 nodes are available" (mesmo padrão, agora 11 nodes candidatos, node `ip-10-0-10-78`).
4. `01:00:57 08/09/2026 BRT (epoch 1788840057000 · 2026-09-08T04:00:57.000Z)` — 3ª ocorrência `FailedScheduling`, mesmo texto, node candidato diferente (`ip-10-0-1-237`, com `host_provider_id` presente — indício de node novo sendo provisionado).
5. `01:02:58 08/09/2026 BRT (epoch 1788840178000 · 2026-09-08T04:02:58.000Z)` — Novo evento de deployment (`identified_changes:3`, `kube_condition_available:false`) — deployment ainda em progresso.
6. `01:03:22 08/09/2026 BRT (epoch 1788840202000 · 2026-09-08T04:03:22.000Z)` — Log de aplicação: banner de start do Strapi ("Welcome back!", "Version 4.15.5 (node v18.20.8)", "Database: postgres") — a aplicação já respondia.
7. `01:03:28 08/09/2026 BRT (epoch 1788840208000 · 2026-09-08T04:03:28.000Z)` — Evento de deployment (`identified_changes:3`, ainda `kube_condition_available:false`).
8. `01:07:14 08/09/2026 BRT (epoch 1788840434000 · 2026-09-08T04:07:14.000Z)` — Evento de deployment com `kube_condition_available:true` — deployment totalmente disponível, incidente encerrado.

Não há mais ocorrências de `FailedScheduling` neste namespace dentro da janela de coleta (`window_from`: 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) até `window_to`: 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z)), apesar de o mesmo redeploy diário ter ocorrido também em 07, 09, 10 e 11/09 sem falha de agendamento.

## Evidência

- 3 eventos `FailedScheduling` no namespace `medprev-institucional-cms`, todos em 08/09/2026 entre `01:00:30 08/09/2026 BRT (epoch 1788840030000 · 2026-09-08T04:00:30.000Z)` e `01:00:57 08/09/2026 BRT (epoch 1788840057000 · 2026-09-08T04:00:57.000Z)`: [Events Explorer (namespace + Reason, janela fixada)](https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-institucional-cms%20FailedScheduling&from_ts=1788808256645&to_ts=1789153856645&live=false).
- Motivo declarado pelo scheduler em todas as 3 ocorrências: insuficiência de CPU/memória, taints não tolerados e violação de topology spread constraints — mesma query acima.
- Deploy correlacionado iniciado às `01:00:29 08/09/2026 BRT (epoch 1788840029000 · 2026-09-08T04:00:29.000Z)` e concluído (`kube_condition_available:true`) às `01:07:14 08/09/2026 BRT (epoch 1788840434000 · 2026-09-08T04:07:14.000Z)`: consulta `source:change_tracking kube_namespace:medprev-institucional-cms`, executada de 2026-09-06 a 2026-09-11 (56 eventos retornados no total, sem link pronto em `evidence_links` para este source — usar a query citada no Events Explorer do Datadog).
- Aplicação reiniciada com sucesso, log de banner de start em `01:03:22 08/09/2026 BRT (epoch 1788840202000 · 2026-09-08T04:03:22.000Z)`: consulta `search_datadog_logs`, query `service:medprev-institucional-cms env:production`, janela 01:00:00 08/09/2026 BRT (epoch 1788840000000 · 2026-09-08T04:00:00.000Z)–04:05:00Z, 30 logs retornados nessa faixa de 10 minutos.
- Spans de APM do serviço na janela completa do achado: consulta `aggregate_spans`, query `service:medprev-institucional-cms env:production`, agrupado por `@http.status_code` — **0 buckets retornados** (sem dados de tracing).
- Logs totais do serviço na janela completa: consulta `search_datadog_logs`, query `service:medprev-institucional-cms env:production` — **762 logs**; com `status:error` adicionado — **240 logs**, mas a amostra retornada é de `npm error` em `15:02:30 11/09/2026 BRT (epoch 1789149750000 · 2026-09-11T18:02:30.000Z)`, fora do horário do incidente.
- Nenhum trace_id disponível para correlação de trace completo — decorre diretamente da ausência de spans acima, não de limitação de consulta.

## Ação recomendada

Revisar o dimensionamento do node pool `default` do Karpenter (ou adicionar buffer de capacidade/pre-scaling) no cluster `eks-medprev-online-prd` para absorver o pico de agendamento do redeploy diário às 04:00 UTC sem retry, já que a insuficiência de CPU/memória se repetiu em 3 tentativas na mesma janela de 27 segundos antes do Karpenter provisionar um node novo.

## Corpo da issue

### Descrição do incidente
No namespace `medprev-institucional-cms` (cluster `eks-medprev-online-prd`), o pod `medprev-institucional-cms-7c467869f9-4kltm` teve 3 tentativas de agendamento rejeitadas pelo scheduler em 08/09/2026, durante o redeploy automatizado diário das 04:00 UTC, por falta momentânea de capacidade (CPU, memória, taints e topology spread constraints) nos nodes existentes. O pod foi agendado com sucesso poucos minutos depois (aplicação respondendo já às 04:03 UTC), sem impacto observável identificado nas consultas realizadas.

### Causa raiz
Ruído operacional autolimitado — sem classificação handled/unhandled aplicável (achado não é de Error Tracking); 0 spans de APM e nenhum log de erro correlacionado foram encontrados na janela do incidente. Causa técnica: capacidade insuficiente nos nodes do pool `default` do Karpenter no instante do redeploy diário, resolvida automaticamente pelo próprio Karpenter/scheduler em ~7 minutos.

### Linha do tempo
1. Deploy iniciado às 04:00:29 UTC (`kube_condition_available:false`, `identified_changes:9`).
2. FailedScheduling às 04:00:30 UTC — 0/10 nodes disponíveis (CPU, memória, taints, topology spread).
3. FailedScheduling às 04:00:57 UTC (2 ocorrências) — 0/11 nodes disponíveis, incluindo tentativa em um node novo (`ip-10-0-1-237`, provável node recém-provisionado).
4. Aplicação já respondendo (banner de start Strapi) às 04:03:22 UTC.
5. Deployment marcado `kube_condition_available:true` às 04:07:14 UTC.
6. Mesmo padrão de redeploy diário às 04:00 UTC ocorreu em 06, 07, 09, 10 e 11/09 sem repetir o FailedScheduling — evento isolado a 08/09.

### Evidências
- Events Explorer (FailedScheduling, namespace, janela fixada): https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Amedprev-institucional-cms%20FailedScheduling&from_ts=1788808256645&to_ts=1789153856645&live=false
- Query usada para deploys correlacionados (sem link pronto): `source:change_tracking kube_namespace:medprev-institucional-cms`, 2026-09-06 a 2026-09-11.
- Query usada para logs de aplicação: `service:medprev-institucional-cms env:production`, 01:00:00 08/09/2026 BRT (epoch 1788840000000 · 2026-09-08T04:00:00.000Z)–04:05:00Z (30 logs).
- Query usada para spans/APM: `aggregate_spans`, `service:medprev-institucional-cms env:production`, janela completa do achado — 0 resultados.

### Ação recomendada
Repositório: `Medprev/medprev-institucional-cms` (código da aplicação) — mas a ação é de infraestrutura, no Helm chart/values do deployment (`medprev-helm-charts-application`, versão `7.1.0`) ou na configuração do Karpenter NodePool `default` do cluster `eks-medprev-online-prd`. Ação concreta: aumentar a margem de capacidade livre do NodePool `default` (via `disruption`/consolidation settings do Karpenter, ou reduzir a agressividade de bin-packing) para que o redeploy diário não precise aguardar provisionamento de node sob demanda; alternativamente, revisar `topologySpreadConstraints` e `tolerations` do deployment `medprev-institucional-cms` para reduzir a chance de rejeição imediata. Validação: acompanhar a mesma query de eventos acima por pelo menos 5 ciclos de deploy diário (04:00 UTC) e confirmar ausência de novas ocorrências `FailedScheduling`.

### Volume
3 ocorrências entre 16:10:56 07/09/2026 BRT (epoch 1788808256645 · 2026-09-07T19:10:56.645Z) e 16:10:56 11/09/2026 BRT (epoch 1789153856645 · 2026-09-11T19:10:56.645Z). Consulta direta ao Datadog com a mesma query e janela retornou o mesmo total (3) — sem divergência.

### Severidade e criticidade
Severidade do achado: `medium`. Como o achado foi classificado como ruído operacional autolimitado, essa severidade não se aplica ao evento em si. Criticidade real (inferência, não dado direto do achado): baixa neste caso concreto — a recuperação foi automática e completa em ~7 minutos, sem evidência de erro de aplicação ou downtime nas consultas de logs e spans feitas. Porém, o padrão indica um risco latente de criticidade média: se a insuficiência de capacidade persistir por mais tempo em um dia futuro (ex.: pico de tráfego coincidindo com o redeploy), o serviço institucional pode ficar temporariamente indisponível até o Karpenter provisionar capacidade.
