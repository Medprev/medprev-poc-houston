---
fingerprint: et-golden-quarantine
source: error_tracking
reason: ProfessionalNotFoundException
novelty: new
service: medprev-rest-api
environment: production
window:
  from: 1700000000000
  to: 1700086400000
observed:
  count: 42
  first_seen: 1700000000000
  last_seen: 1700000001000
severity: high
state: quarantined
cost:
  input_tokens: 5000
  output_tokens: 300
  cache_read_input_tokens: 0
  cache_creation_input_tokens: 0
  duration_s: 10.0
  usd: 0.1
  model: claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/error-tracking/issue/et-golden-quarantine
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/error-tracking/issue/et-golden-quarantine

Investigação concluída, relatório retido pelo gate de PII (email) sobre o arquivo renderizado. O texto completo ficou em reports/.quarantine/et-golden-quarantine.md, fora do git.

Este registro existe para dois motivos: a dedup para de reselecionar o achado (que já foi investigado e pago), e o custo continua contabilizado em `houston metrics`.

Para retomar: leia o arquivo em quarentena, decida se o achado virou issue (`state: promoted`) ou não (`state: discarded`), ou apague este registro para que o achado volte à fila de investigação.
