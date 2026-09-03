---
fingerprint: k8s-eks-medprev-online-prd-InstanceTerminating-unknown-namespace
source: kubernetes
reason: InstanceTerminating
novelty: new
service: unknown-namespace
environment: production
window:
  from: 1787947458029
  to: 1788293058029
observed:
  count: 193
  first_seen: null
  last_seen: null
severity: medium
state: seeded
cost:
  input_tokens: 0
  output_tokens: 0
  cache_read_input_tokens: 0
  cache_creation_input_tokens: 0
  duration_s: 0.0
  usd: 0.0
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aunknown-namespace%20InstanceTerminating&from_ts=1787947458029&to_ts=1788293058029&live=false
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aunknown-namespace%20InstanceTerminating&from_ts=1787947458029&to_ts=1788293058029&live=false

Seeded on first run — pre-existing debt, not investigated. This finding already had activity before Houston started tracking it.
