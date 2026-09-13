---
fingerprint: et-golden-test
source: error_tracking
reason: ProfessionalNotFoundException
novelty: regression
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
state: new
cost:
  input_tokens: 12000
  output_tokens: 800
  cache_read_input_tokens: 9000
  cache_creation_input_tokens: 1200
  duration_s: 42.5
  usd: 0.32
  model: claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/error-tracking/issue/et-golden-test
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/error-tracking/issue/et-golden-test

Causa raiz: timeout no client axios apos 5s.
