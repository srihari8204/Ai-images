# AI Mirror Platform — Documentation

API-first, self-hosted AI image-generation platform.

## Contents

- [Local Testing (no GPU)](local-testing.md) — unit tests, full-stack smoke test, browser walkthrough.
- [GPU Deployment](gpu-deployment.md) — switch from CPU stand-ins to real FLUX/InstantID/ControlNet on GPU.
- [Production Configuration](production-config.md) — Stripe, OAuth, SMTP, limits, launch checklist.
- [Integration Guide](integration-guide.md) — auth, upload, generate, poll, gallery.
- [Versioning & Deprecation Policy](versioning.md)
- [Operations Runbooks](runbooks.md) — deploy, scale, incident, backup/restore.
- [Security Overview](security.md) — secrets, PII retention, rate limits, audit.
- [`openapi.json`](openapi.json) — generated OpenAPI 3.1 spec (kept in sync via CI).

## Live API docs

When the API is running:

- Swagger UI: `GET /docs`
- ReDoc: `GET /redoc`
- Raw spec: `GET /openapi.json`

All product endpoints are namespaced under `/api/v1`. Authentticate by sending
`Authorization: Bearer <access_token>`; obtain tokens from `/api/v1/auth/login`.

## Error envelope

Every error uses a single envelope:

```json
{ "error": { "code": "insufficient_credits", "message": "...", "details": {} } }
```

## Architecture

Three independently-scaling planes:

- **Web/API** — stateless FastAPI behind Nginx (auth, validation, pricing, orchestration).
- **Async compute** — GPU workers consuming a Redis queue (FLUX.1 + InstantID + ControlNet + GFPGAN/RealESRGAN/bg-removal).
- **Data/storage** — PostgreSQL (system of record), Redis (queue/cache/sessions), MinIO (objects) behind a CDN.

See [`../openspec/changes/ai-mirror-platform/design.md`](../openspec/changes/ai-mirror-platform/design.md) for the full design.
