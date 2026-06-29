# API Versioning & Deprecation Policy

## Versioning

- The API is namespaced by major version in the path: `/api/v1`.
- Backwards-compatible changes (new endpoints, new optional fields, new enum
  values on output) ship within the current major version without a bump.
- Breaking changes (removing/renaming fields, changing types, changing required
  inputs, changing status-code semantics) require a new major namespace
  (`/api/v2`) served alongside the previous one.

## Deprecation

When an endpoint or field is deprecated:

1. It keeps working for the announced **sunset window** (minimum **90 days**).
2. Responses carry standard headers (RFC 8594):
   - `Deprecation: true`
   - `Sunset: <date>`
   - `Link: <successor-url>; rel="successor-version"` (when a replacement exists)
3. The OpenAPI spec marks the operation `deprecated: true` and the docs state the
   sunset date and replacement.

Implementation: add the `app.core.deprecation.deprecated(sunset=..., successor=...)`
dependency to the route.

```python
from fastapi import Depends
from app.core.deprecation import deprecated

@router.get("/legacy", dependencies=[Depends(deprecated(sunset="2026-01-01",
            successor="/api/v1/new"))])
async def legacy(): ...
```

## Compatibility guarantees

- Unknown response fields MUST be ignored by clients (forward compatibility).
- Cursor pagination tokens are opaque; do not parse them.
- Idempotency keys on money/GPU-spending endpoints are honoured for at least 24h.

## Change management

- Every route/schema change is reflected in `docs/openapi.json`, enforced in CI
  by `backend/scripts/check_openapi.py` (fails the build on drift).
