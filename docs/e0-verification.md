# E0 — verificação do schema do Error Tracking

Verificado em 2026-09-01 contra a conta de produção, via REST v2 direto (chave de escopo
de leitura) e cruzado com o OpenAPI oficial (`datadog-api-client-go`, `.generator/schemas/v2/openapi.yaml`).

## Resultado

- `GET /api/v1/validate` → HTTP 200, `{"valid": true}`.
- `first_seen` existe no objeto de issue. Epoch em **milissegundos**, não string relativa.
- `is_regression` **não existe**. O campo é `regression`: objeto com `resolved_at`,
  `regressed_at`, `regressed_at_version`, presente só quando a issue foi resolvida e
  reaberta. Ausência (`null`) = nunca regrediu. Mais informação que um booleano, de graça.
- A busca é **dois passos**, não um:
  1. `POST /api/v2/error-tracking/issues/search` — corpo `{"data":{"type":"search_request","attributes":{"query","track","from","to"}}}`.
     Devolve só `id` + `total_count` por resultado (tipo `error_tracking_search_result`).
  2. `GET /api/v2/error-tracking/issues/{issue_id}` — devolve os atributos completos,
     incluindo `first_seen` e `regression`.
  O coletor faz N+1 chamadas por janela: 1 busca + 1 detalhe por achado novo (não por
  achado total — achados já vistos são descartados pela dedup antes do detalhe).
- `track` é enum fechado: `trace` | `logs` | `rum`. Não aceita valor livre por ambiente/serviço.

## Exemplo real

Issue `114e7438-e897-11ef-83c4-da7ad0900002` (o mesmo prefixo do fingerprint de exemplo
`et-114e7438` já citado no plano): `error_type: ProfessionalNotFoundException`,
`service: medprev-rest-api`, `regression.regressed_at: 2025-11-10T20:03:03.256Z`.

## Fonte

`DataDog/datadog-api-client-go`, `.generator/schemas/v2/openapi.yaml`, schemas
`IssueAttributes`, `IssueRegression`, `IssuesSearchRequestData*`.
