# Local Testing (no GPU)

The pipeline stages degrade to deterministic CPU stand-ins when the GPU stack is
absent, so the **entire async path runs locally** — submit → worker → output →
credit debit. Swap in real models later by uncommenting the GPU deps in
`ai-engine/requirements.txt` and mounting weights; no code changes needed.

There are three levels of local testing.

## 1. Unit tests (no services needed)

Runs against in-memory SQLite. Covers ledger invariants, auth/refresh-reuse,
payment-webhook idempotency, image validation, and readiness probes.

```bash
cd backend
pip install -r requirements.txt
PYTHONPATH=. pytest            # 24 tests
```

## 2. Full stack end-to-end (Docker)

Brings up api, worker, postgres, redis, minio, nginx. The worker runs on CPU.

```bash
cd docker
docker compose up --build -d

# create a verified user with credits (skips email verification in dev)
docker compose exec api python -m app.db.bootstrap \
    --email dev@local --password Str0ngPassw0rd --credits 100 --admin

# run the end-to-end smoke test against the edge
cd ../backend
python scripts/smoke_e2e.py --base http://localhost:8080 \
    --email dev@local --password Str0ngPassw0rd
```

Expected tail:

```
[ok] job completed with 1 output(s)
[ok] gallery has 1 image(s); first url: http://localhost:9000/outputs/...
PASS — full local generation path works (no GPU).
```

What the smoke test proves: liveness/readiness, login, credit balance, style
catalog, async job submit (202), worker execution through multiple stages,
progress to completion, output stored in MinIO + visible in the gallery via a
presigned URL, and credits debited by exactly the job cost.

### Try it in the browser
```bash
cd frontend && npm install
NEXT_PUBLIC_API_BASE_URL=http://localhost:8080 npm run dev   # http://localhost:3000
```
Log in as `dev@local` / `Str0ngPassw0rd`, open **Studio**, generate, and watch
live SSE progress; results appear in **Gallery**. The admin user can open **Admin**.

## 3. Backend without Docker

If you run Postgres/Redis/MinIO yourself (or via the compose `postgres redis
minio` services only):

```bash
cd backend
cp .env.example .env                     # point DATABASE_URL/REDIS_URL/S3_* at your services
alembic upgrade head && python -m app.db.seed
python -m app.db.bootstrap --credits 100 --admin

# terminal 1 — API
uvicorn app.main:app --reload
# terminal 2 — worker (CPU)
cd ../ai-engine && PYTHONPATH=../backend:. python -m ai_engine.worker

python scripts/smoke_e2e.py --base http://localhost:8000
```

## Load test (optional)

```bash
python scripts/loadtest.py --base http://localhost:8080 --users 20 --jobs 5
```

## Tips
- Email verification/reset links are printed to the API logs in dev (no SMTP):
  `docker compose logs -f api`.
- Payments use a built-in signed mock provider when `STRIPE_SECRET_KEY` is unset.
- If `smoke_e2e` reports the job never completes, check the worker is up:
  `docker compose logs -f worker`.
- `GET /readyz` shows which dependency is down if startup fails.
