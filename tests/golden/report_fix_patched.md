---
fingerprint: et-golden-fix
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
state: promoted
cost:
  input_tokens: 12000
  output_tokens: 800
  cache_read_input_tokens: 9000
  cache_creation_input_tokens: 1200
  duration_s: 42.5
  usd: 0.32
  model: claude-sonnet-5
issue: https://github.com/Medprev/medprev-product-backlog/issues/1
datadog_url: https://app.datadoghq.com/error-tracking/issue/et-golden-fix
fix_pr: https://github.com/Medprev/medprev-web-app/pull/1372
fix_state: pr_open
fix_attempts: 1
fix_cost:
  input_tokens: 90000
  output_tokens: 4200
  cache_read_input_tokens: 80000
  cache_creation_input_tokens: 3000
  duration_s: 311.5
  usd: 1.75
  model: claude-sonnet-5
---

**Link do Datadog:** https://app.datadoghq.com/error-tracking/issue/et-golden-fix

Causa raiz: timeout no client axios apos 5s.
