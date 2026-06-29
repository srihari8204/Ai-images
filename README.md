# AI Mirror Platform

An original, self-hosted, **API-first AI image-generation platform** built from
scratch: FLUX.1 generation with InstantID face consistency, ControlNet
conditioning, GFPGAN/RealESRGAN post-processing, a credit ledger, payments,
gallery, and an admin surface — designed to scale to millions of users.

## Architecture

Three planes that scale independently (see
[`openspec/changes/ai-mirror-platform/design.md`](openspec/changes/ai-mirror-platform/design.md)):

- **Web/API** — stateless FastAPI modular monolith behind Nginx.
- **Async compute** — GPU workers consuming a Redis queue (the AI engine).
- **Data/storage** — PostgreSQL (system of record), Redis (queue/cache/sessions),
  MinIO (objects) behind a CDN.

```
backend/     FastAPI app (13 modules: auth, users, uploads, prompts, styles,
             pipeline, generation, gallery, credits, payments, admin, monitoring)
ai-engine/   GPU worker + composable pipeline stages
frontend/    Next.js (App Router) reference client
database/    schema.sql reference + seeds
storage/     MinIO bucket policies
docker/      Compose (dev/prod/monitoring), Dockerfiles, Nginx
deploy/      Kubernetes manifests + Helm (worker autoscaling on queue depth)
monitoring/  Prometheus, Grafana dashboards, alert rules, Alertmanager
docs/        OpenAPI export, integration guide, versioning, runbooks, security
```

## Quick start (dev)

```bash
cd docker
docker compose up --build           # api, worker, postgres, redis, minio, nginx
# API:    http://localhost:8000/docs        (Swagger UI)
# Edge:   http://localhost:8080             (Nginx → API, SSE, share routes)
# MinIO:  http://localhost:9001             (console)
```

The API auto-runs migrations and seeds plans/styles/flags on start. Optionally
bring up observability:

```bash
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
# Grafana http://localhost:3001 (admin/admin), Prometheus http://localhost:9090
```

Frontend:

```bash
cd frontend && npm install && NEXT_PUBLIC_API_BASE_URL=http://localhost:8080 npm run dev
```

## Develop the backend locally

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head && python -m app.db.seed
uvicorn app.main:app --reload
pytest                              # 24 tests (ledger, auth, payments, validation, health)
```

## Key design guarantees

- **Exactly-once money/GPU semantics** — idempotency keys + DB-unique constraints;
  append-only credit ledger with row-locked balance and a `balance >= 0` CHECK.
- **Async generation** — submit returns `202` + job id; track via polling or SSE.
- **Privacy** — versioned biometric consent, EXIF stripping, NSFW screening,
  retention purge, full audit log.
- **Operability** — `/healthz` + `/readyz`, Prometheus metrics, structured JSON
  logs with correlation ids, Grafana dashboards, alert rules, runbooks.

## Documentation

- [Integration guide](docs/integration-guide.md) · [API versioning](docs/versioning.md)
- [Runbooks](docs/runbooks.md) · [Game-days](docs/gamedays.md) · [Security](docs/security.md) · [CDN](docs/cdn.md)
- Live API docs at `/docs` (Swagger) and `/redoc`; spec at [`docs/openapi.json`](docs/openapi.json).

## Spec-driven development

This platform was built against the OpenSpec change in
[`openspec/changes/ai-mirror-platform/`](openspec/changes/ai-mirror-platform/)
(proposal, design, capability specs, and the implementation task list).
