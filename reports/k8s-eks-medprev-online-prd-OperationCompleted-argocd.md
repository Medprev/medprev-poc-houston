---
fingerprint: k8s-eks-medprev-online-prd-OperationCompleted-argocd
source: kubernetes
reason: OperationCompleted
novelty: new
service: argocd
environment: production
window:
  from: 1788814356569
  to: 1789159956569
observed:
  count: 1
  first_seen: 1788998985000
  last_seen: 1788998985000
severity: medium
state: quarantined
cost:
  input_tokens: 432780
  output_tokens: 9101
  cache_read_input_tokens: 339611
  cache_creation_input_tokens: 93159
  duration_s: 101.307
  usd: 0.5361792
  model: claude-haiku-4-5-20251001,claude-sonnet-5
issue: null
datadog_url: https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aargocd%20OperationCompleted&from_ts=1788814356569&to_ts=1789159956569&live=false
fix_pr: null
fix_state: null
---

**Link do Datadog:** https://app.datadoghq.com/event/explorer?query=source%3Akubernetes%20env%3Aproduction%20status%3Awarn%20kube_namespace%3Aargocd%20OperationCompleted&from_ts=1788814356569&to_ts=1789159956569&live=false

Investigação concluída, relatório retido pelo gate de PII (email) sobre o arquivo renderizado. O texto completo ficou em reports/.quarantine/k8s-eks-medprev-online-prd-OperationCompleted-argocd.md, fora do git.

Este registro existe para dois motivos: a dedup para de reselecionar o achado (que já foi investigado e pago), e o custo continua contabilizado em `houston metrics`.

Para retomar: leia o arquivo em quarentena, decida se o achado virou issue (`state: promoted`) ou não (`state: discarded`), ou apague este registro para que o achado volte à fila de investigação.
