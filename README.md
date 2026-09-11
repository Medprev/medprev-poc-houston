# medprev-poc-houston

PoC que detecta problemas em produção via Datadog, investiga a causa raiz com um agente de IA, e propõe correções automaticamente via PR. Derivado da arquitetura Vigília ("Versão mínima").

## Como funciona

O pipeline tem duas fases de agente e três decisões humanas:

```
        DETECÇÃO                    INVESTIGAÇÃO               CORREÇÃO
   ┌─────────────────┐      ┌──────────────────────┐    ┌─────────────────────┐
   │  Datadog API v2  │      │  claude -p (read-only)│    │  claude -p (code)   │
   │  Error Tracking  │──┐   │  Datadog MCP tools    │    │  Bash/Read/Write    │
   │  Kubernetes      │  │   │  $0.50 budget         │    │  $3.00 budget       │
   │  Monitor alerts  │  │   │  300s timeout         │    │  600s timeout       │
   └─────────────────┘  │   └──────────────────────┘    └─────────────────────┘
                        │            ▲                           ▲
                        ▼            │                           │
                   ┌─────────┐  ┌────────┐  ┌──────────┐  ┌─────────┐  ┌────────┐
                   │ Dedup + │  │  PII   │  │ Humano   │  │ Humano  │  │ Humano │
                   │ Cap     │──│  Gate  │──│ decide   │──│ cria    │──│ revisa │
                   │         │  │        │  │ promoted/│  │ issue   │  │ PR     │
                   │severity,│  │CPF,CNPJ│  │discarded │  │         │  │        │
                   │round-   │  │email,  │  │          │  │         │  │        │
                   │robin    │  │phone,  │  │          │  │         │  │        │
                   │         │  │PAN     │  │          │  │         │  │        │
                   └─────────┘  └────────┘  └──────────┘  └─────────┘  └────────┘
                        │            │           │             │            │
                        ▼            ▼           ▼             ▼            ▼
                    top N        reports/    state:         issue URL    fix_state:
                    findings     *.md        promoted       no report    merged/
                                             ou             front-      rejected
                                             discarded      matter
```

### Passo a passo

1. **Coletar** — `houston run` busca sinais de Error Tracking, Kubernetes e Monitor via Datadog REST v2. Sem custo LLM.

2. **Dedup + Cap** — achados já reportados são ignorados. O resto é priorizado por severidade, depois round-robin entre fontes, depois volume. Top N selecionados (default 5).

3. **Investigar** — `houston investigate` roda um `claude -p` por achado, com ferramentas de leitura do Datadog (MCP). Sem acesso de escrita ao disco — o agente só lê. Produz: causa raiz, linha do tempo passo a passo (cada evento com hora exata e link/query de evidência), evidência com links do Datadog prontos, ação recomendada, e um corpo de issue pronto para o agente de correção consumir (descrição, causa raiz, linha do tempo com correlações, evidências, ação por repositório, volume, severidade e criticidade). Todo timestamp é renderizado em código — hora primeiro, epoch e ISO-8601 sempre juntos — nunca calculado pelo modelo.

4. **PII Gate** — o relatório renderizado (front-matter + corpo) passa por validação de CPF, CNPJ, email, telefone BR e PAN antes de ser gravado. Um hit redireciona para quarentena.

5. **Decisão humana** — o humano lê o relatório e marca `state: promoted` (bug real, vira issue) ou `state: discarded` (ruído). Essa decisão é o que mede a taxa de falso positivo.

6. **Promover** — `houston promote <fingerprint>` gera o comando `gh issue create` com o corpo da issue e a label `AIOPS` (toda issue aberta pelo agente carrega essa label, para dar para filtrar). Com `--create`, o próprio comando abre a issue e grava `issue:` + `state: promoted` no report, depois de quatro guardas que falham fechado: conta `gh` ativa, issue já registrada, report em quarentena e marcador não expandido no corpo (ADR-0028).

7. **Corrigir** — `houston fix <fingerprint>` roda um segundo `claude -p`, agora com ferramentas de código (Bash, Read, Write, Edit), contra o repo do serviço afetado via git worktree. O agente lê o relatório, navega o codebase, escreve a correção, tenta rodar testes, e abre um PR linkado à issue.

8. **Review do PR** — o squad dono do serviço revisa o PR. O agente nunca faz merge — o PR é o gate humano.

9. **Métricas** — `houston metrics` computa: FP rate (discarded / decididos), fix rate (merged / tentados), custo total e por finding.

### O que cada agente pode fazer

| | Agente de investigação | Agente de correção |
|---|---|---|
| **Ferramentas** | Datadog MCP (leitura) | Bash, Read, Write, Edit, Glob, Grep |
| **Bloqueado** | Bash, Write, Edit | Datadog MCP tools |
| **Escopo** | Lê sinais do Datadog | Navega e edita código-fonte |
| **Saída** | Relatório Markdown | Branch + PR no GitHub |
| **Budget** | $0.50 | $3.00 |
| **Gate** | PII gate + humano decide estado | Humano revisa PR |

## Setup

```bash
cp .env.example .env
# preencher DD_API_KEY e DD_APP_KEY (escopo de leitura) e DD_SITE
```

Task runner: [mise](https://mise.jdx.dev). `mise run <task>`, ou `mise tasks` para a lista completa.

## Comandos

| Task | O que faz | Custo? |
|---|---|---|
| `mise run setup` | Instala dependências no venv do projeto | Não |
| `mise run lint` | `ruff check .` | Não |
| `mise run test [pattern]` | Roda a suíte de testes | Não |
| `mise run run` | Coleta + dedup + cap, imprime o que seria investigado | Não |
| `mise run seed` | Registra achados pré-existentes como `state: seeded` | Não |
| `mise run investigate` | Roda o agente de investigação nos achados novos | **Sim** — ~$0.30–0.42/finding |
| `mise run promote <fp>` | Imprime o `gh issue create` pronto; com `--create`, abre a issue e grava a URL no report | Não |
| `mise run fix <fp> --issue <url>` | Roda o agente de correção, abre PR | **Sim** — ~$2–3/fix |
| `mise run metrics` | FP rate, fix rate, custo, prontidão de fase | Não |

## Ciclo diário (E7)

```bash
mise run run                          # ver o que apareceu
mise run investigate                  # investigar top 5 (~$1.90)
# ler os reports, decidir state: promoted ou discarded
mise run promote <fingerprint>        # conferir o comando/corpo que seria aberto
mise run promote <fingerprint> --create   # abrir a issue e gravar a URL no report
mise run fix <fp> --issue <url>       # corrigir via PR (~$3.00)
mise run metrics                      # conferir FP rate e fix rate
```
