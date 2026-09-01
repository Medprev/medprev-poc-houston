# medprev-poc-houston

PoC: investiga sinais do Datadog (Error Tracking, Monitors, Kubernetes events) e produz
laudo versionado com evidência reconferível. Um `claude -p` por achado, sem acesso de
escrita ao disco — todo laudo passa pelo gate de PII antes de chegar em `reports/`.

## Setup

```
cp .env.example .env
# preencher DD_API_KEY e DD_APP_KEY (escopo de leitura) e DD_SITE
```

## Origin

Derived from the Vigília architecture document, "Versão mínima" tab.
