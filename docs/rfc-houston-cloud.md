# RFC — Houston na cloud: da PoC local a um serviço agendado na AWS

**Status:** Em revisão
**Data:** 2026-09-04
**Autora:** Carla Cury
**Decisores:** Carla Cury — estilo autocrático, com revisão do tech lead
**Supersede:** nada. Complementa os ADRs 0001–0021 deste repo; onde contradiz, o ADR novo é citado.

## Documentos relacionados

- `README.md` — o pipeline como ele roda hoje.
- `CLAUDE.md` — o contrato interno do repo (o que o agente pode e não pode).
- `docs/adr/0001` a `docs/adr/0021` — as decisões que a PoC já pagou para aprender.
- `Medprev/medprev-librarian`: `ARCHITECTURE.md`, `CONTEXT.md`, `ROADMAP.md`, `docs/adr/` — a referência de práticas.
- `Medprev/medprev-cloud-iac` — o padrão real de Lambda da casa (`modules/**/lambda.tf`).
- Refinamento com o tech lead (Granola, "AI agents architecture — library, monitoring, and QA testing"), **incorporado nesta versão**. É a fonte de quatro definições: o escopo do librarian, o gatilho por webhook, a plataforma dos agentes e o custo por rodada.

---

## Glossário

Quem nunca abriu este repo precisa destes termos para ler o resto.

| Termo | O que é |
|---|---|
| **Achado (finding)** | Um sinal de problema em produção, normalizado numa forma só, venha ele de qual fonte vier. |
| **Fonte** | De onde o sinal vem: **Error Tracking** (erros agrupados do Datadog), **Kubernetes** (eventos de warning do cluster), **Monitor** (notificações de alerta). |
| **Fingerprint** | Identidade estável de um achado (`et-{issue_id}`, `k8s-{cluster}-{reason}-{namespace}`, `mon-{monitor_id}`). É o que permite dizer "esse eu já vi". |
| **Dedup** | Ignorar achados já tratados. Hoje: existir o arquivo `reports/{fingerprint}.md` **é** o mecanismo — não há índice nem banco. |
| **Cap** | Limitar quantos achados vão para o agente por rodada, ranqueando por severidade, depois round-robin entre fontes (ADR-0018). |
| **PII gate** | Validador que barra CPF, CNPJ, e-mail, telefone BR e cartão (Luhn) no arquivo renderizado inteiro, antes de gravar. |
| **Quarentena** | Destino de um relatório que bateu no PII gate: o texto vai para fora do git, e fica um registro redigido `state: quarantined` (ADR-0015). |
| **Estado do relatório** | `seeded` (dívida pré-existente, nunca investigada) · `new` (investigado, aguardando humano) · `promoted` (virou issue) · `discarded` (ruído) · `incomplete` (falhou/estourou tempo) · `quarantined`. |
| **Agente de investigação** | Um processo de LLM só-leitura que lê o Datadog e escreve um relatório. Não tem ferramenta de escrita. |
| **Agente de correção (fix agent)** | Um processo de LLM com ferramentas de código que edita o repo do serviço afetado e abre um PR. Nunca faz merge. |
| **MCP** | *Model Context Protocol* — o protocolo pelo qual o agente ganha ferramentas externas. Hoje o agente de investigação usa o servidor MCP do Datadog. |
| **Bedrock** | Serviço da AWS que serve modelos Claude sob a identidade AWS da conta, sem chave da Anthropic. |
| **Hexagonal `app`/`infra`/`run`** | Layout do librarian: `app` é a regra de negócio pura, `infra` fala com o mundo, `run` é o ponto de entrada que monta os dois. As setas apontam `run → app ← infra`. |
| **Fan-out** | Quebrar um lote em N mensagens independentes, cada uma processada por uma invocação separada. |
| **ADR** | *Architecture Decision Record* — um arquivo curto que registra uma decisão e por quê. |

---

## 1. Contexto

### 1.1 O que existe hoje

O `medprev-poc-houston` é uma prova de conceito de 2.049 linhas de Python que roda inteira num laptop. Ela faz três coisas em sequência:

1. **Detecta** — chama a REST v2 do Datadog em três fontes, normaliza tudo na mesma forma de achado, calcula um fingerprint determinístico, descarta o que já foi visto e corta o resto num top-N por severidade.
2. **Investiga** — para cada achado novo, dispara um subprocesso `claude -p` com ferramentas **só de leitura** do Datadog, teto de US$ 0,50 e 300 s de relógio. A saída passa pelo PII gate e vira um Markdown versionado em `reports/`.
3. **Corrige** — para um achado que um humano promoveu, dispara um segundo `claude -p`, agora com `Bash,Read,Write,Edit,Glob,Grep`, dentro de um `git worktree` do repo do serviço afetado, com teto de US$ 3,00 e 600 s. Ele escreve a correção, tenta rodar os testes e abre um PR ligado à issue.

Entre as fases há três decisões humanas: promover ou descartar o relatório, criar a issue, e revisar o PR. O agente nunca faz merge.

### 1.2 O que a PoC provou — números medidos, não estimados

Todos os números abaixo saem do front-matter dos 152 relatórios em `reports/`, não de estimativa:

| Medida | Valor | Como foi obtido |
|---|---|---|
| Corpus de achados | 152 relatórios | 102 error_tracking · 43 kubernetes · 7 monitor |
| Dívida pré-existente | 143 `seeded` | achados que existiam antes da PoC começar |
| Investigações realmente pagas | 9 | as únicas com `usd > 0` |
| Custo total das 9 | **US$ 2,9530** | soma do campo `cost.usd` |
| Custo médio por investigação | **US$ 0,3281** | mín. US$ 0,2414 · máx. US$ 0,4206 |
| Duração por investigação | **87,0 s a 147,5 s**, mediana 115,6 s | campo `cost.duration_s` |
| Taxa de falso positivo | **22,2%** (2 `discarded` de 9 decididos) | 7 `promoted` · 2 `discarded` |
| PRs abertos pelo fix agent | 3 (`fix_state: pr_open`) | campo `fix_pr` |

O que isso diz: a hipótese central — *um agente lendo Datadog produz causa raiz suficiente para virar issue* — se sustentou em 7 de 9 casos, a US$ 0,33 cada. E o ciclo fechou de ponta a ponta: 3 correções viraram PR real em repositório de produção.

Um número **não** medido: o custo do fix agent. O README estima "~US$ 2–3 por fix", mas o front-matter não registra custo de correção — só `fix_pr` e `fix_state`. É estimativa, não medição.

### 1.3 O problema: o que quebra quando sai do laptop

Cinco coisas que a PoC resolveu de um jeito que só funciona localmente:

1. **O estado mora no disco do laptop.** Dedup é "o arquivo existe". Métrica é "leia todos os `.md`". Num runtime efêmero, nada disso sobrevive à invocação — o serviço reinvestigaria os mesmos 152 achados, pagando de novo.
2. **O acesso ao modelo é a credencial interativa da máquina.** O ADR-0001 escolheu `claude -p` justamente para não abrir chave nova da Anthropic na conta da empresa. Essa credencial é de uma sessão humana; não existe em runtime não interativo.
3. **O fix agent depende de clones locais.** `houston/service_repos.yaml` mapeia serviço → `~/repos/m/...`. Não há esses caminhos na nuvem.
4. **Ninguém dispara.** Hoje a Carla roda `mise run run`. Não há agendamento, nem retentativa, nem alarme quando a rodada falha.
5. **A separação de poder entre os dois agentes é por flag, não por construção.** O agente de investigação é só-leitura porque `--disallowedTools Bash,Write,Edit` está no comando. Errar essa string uma vez dá ao investigador acesso de escrita. Numa PoC de uma pessoa isso é aceitável; num serviço, não.

Some-se a isso o objetivo declarado: **deixar disponível na cloud** e **seguir as práticas do medprev-librarian**.

### 1.4 A fronteira entre o librarian e o Houston

O refinamento com o tech lead resolveu uma confusão que estava travando o desenho — nas palavras da própria nota, *"Max citou o librarian como destino para tudo, mas ele não resolve tudo: gerou confusão"*. A definição que ficou:

> **O librarian é um indexador, não um agente.** Ele cria ferramentas de acesso a Google Drive, GitHub, Slack, Metabase, Datadog e PostHog, e funciona como **proxy** para serviços que o agente não alcança direto. A intenção é mantê-lo puro, sem skills embutidas. **Os agentes de QA e de AIOps são projetos separados que usam o librarian como ferramental.**

Isso decide a forma do repositório (§3.1) e muda de onde vêm as ferramentas do agente (§3.5). O Houston é um **consumidor** do librarian, não uma extensão dele.

**Uma restrição de sequência, verificada:** o librarian **ainda não tem conector Datadog**. Os conectores implementados hoje são Notion, GitHub e Google (Drive, Gmail, Calendar) — Datadog está na lista de intenção da nota, não no código. O Houston precisa de ferramentas Datadog agora. Logo: o acesso ao Datadog fica **atrás de uma porta** no Houston, implementada hoje direto contra a REST v2 e trocável pela fachada do librarian quando o conector existir. Essa é a razão prática, e não estética, para o layout hexagonal.

### 1.5 O que herdar do librarian como método

Verificado no repo: **o librarian não tem Lambda.** O `ROADMAP.md` marca *"Phase 7 — Deploy: DEFERRED"* e a `docs/runbooks/deploy.md` abre com *"hosting is still Phase 7 — deferred: no target platform is decided"*. O que existe é empacotamento (ADR-0047: uma imagem OCI, dois comandos). O refinamento é coerente com isso ao separar as plataformas: *"ambos devem ser hospedados na AWS Lambda; Kubernetes faz mais sentido para o librarian (disponibilidade contínua)"* — o indexador é um serviço que fica de pé, os agentes são disparados por evento.

Herdar do librarian é herdar o modo de construir:

- Layout hexagonal `run → app ← infra` com nomes de intenção, não de padrão (ADR-0002 "screaming layout").
- **Portas segregadas por capacidade**: uma habilidade depende só da fatia que usa, e o que não pode escrever não recebe porta de escrita. A separação é estrutural, verificada por teste e por contrato de import-linter — não por flag.
- `CONTEXT.md` (o que as coisas *são*), `ARCHITECTURE.md` (a forma), `ROADMAP.md` (o que vem quando), `docs/adr/` (por quê).
- Terraform real rodando em LocalStack no dev, para que o mesmo HCL suba na AWS depois.
- DynamoDB + KMS como substrato de estado e segredo; adaptador ligado à partição no construtor.
- Log estruturado JSON com `correlation_id` e redação de segredo; trilha de auditoria por ação.
- Modelo alcançado por uma porta configurável, com **Bedrock sob a identidade AWS** como caminho de credencial (ADR-0019 §3) — o que dissolve a restrição do nosso ADR-0001.

### 1.6 Fora de escopo

- **Console web.** O librarian tem um (`apps/web`, Vue). Houston v1 não terá; o gate humano vive no GitHub.
- **Multi-tenant.** O librarian separa Tenant e Project porque serve vários. Houston serve uma organização só.
- **Mudar a heurística de detecção.** Fingerprint por namespace (ADR-0008), cap por severidade e round-robin (ADR-0018), regras do PII gate (ADR-0017) e contagem por janela (ADR-0014) seguem como estão. Foram pagas com investigação real.
- **Mudar o prompt de investigação.** O texto e a estrutura de saída permanecem.
- **O `medprev-houston`.** Nome já ocupado por um sistema diferente (`medprev-product-backlog#242`/`#5483`) — ver ADR-0002.
- **Merge automático.** O PR continua sendo o gate humano.
- **O agente de QA.** Projeto separado, com gatilho em PR aberta e possivelmente EC2 Spot + Playwright. Ele é, porém, o **próximo consumidor do molde** que este repo criar — ver N11.
- **Migração Vue 3.3→3.5 e o benchmark TRIMS.** Assunto do mesmo refinamento, sem interseção com este desenho.
- **Construir o conector Datadog do librarian.** Fica na porta (§1.4); quem o constrói e quando é pergunta aberta (§8).

---

## 2. Requisitos

Cada item abaixo passa em pelo menos um dos testes de relevância arquitetural: é caro de reverter, força um componente a existir, ou o sistema falha no seu propósito sem ele. Detalhe de funcionalidade que não muda a forma ficou de fora.

### 2.1 Funcionais

| # | Requisito |
|---|---|
| **F1** | Coletar as três fontes do Datadog em cadência agendada, sem intervenção humana, com janela configurável. |
| **F2** | Deduplicar por fingerprint de forma determinística e **durável entre execuções e entre runtimes** — um achado já tratado nunca é pago duas vezes. |
| **F3** | Investigar cada achado elegível com um agente que só lê, produzindo relatório com causa raiz, linha do tempo, evidência como ponteiro+consulta, ação recomendada e corpo de issue 5W2H. |
| **F4** | Barrar CPF, CNPJ, e-mail, telefone BR e PAN no arquivo renderizado **inteiro**, antes de qualquer persistência ou exposição; um acerto vai para quarentena rastreável, sem perder o registro de que o achado já foi pago. |
| **F5** | Registrar a decisão humana (`promoted` / `discarded`) ligada à issue, porque é ela que mede a taxa de falso positivo. |
| **F6** | Corrigir um achado promovido com um agente de código que abre PR ligado à issue, em branch dedicada, sem merge e sem force-push. |
| **F7** | Computar FP rate, fix rate, custo total e por achado a partir do estado persistido — nunca digitado à mão. |
| **F8** | Oferecer o mesmo fluxo por linha de comando local, para depurar sem subir infra. |
| **F9** | Alcançar o Datadog por uma porta, não por chamada direta espalhada — para que a implementação troque de REST própria para a fachada do librarian sem tocar em caso de uso. |

### 2.2 Não funcionais

| # | Requisito | Como se verifica |
|---|---|---|
| **N1** | Nenhum processo tem, ao mesmo tempo, credencial de leitura de produção e credencial de escrita em repositório. A separação é **estrutural** — por fronteira de execução e de identidade, não por flag de linha de comando. | Teste de composição + política IAM/GitHub App distintas. |
| **N2** | Teto de gasto por rodada e por achado, aplicado antes da chamada e registrado depois — inclusive em execução que falhou (ADR-0013). | Campo de custo em todo registro, inclusive `incomplete`. |
| **N3** | Zero credencial de longa duração em código, imagem ou variável de ambiente commitada. Segredo em Secrets Manager; identidade por role. | Revisão de IaC + varredura de segredo no CI. |
| **N4** | Log estruturado JSON com `correlation_id` por rodada e por achado, custo e duração por invocação, e redação de segredo no transporte. | Contrato de logging da casa (`observability-logging`). |
| **N5** | Toda infra por Terraform, no padrão do `medprev-cloud-iac`. Nada criado no console. | `terraform plan` limpo; nenhum recurso órfão. |
| **N6** | O estado sobrevive ao runtime: relatórios, decisões, custos e quarentena persistem fora do sistema de arquivos do processo. | Reinvocação a frio não reinvestiga nada já tratado. |
| **N7** | Falha parcial nunca fabrica resultado: timeout ou erro produz `incomplete` com o custo real registrado, jamais um relatório inventado. | Já garantido no código atual; preservar. |
| **N8** | LGPD: nenhum conteúdo de log ou dado de usuário sai do Datadog para o armazenamento. Evidência é sempre ponteiro + consulta. | PII gate + a prática já escrita no prompt. |
| **N9** | Custo mensal de operação previsível e declarado, com alarme quando exceder o teto. | Orçamento por tag + alarme. |
| **N10** | Uma rodada que falha é observável em minutos, não no dia seguinte. | Alarme de falha e de rodada vazia. |
| **N11** | A estrutura do repo serve de molde para o próximo agente (QA), que segundo o refinamento *"segue o mesmo modelo do Houston"*. O que é específico de AIOps fica isolado do que é esqueleto. | Um leitor consegue apontar o que copiaria para o agente de QA. |

---

## 3. Design

Cada componente abaixo existe porque atende a um requisito nomeado. Onde eu não conseguir nomear o requisito, o componente sai.

### 3.1 Forma do repositório

Repo próprio, `medprev-houston-agent`, seguindo as convenções do librarian: `mise.toml` na raiz, tarefas em `.mise/tasks/<grupo>/`, `CONTEXT.md` + `ARCHITECTURE.md` + `ROADMAP.md`, `docs/adr/` continuando a numeração desta PoC (0022 em diante), Terraform em `infra/terraform/` rodando contra LocalStack no dev.

O refinamento pede que o agente de QA *"siga o mesmo modelo do Houston"*. Então o repo tem duas metades legíveis: o **esqueleto** (composição, portas, store, gate de PII, contabilidade de custo, IaC, tarefas) e o **domínio AIOps** (fontes Datadog, fingerprint, cap, prompts). Copiar o esqueleto e trocar o domínio é o que o próximo agente vai fazer.

Os 21 ADRs e os 152 relatórios da PoC migram junto — a transferência de repositório carrega o histórico completo, que é exatamente a razão pela qual o PII gate roda desde o primeiro commit (ADR-0003).

### 3.2 As três camadas

```
run/  (entrada)                  app/  (puro)                    infra/  (mundo externo)
┌ handler de coleta              ┌───────────────────────────┐   ┌ DatadogSignals   (REST v2)
├ handler de investigação   ─▶ in ─▶ modelo: Finding,        │─▶─├ DynamoReportStore
├ workflow de correção           │   Report, Decision        │   ├ S3QuarantineStore (KMS)
├ CLI local (mesmo fluxo)        │ casos de uso: collect ·   │   ├ BedrockInvestigator
└ composition root               │   dedup · cap · investigate│  ├ GitHubFixer (App token)
                                 │   · gate · promote · fix   │  ├ SecretsConfig
                                 │   · metrics                │  └ StructuredAudit
                                 │ portas: SignalSource,      │
                                 │   ReportStore, Investigator│
                                 │   , Fixer, Clock           │
                                 │ regra pura: pii_gate,      │
                                 │   fingerprint, cap         │
                                 └───────────────────────────┘
```

O que muda de lugar em relação à PoC, e por quê:

- **`pii_gate.py`, `fingerprint.py`, `dedup.cap()` viram `app/`.** São funções puras, sem I/O. É a parte que não pode mudar de comportamento por causa de deploy (N7, F4).
- **`dedup.already_reported()` vira uma porta.** Hoje ela é `Path.exists()`. Vira `ReportStore.exists(fingerprint)` — a mesma pergunta, respondida por DynamoDB em produção e por disco no dev (F2, N6).
- **`agent.py` vira a porta `Investigator`.** O que o caso de uso pede é "investigue este achado e devolva corpo, custo, duração, estado". Como isso acontece — subprocesso, SDK ou API — é `infra`.
- **`fix_agent.py` vira a porta `Fixer`.** Mesma ideia: "corrija este achado e devolva a URL do PR".
- **`datadog_client.py` fica em `infra` como está.** Ele já é um wrapper fino com retry; o que precisa é ser injetado, não importado.

O ganho que N1 cobra: o caso de uso de investigação recebe `SignalSource` + `Investigator` + `ReportStore` e **nada mais**. Ele não tem sintaxe para escrever em repositório, porque a porta não existe no seu construtor. O caso de uso de correção recebe `Fixer` + `ReportStore` e não tem `SignalSource`. A separação vira propriedade da composição, não de uma string de flag.

### 3.3 Fluxo dinâmico — a rodada diária

```
 1. Datadog dispara o webhook quando um monitor alerta  (push, não cron)
 2. Handler valida a assinatura e normaliza o payload   (1 achado por evento)
 3. Fingerprint → consulta o ReportStore                (dedup, F2)
 4. Reserva o achado com escrita condicional            (idempotência)
 5.   Agente só-leitura investiga                       (teto de custo + relógio)
 6.   PII gate roda no arquivo renderizado inteiro      (F4)
 7.   Grava relatório (ou quarentena) + custo           (N2, N7)
 8. Humano lê, decide promoted/discarded, cria issue    (F5)
 9. Correção é disparada para um achado promovido       (F6)
10.   Agente de código abre PR ligado à issue
11. Squad dono revisa o PR                              (gate humano final)
12. Métricas recomputam do store                        (F7)

 — em paralelo, para o que o Datadog não empurra —
 A. Varredura agendada de Error Tracking e Kubernetes    (cron)
 B. Dedup + cap por severidade e round-robin             (top N, ADR-0018)
 C. Cada achado entra no mesmo passo 4 acima             (fan-out)
```

Os passos 1–7 e A–C são automáticos. Os passos 8 e 11 são humanos. O passo 9 é humano em v1.

**O que o webhook muda no que já existe.** Com o Datadog empurrando um evento por vez, o fan-out deixa de ser uma escolha de engenharia e passa a ser a forma natural do problema — e o limite de 900 s da Lambda some do caminho crítico. Em compensação, o `cap()` (ADR-0018) perde a função de escolher os N melhores de um lote: no caminho de webhook não há lote. Ele não morre — vira **controle de gasto**, um teto diário de investigações pagas, com a mesma ordenação por severidade decidindo quem passa quando o teto aperta. E a varredura agendada, que ainda existe para Error Tracking e Kubernetes, continua usando o `cap()` como hoje.

### 3.4 Persistência

Uma tabela DynamoDB `houston-reports`, chave de partição `fingerprint`. O corpo do relatório é atributo do item (os relatórios atuais têm poucos KB; o teto de item do DynamoDB é 400 KB). Quarentena vai para um bucket S3 dedicado com SSE-KMS, e no DynamoDB fica só o registro redigido.

Três razões, em ordem de peso:

1. **Escrita condicional resolve idempotência no fan-out.** Se a investigação for disparada por fila, a entrega é *pelo menos uma vez* — a mesma mensagem pode chegar duas vezes. `PutItem` com `attribute_not_exists(fingerprint)` faz "reserve este achado" ser atômico, e uma segunda entrega falha na condição em vez de pagar a investigação de novo. Isso é diretamente F2 + N2.
2. **Métrica vira consulta.** Hoje `metrics` lê e parseia 152 arquivos. Com índice por estado, vira agregação.
3. **É o substrato que o librarian já opera** (vault, map, audit, oauth — oito tabelas), com o padrão de adaptador ligado à chave no construtor.

O que se perde: o relatório deixa de ser um arquivo Markdown legível no git. Mitigação — o relatório continua sendo **renderizado** como Markdown (o PII gate depende disso, ADR-0015) e a exportação para arquivo continua existindo no CLI local.

### 3.5 Como o agente alcança o modelo e as ferramentas

Este é o ponto mais caro do desenho, e o que mais muda em relação à PoC.

**O bloqueio verificado:** na tabela de disponibilidade por plataforma, o **conector MCP** e os **Managed Agents** são `No` no Amazon Bedrock — existem só na API primária da Anthropic e na Claude Platform on AWS. Ou seja: **não dá para manter o servidor MCP do Datadog e usar Bedrock ao mesmo tempo.**

**A segunda restrição verificada:** o Claude Agent SDK é o Claude Code empacotado como biblioteca — ele precisa do runtime Node e do binário `claude`. O próprio librarian registra isso no ADR-0047 §3: *"Node and the `claude` CLI are **not** installed: `claude-agent-sdk` is reached only from the CLI's `ask` path, never from either server."* A imagem de servidor deles deliberadamente não carrega esse runtime.

**A saída, e a que lugar ela pertence:** trocar o servidor MCP do Datadog por **ferramentas expostas por código nosso, atrás da porta de F9**. Hoje essa porta é implementada direto contra a REST v2 do Datadog; quando o librarian ganhar seu conector Datadog, a mesma porta passa a ser servida pela fachada HTTP/JSON dele — que é exatamente o papel de proxy que o refinamento atribui ao librarian (§1.4), e o caminho que funciona sob Bedrock, onde o conector MCP não existe. O caso de uso não muda nas duas situações.

Na prática imediata: O `datadog_client.py` já é um wrapper da REST v2 do Datadog; expor três a cinco funções dele como ferramentas do modelo (buscar issue, buscar eventos, buscar logs por consulta, buscar spans) resolve o mesmo problema com três ganhos:

- **Bedrock volta a ser possível** — sem chave nova da Anthropic, atendendo à mesma restrição que gerou o ADR-0001, agora por outro caminho.
- **A superfície de ferramenta vira código nosso.** O ADR-0016 hoje monta a allowlist por heurística de verbo no nome da ferramenta MCP, e falha fechado porque não há introspecção scriptável. Com ferramentas próprias, o conjunto é literal: o que não está no dicionário não existe. A heurística some, e com ela o ADR-0016.
- **O snapshot manual de inventário MCP some** (`houston/mcp_tool_inventory_snapshot.txt`, hoje atualizado à mão).

O laço do agente passa a ser um laço explícito sobre `POST /v1/messages` (pedir → executar ferramenta → devolver resultado → repetir até `end_turn`), com teto de iterações e de tokens. São dezenas de linhas, provider-agnóstico, sem dependência de beta.

**O que isso custa:** perde-se o catálogo pronto de ferramentas do MCP do Datadog. O agente passa a enxergar só o que expusermos. Para a investigação atual isso é suficiente — as evidências nos 9 relatórios pagos citam essencialmente busca de issue, agregação de erros e consulta de eventos — mas é uma redução real de alcance e precisa ser validada com um piloto medido.

**O fix agent é caso à parte.** Ele precisa de `Bash`, `Read`, `Write`, `Edit`, `Glob`, `Grep` — reimplementar isso sobre a Messages API é reescrever meio Claude Code. Aqui a decisão certa é *não* portar: manter o `claude -p` como está e rodá-lo onde Node, `git` e `gh` já existem nativamente. Ver §4, dimensão [Runtime].

### 3.6 Identidade e segredos

| Segredo | Onde vive | Quem lê |
|---|---|---|
| `DD_API_KEY` / `DD_APP_KEY` (escopo de leitura) | Secrets Manager, injetado como no padrão do `medprev-chat-core` (`jsondecode(aws_secretsmanager_secret_version...)`) | só o processo de coleta/investigação |
| Credencial do modelo | Nenhuma — identidade AWS da role, via Bedrock | só o processo de investigação |
| Token de escrita no GitHub | **GitHub App** instalado nos repos-alvo, token de instalação de vida curta | só o processo de correção |

Há precedente na casa: o librarian tem um `ADR-0018 — github-app-delegated-auth` (li o índice de ADRs, não o corpo do documento). Um PAT pessoal não serve: expira com a pessoa, e dá escopo largo demais para uma automação que escreve em repositório de produção.

Isso é o que faz N1 valer estruturalmente: **o processo que lê o Datadog não tem token do GitHub, e o processo que escreve código não tem chave do Datadog.** Não é uma flag; são duas identidades diferentes em dois lugares diferentes.

### 3.7 O gate humano

O estado canônico fica no `ReportStore`. A interface humana é a **issue do GitHub**, onde a pessoa já está:

- `houston promote` cria a issue com o corpo 5W2H que o relatório já produz, e grava a URL no registro.
- A decisão `discarded` é registrada por comando (v1) — e, numa fase seguinte, por label na issue, reconciliada de volta para o store.

Não construir console web em v1 é decisão consciente: o valor que o console entregaria (ver relatórios) é entregue pela issue, e o custo dele é um front-end inteiro.

### 3.8 Observabilidade

Log JSON estruturado seguindo o contrato de logging da casa, com `correlation_id` por rodada propagado para cada achado, e o custo/duração de cada invocação como atributo — os mesmos campos que hoje vivem no front-matter. Alarme em: rodada que falhou, rodada que voltou vazia (sintoma de credencial expirada ou mudança de schema no Datadog), e gasto acumulado acima do teto (N9, N10).

---

## 4. Análise de alternativas

### Dimensão A — Onde o agente executa  ·  **fechada pelo refinamento**

> *"Ambos devem ser hospedados na AWS Lambda; Kubernetes faz mais sentido para o librarian (disponibilidade contínua)."* A análise abaixo fica registrada porque explica **por que Lambda funciona** e qual é a condição em que ela deixaria de funcionar — não para reabrir a escolha.

O número que dita esta dimensão: **o teto de execução de uma Lambda é 900 s (15 min)**, memória até 10.240 MB (1 vCPU a 1.769 MB), `/tmp` de 512 MB a 10.240 MB, imagem de container até 10 GB, payload síncrono 6 MB / assíncrono 1 MB.

Contra isso: a investigação real durou entre 87,0 s e 147,5 s (n=9), com timeout configurado em 300 s. Um achado cabe com folga. **Um lote de 5 achados a 300 s cada não cabe** — 1.500 s no pior caso. Portanto, se for Lambda, tem de ser fan-out; lote sequencial está fora por limite duro, não por preferência.

O fix agent é o oposto: 600 s de timeout, mais `git clone`, `git worktree`, execução de testes do repo-alvo e `gh pr create`.

| Alternativa | Prós | Contras | Risco | Impacto | Probab. | Mitigação | Contingência |
|---|---|---|---|---|---|---|---|
| **A1 — Lambda com fan-out (1 achado = 1 invocação)** | Cabe no teto medido com folga; escala sozinha; sem nó ocioso; é o padrão que a casa já opera no `cloud-iac` (`terraform-aws-modules/lambda/aws ~8.8`, SQS, API Gateway, Secrets Manager) | Fan-out obriga idempotência explícita; o fix agent não cabe sem imagem pesada com Node+git+gh | Uma investigação atípica estoura 900 s e morre sem registro | Médio | Baixa | Timeout da Lambda em 870 s com o teto interno em 300 s, e `incomplete` gravado antes do fim | Reduzir o teto interno; mover só esse achado para execução manual |
| | | | Entrega em duplicidade da fila paga a investigação duas vezes | Alto | Média | `PutItem` condicional reservando o fingerprint antes de chamar o modelo | Reconciliação por custo duplicado na métrica |
| **A2 — EKS Job/CronJob via ArgoCD** | Sem teto de tempo; lote e fix agent cabem no mesmo lugar; `git`/`gh`/Node numa imagem comum; cluster que a casa já opera | Nó ligado para um job que roda minutos por dia; mais superfície operacional; foge do "talvez numa lambda" | Job preso consome nó indefinidamente | Médio | Média | `activeDeadlineSeconds` e limite de recurso no manifesto | Matar o job; alarme de job pendurado |
| | | | Manifesto e imagem viram mais uma coisa para manter num repo que é de uma pessoa | Médio | Alta | Reusar o pipeline de imagem que a casa já tem | — |
| **A3 — Híbrido: Lambda detecta/investiga, GitHub Actions corrige** | Investigação onde o limite não aperta; **o fix agent roda sem reescrita nenhuma** — `claude -p` com Node, `git` e `gh` nativos e 6 h de limite; N1 vira fronteira de plataforma, não flag | Duas plataformas para operar e depurar; a correção depende da disponibilidade do Actions | O gasto de LLM em Actions não aparece no orçamento da AWS | Baixo | Alta | Registrar custo no mesmo store; um relatório de custo, duas origens | — |
| | | | Runner do Actions expõe o token de instalação a um agente que executa código arbitrário do repo-alvo | Alto | Média | GitHub App com permissão mínima, escopo por repo, token de vida curta, proibição de push em `main` já no prompt e por branch protection | Revogar a instalação; branch protection barra o estrago |
| **A4 — Lambda MicroVM** | Até **8 h** de execução por MicroVM, baseada em imagem — investigação e correção caberiam no mesmo runtime | Zero precedente na Medprev; ARM64; superfície nova para operar e para revisar | Aposta em serviço sem uso interno prévio, num projeto de uma pessoa | Alto | Alta | — | Cair para A3, que resolve o mesmo problema com peças conhecidas |

### Dimensão E — O que dispara uma rodada

| Alternativa | Prós | Contras | Risco | Impacto | Probab. | Mitigação | Contingência |
|---|---|---|---|---|---|---|---|
| **E1 — Webhook do Datadog** (o do refinamento) | Um achado por evento: o fan-out vira natural e o teto de 900 s sai do caminho crítico; latência de minutos em vez de um dia; sem invocação vazia | Cobre bem a fonte `monitor`; Error Tracking e Kubernetes só chegam por webhook se alguém criar monitores para eles — o que empurra regra de detecção para dentro da configuração do Datadog | Endpoint público recebe evento forjado e paga investigação | Alto | Média | Segredo em header custom do webhook, validado antes de qualquer chamada de modelo; teto diário de gasto | Rotacionar o segredo; desligar a rota |
| | | | Uma tempestade de alertas dispara dezenas de investigações pagas | Alto | Média | Teto diário no `cap()` reaproveitado como controle de gasto; dedup por fingerprint corta a repetição | Alarme de gasto e desligamento da rota |
| **E2 — Varredura agendada** (o que a PoC faz) | Cobre as três fontes sem depender de configuração no Datadog; o `cap()` funciona como foi desenhado | Latência de um dia; lote não cabe em Lambda sem fan-out; invoca mesmo quando não há nada | Achado urgente espera a próxima rodada | Médio | Alta | Cadência mais curta | — |
| **E3 — Os dois** (recomendado) | Webhook onde o Datadog empurra, varredura onde ele não empurra; nenhuma fonte perde cobertura | Dois caminhos de entrada para testar e observar | Um achado entra pelos dois caminhos e é investigado duas vezes | Médio | Alta | O fingerprint é o mesmo nos dois caminhos, e a reserva condicional resolve na primeira escrita | Reconciliação por custo duplicado |

### Dimensão B — Como o agente alcança o modelo

| Alternativa | Prós | Contras | Risco | Impacto | Probab. | Mitigação | Contingência |
|---|---|---|---|---|---|---|---|
| **B1 — Bedrock + ferramentas próprias sobre a REST do Datadog** | Sem chave nova da Anthropic (a restrição do ADR-0001 continua honrada); identidade AWS por role; superfície de ferramenta explícita, o que aposenta a heurística do ADR-0016; Python puro, empacota em qualquer runtime | Perde o catálogo pronto do MCP do Datadog; o alcance do agente passa a ser o que expusermos | A investigação piora porque faltou uma ferramenta que o MCP dava | Alto | Média | Piloto medido: rodar os mesmos achados já investigados e comparar os relatórios lado a lado antes de cortar o caminho antigo | Voltar para B2 nos achados onde a qualidade cair |
| | | | Modelo Claude não habilitado na conta/região Bedrock da Medprev | Alto | Média | Confirmar habilitação e região antes de escrever código | Usar a região onde já está habilitado |
| **B2 — API primária da Anthropic + conector MCP** | Mantém o servidor MCP do Datadog e o alcance atual; menos reescrita | Exige a chave que o ADR-0001 recusou; conector MCP é beta; nova linha de custo e de governança de credencial | A chave vira um segredo a mais para rotacionar e auditar | Médio | Alta | Secrets Manager + rotação | — |
| **B3 — Claude Agent SDK (caminho do librarian)** | É o que o librarian usa hoje e funciona sobre Bedrock; ferramentas embutidas prontas | Precisa de Node + binário `claude` no runtime — o próprio ADR-0047 do librarian exclui esse runtime da imagem de servidor; empacotamento pesado em Lambda | A imagem cresce e a fronteira "quem pode escrever" volta a ser configuração do SDK | Médio | Média | Imagem de container com camada fixada | Usar B1 na investigação e reservar o SDK/CLI só ao fix agent |
| **B4 — Manter `claude -p` como está, num runtime com o CLI** | Zero reescrita | A credencial é de sessão humana; não existe em runtime automatizado | O serviço para quando a credencial da máquina expira | Alto | Alta | — | Inviável para serviço; permanece só no CLI local |

### Dimensão C — Onde o estado vive

| Alternativa | Prós | Contras | Risco | Impacto | Probab. | Mitigação | Contingência |
|---|---|---|---|---|---|---|---|
| **C1 — DynamoDB (+ S3/KMS para quarentena)** | Escrita condicional dá idempotência atômica no fan-out; consulta por estado torna métrica barata; é o substrato do librarian | Relatório deixa de ser arquivo versionado no git; mais um recurso no IaC | Item acima de 400 KB é rejeitado | Baixo | Baixa | Corpo grande vai para S3 e o item guarda o ponteiro | — |
| **C2 — S3 com os mesmos Markdown** | Mudança mínima em relação a hoje; relatório continua legível; barato | Métrica exige listar e parsear tudo; idempotência depende de escrita condicional do S3, menos direta que a do DynamoDB | Métrica fica lenta conforme o corpus cresce | Baixo | Média | Índice separado — que é reinventar C1 | Migrar para C1 |
| **C3 — Postgres** | Consulta rica; a casa já opera Aurora | Puxa VPC, pool de conexão e migração para um serviço que grava dezenas de linhas por dia | Custo e acoplamento desproporcionais ao volume | Médio | Alta | — | — |

### Dimensão D — Onde o fix agent executa

| Alternativa | Prós | Contras | Risco | Impacto | Probab. | Mitigação | Contingência |
|---|---|---|---|---|---|---|---|
| **D1 — GitHub Actions** | `git`, `gh`, Node e o CLI já existem; 6 h de limite; `fix_agent.py` roda praticamente sem mudança; a credencial de escrita nunca entra na AWS | Segunda plataforma; custo de LLM fora do orçamento AWS | O agente executa código arbitrário do repo-alvo no runner | Alto | Média | GitHub App com escopo mínimo; branch protection em `main`; proibição de force-push | Revogar instalação |
| **D2 — Lambda de container com Node+git+gh** | Uma plataforma só; orçamento único | Imagem grande; 900 s pode não bastar para clonar, corrigir e rodar testes de um repo grande; `/tmp` precisa ser dimensionado | Timeout no meio do fix deixa branch órfã | Médio | Alta | `/tmp` em 10 GB e limpeza de worktree no `finally` (já existe no código) | Reexecutar com `-v2` na branch, como o código já faz |
| **D3 — EKS Job** | Sem teto de tempo; imagem comum com A2 | Só compensa se A2 for a escolha do runtime de investigação | — | — | — | — | — |

---

## 5. A decisão

Estilo: **autocrático** — a decisão é minha, revisada pelo tech lead.

### 5.1 Decidido

| Dimensão | Decisão | Razão de uma linha |
|---|---|---|
| Repositório | **Repo próprio** `medprev-houston-agent`, convenções do librarian | O refinamento define o librarian como ferramental, e os agentes como projetos separados que o consomem (§1.4) |
| Plataforma | **AWS Lambda** | Decidido no refinamento; o teto de 900 s cabe na duração medida (87–148 s) |
| Gatilho | **E3 — webhook do Datadog + varredura agendada** | O webhook é o que o refinamento pede e resolve `monitor`; a varredura cobre Error Tracking e Kubernetes, que não têm push equivalente |
| Escopo v1 | **Ciclo completo**, incluindo o fix agent | É o que a PoC já provou de ponta a ponta (3 PRs) |
| Modelo | **B1 — Bedrock + ferramentas atrás da porta de F9** | Único caminho compatível com Bedrock (conector MCP é `No` lá) e que mantém a restrição do ADR-0001; a porta é o que permite trocar a REST própria pela fachada do librarian depois |
| Estado | **C1 — DynamoDB, quarentena em S3/KMS** | Escrita condicional é o que torna o fan-out seguro |
| Fix agent | **D1 — GitHub Actions** | Roda o código atual sem reescrita e põe a separação de poder numa fronteira de plataforma |
| Layout | Hexagonal `run → app ← infra`, portas segregadas | Torna N1 propriedade da composição, não de uma flag |
| Identidade | Role AWS para o modelo; GitHub App para escrita | Precedente do librarian (ADR-0018); sem credencial pessoal |

### 5.2 Onde eu discordo do refinamento, e por quê

O refinamento diz *"ambos devem ser hospedados na AWS Lambda"*, e para detecção e investigação isso fecha sem atrito. **Para o fix agent eu recomendaria o contrário**, e coloco o argumento aqui em vez de decidir sozinha.

O fix agent precisa de `git`, `gh`, Node e o binário `claude`, mais espaço para clonar um repo e rodar a suíte dele, dentro de 900 s. Em Lambda isso significa uma imagem de container carregando esses runtimes e um `/tmp` dimensionado — e o `medprev-rest-api` clonado com testes rodando é o tipo de coisa que encosta nos 900 s. No GitHub Actions esse mesmo agente roda **sem uma linha de mudança**: o ambiente já tem tudo, o limite é de 6 h, e o token de escrita nunca precisa entrar na AWS.

Há um ganho de segurança junto: com o fix agent no Actions, N1 deixa de ser uma flag `--disallowedTools` e passa a ser uma fronteira de plataforma. **O processo que lê produção não tem token do GitHub; o processo que escreve código não tem chave do Datadog.**

O que pesa do outro lado, e é real: duas plataformas para operar e depurar, num serviço mantido por uma pessoa, e o custo de LLM aparecendo em dois relatórios. Se a preferência for plataforma única, D2 (Lambda de container) é viável — a mitigação é `/tmp` em 10 GB e aceitar que repositório grande com suíte lenta vai estourar às vezes, caindo em `incomplete` e sendo reexecutado, que é o comportamento que o código já tem.

**A decisão é sua.** O roadmap (§7) só depende dela na Fase 4.

### 5.3 O que precisa de medição antes de virar código

Duas incertezas que nenhum documento resolve — só experimento:

1. **A qualidade da investigação sem MCP.** Rodar os 9 achados já investigados através de B1 e comparar os relatórios com os que estão em `reports/`. Critério: a causa raiz e a evidência se mantêm em pelo menos 7 dos 9. Custo do experimento: ~US$ 3 em modelo.
2. **O custo real no Bedrock.** Os US$ 0,3281 medidos vêm do envelope do Claude Code, e a contabilidade de token daqueles relatórios é sabidamente incompleta — há registro de investigação de US$ 0,35 com `input_tokens: 12`. O refinamento traz a forma real do consumo: **14k tokens de entrada, 11k de saída por rodada**. Isso reconcilia: a esse volume, ao preço de tabela da API primária para Opus 5 (US$ 5/M entrada, US$ 25/M saída), a conta dá **US$ 0,345** — contra US$ 0,3281 medidos. A forma do consumo está entendida.

   Duas ressalvas que impedem transformar isso em orçamento: **o Bedrock tem preço próprio**, operado pela AWS e diferente da tabela primária; e a escolha de modelo é uma alavanca grande — o mesmo volume em Sonnet 5 (US$ 2/M e US$ 10/M) daria **US$ 0,138**, 2,5× mais barato. Se a qualidade da investigação se sustenta em Sonnet é pergunta para o piloto, não para este documento.

Com 5 achados/dia ao custo medido hoje, a ordem de grandeza é **~US$ 50/mês em modelo**, e o compute serverless é centavos ao lado disso. Em Sonnet, ~US$ 21/mês. Ambos os números pressupõem preço de API primária e precisam ser refeitos no Bedrock antes de virar orçamento.

---

## 6. Riscos residuais do desenho escolhido

| Risco | Impacto | Probab. | Mitigação | Contingência |
|---|---|---|---|---|
| O agente de correção abre PRs de baixa qualidade em escala e queima a confiança dos squads | Alto | Média | Manter o disparo da correção **manual** em v1; publicar a fix rate junto com os PRs | Desligar o fix agent; a investigação sozinha já entrega valor |
| Falso positivo de 22,2% (medido, n=9) se mantém e o time perde tempo triando ruído | Médio | Média | Medir por rodada; amostra de 9 é pequena demais para decidir agora | Subir o corte de severidade; reduzir o N por rodada |
| O PII gate deixa passar nome próprio ou PAN em corrida de 20+ dígitos — lacunas já documentadas e não resolvíveis por regex | Alto | Baixa | A prática de "evidência é ponteiro, nunca texto de log" continua no prompt; quarentena rastreável | Revisão manual do relatório antes de virar issue |
| Mudança de schema na API do Datadog quebra a coleta em silêncio | Médio | Média | Alarme de rodada vazia (N10) | Fixtures gravadas nos testes apontam a divergência |
| O serviço vira dependência de uma pessoa só | Alto | Alta | ADRs, `CONTEXT.md` e runbook desde a primeira fase | — |

---

## 7. Roadmap

Fatiado para que o primeiro corte seja medido e de risco zero, e o que depende de estimativa venha depois.

| Fase | Entrega | Risco | Como se prova |
|---|---|---|---|
| **0 — Fundação** | Repo novo, layout `app`/`infra`/`run`, código atual movido sem mudar comportamento, contrato de import-linter, suíte verde | Zero — nada roda na nuvem | A mesma suíte passa; `houston run` local produz o mesmo resultado |
| **1 — Piloto do modelo** | Ferramentas próprias sobre a REST do Datadog; os 9 achados reinvestigados via Bedrock e comparados | Baixo — só custo de modelo (~US$ 3) | 7 de 9 relatórios mantêm causa raiz e evidência; custo real no Bedrock medido |
| **2 — Estado durável** | `ReportStore` em DynamoDB + quarentena em S3/KMS; Terraform rodando em LocalStack; migração dos 152 relatórios | Baixo — ainda local | Reexecução a frio não reinvestiga nada; `metrics` reproduz os números da §1.2 |
| **3 — Houston na AWS** | Lambda de investigação, webhook do Datadog com segredo validado, varredura agendada, segredos, log estruturado, alarmes | Médio — primeiro dinheiro em produção | Um alerta do Datadog vira relatório sem intervenção; 7 dias seguidos dentro do teto de gasto |
| **4 — Correção na nuvem** | GitHub App, o fix agent no runtime decidido em §8.1, custo do fix registrado | Médio-alto — escreve em repo de produção | Um PR aberto pelo workflow, revisado e mergeado pelo squad dono |
| **5 — Fechar o laço humano** | Decisão por label na issue reconciliada para o store; painel de métricas | Baixo | FP rate e fix rate saem do store sem edição manual |

---

## 8. O que ainda está aberto

Resolvido pelo refinamento: escopo do librarian, plataforma dos agentes, gatilho por webhook e a forma do custo por rodada. O que resta:

1. **O fix agent roda em Lambda ou no GitHub Actions?** Único ponto onde recomendo diferente do refinamento — argumento inteiro em §5.2. Trava a Fase 4, não as anteriores.
2. **Bedrock na conta:** quais modelos Claude estão habilitados e em qual região. De auditoria de custo anterior — **não reverificada nesta sessão** — a Medprev consome Bedrock majoritariamente em `us-east-1`, com volume dirigido por pessoas e não por aplicação. Ter consumo não é ter o modelo certo habilitado para um serviço.
3. **O conector Datadog do librarian:** quem constrói e quando. Não bloqueia — a porta de F9 existe exatamente para isso — mas define se o Houston mantém a REST própria por seis meses ou por seis semanas.
4. **GitHub App:** quem cria e instala nos repos-alvo, e em quais repos.
5. **Destino do repo:** fica em `carlacurymed` ou nasce dentro da organização `Medprev`? Muda Actions, IaC e quem consegue revisar o PR do próprio agente.
6. **Sonnet ou Opus na investigação.** Diferença de 2,5× no custo (§5.3). Decidido pelo piloto da Fase 1, não por preferência.

## 9. Histórico de versões

| Versão | Data | Autora | Mudança |
|---|---|---|---|
| 0.1 | 2026-09-04 | Carla Cury | Primeira versão. Runtime em aberto; refinamento com o tech lead não incorporado. |
| 0.2 | 2026-09-04 | Carla Cury | Refinamento incorporado. Fecha plataforma (Lambda) e gatilho (webhook + varredura); define a fronteira librarian↔Houston (§1.4) e a porta de acesso ao Datadog (F9); reconcilia o custo com os 14k/11k tokens. Resta o runtime do fix agent (§5.2). |
