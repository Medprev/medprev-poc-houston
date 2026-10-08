# Output templates (pt-BR)

All three outputs share the same facts. Fill them from evidence you have; anything not checked goes to
"não verificado" — never omit a gap to make the report look complete. Times in BRT (UTC−3), with UTC in
parentheses when the source shows UTC. No PII: pointers and counts only.

## Relatório no chat

```markdown
**Veredito:** <uma frase: o que quebrou, por quê, e se já foi corrigido>

## Linha do tempo (BRT)
| Quando | Evento | Fonte |
|---|---|---|
| <data hora> | <último run com sucesso> | Airflow `<dag_run_id>` |
| <data hora> | <mudança que alterou o runtime: merge, build, release> | <git sha / ECR tag / PyPI> |
| <data hora> | <primeira falha + erro> | Airflow + log da try |
| <data hora> | <alerta no Slack> | thread |

## Causa
- **Gatilho:** <o que mudou o runtime, com o mecanismo>
- **Causa raiz:** <por que essa mudança podia quebrar>
- **Prova:** <reprodução no digest que falha vs digest bom; diff de pacotes; trecho da doc do fornecedor>
- **Por que <irmãs> passaram:** <evidência discriminante>

## Solução
1. Imediata: <ação + como validar>
2. Seguinte: <ação>
3. Estrutural: <ação + tradeoff>

## Riscos e não verificado
- <blast radius: outros jobs no mesmo caminho, DAGs pausadas>
- <impacto em dados>
- <acesso que faltou e passo que não foi feito>
```

## Resposta na thread do Slack

Short; the thread is for the people who saw the alert. Same order: causa → linha do tempo resumida →
prova → sugestão → riscos. Link the issue/PR when they exist. No code blocks longer than 3 lines.

## Issue de incidente (`Medprev/medprev-product-backlog`)

Title: `[<Projeto>] <sintoma observado>` (for example `[Analytics ETL] DAGs de sitemap falham com 'No
module named psycopg' após SQLAlchemy 2.1`). Labels empty — the team triages.

Target length is 50 lines. **The timeline and the evidence are never cut to fit**; shorten the prose of the
other sections instead. Reference model: Medprev/medprev-product-backlog#6883.

```markdown
### O que? (problema)
<sintoma, quais DAGs, erro exato>

### Por quê? (impacto)
<dados não escritos, consumidores afetados, jobs com risco latente>

### Onde?
<repo, imagem/serviço, ambiente, DAG>

### Quando?
<primeira falha, frequência, até quando>

### Quem?
<responsável; afetados>

### Linha do tempo (BRT)
| Quando | Evento | Fonte |
|---|---|---|
| ... | ... | ... |

### Evidência
- Thread: <link>
- Airflow: <dag_id / dag_run_id / task / try>
- Datadog: <consulta exata, ex. `service:… ` agrupada por `pod_name` × `image_id`>
- Imagens: <digest bom> vs <digest com falha>; diff de pacotes relevante
- Fornecedor: <link do changelog/guia de migração>

### Causa
<gatilho vs causa raiz; "não determinado" se não houver prova>

### Como? (solução)
1. Imediata …  2. Seguinte …  3. Estrutural …

### Quanto?
<esforço / volume>

### Riscos / não verificado
- …
```
