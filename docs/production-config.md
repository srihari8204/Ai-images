# Production Configuration

Everything below is **config / secrets**, not code. Set via env (K8s Secret /
ConfigMap, or `docker-compose.prod.yml`). See `backend/.env.example` for the full
list and `app/core/config.py` for defaults.

## Core (required)

| Var | Notes |
|-----|-------|
| `ENVIRONMENT` | `prod` |
| `SECRET_KEY` | Long random string; rotates JWT signing. **Required.** |
| `PUBLIC_BASE_URL` / `FRONTEND_BASE_URL` | Your real domains |
| `CORS_ORIGINS` | Comma-separated allowed origins |
| `DATABASE_URL` | Managed Postgres DSN (`postgresql+asyncpg://...`) |
| `REDIS_URL` | Managed Redis |
| `S3_ENDPOINT_URL` / `S3_PUBLIC_ENDPOINT_URL` | MinIO/S3 internal + CDN URL |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | Object storage creds |

## Payments (Stripe) — go live

1. Create products/prices in Stripe; set each plan's `provider_price_id` (DB `plans`).
2. Set `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`.
3. Point a Stripe webhook at `https://<domain>/webhooks/payments` for events:
   `checkout.session.completed`, `charge.refunded`, `charge.dispute.created`.
4. With `STRIPE_SECRET_KEY` set, the platform uses the **real** Stripe provider
   (the mock provider is only used when it's blank).

`PAYMENTS_ALLOW_NEGATIVE_BALANCE` controls whether refunds/chargebacks may
overdraw (default true; ledger always records the full reversal).

## OAuth (Google / Apple)

| Var | |
|-----|--|
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth credentials |
| `APPLE_CLIENT_ID` / `APPLE_CLIENT_SECRET` | Apple Sign-in |

Redirect URI to register: `https://<domain>/api/v1/auth/oauth/{provider}/callback`.
Providers with blank creds are disabled (return 503), the rest keep working.

## Email (SMTP)

Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`. With
`SMTP_HOST` blank, verification/reset emails are **logged** (dev only) — set it in
prod so users actually receive them.

## Generation (GPU)

See [gpu-deployment.md](gpu-deployment.md). Key vars: `GENERATION_BACKEND=flux`,
`TORCH_DEVICE=cuda`, `ENABLE_NSFW_MODEL=true`, model refs, `HF_TOKEN`.

## Limits & retention

| Var | Default | |
|-----|---------|--|
| `UPLOAD_MAX_BYTES` | 25 MB | max upload size |
| `MAX_STEPS` / `MAX_RESOLUTION` | 50 / 1536 | generation bounds |
| `JOB_MAX_RETRIES` | 3 | transient retry limit |
| `NSFW_THRESHOLD` | 0.85 | block threshold |
| `PURGE_RETENTION_DAYS` | 30 | hard-purge window for deleted data |
| `RATE_LIMIT_AUTH_PER_IP` / `_PER_ACCOUNT` | 20 / 10 per 5 min | auth throttle |

## Scheduled maintenance

Run the retention purge regularly (e.g. a daily k8s CronJob or RQ scheduler):

```bash
python -c "from ai_engine.tasks import purge_expired; purge_expired()"
```

## Pre-launch checklist

- [ ] `SECRET_KEY` set to a strong secret (not the dev default)
- [ ] DB migrated (`alembic upgrade head`) and seeded (`python -m app.db.seed`)
- [ ] Stripe live keys + webhook configured and tested
- [ ] OAuth + SMTP configured
- [ ] GPU workers up with weights mounted; a test job completes in seconds
- [ ] `ENABLE_NSFW_MODEL=true`; moderation queue reachable
- [ ] TLS at the edge; `/metrics` not publicly exposed
- [ ] Purge CronJob scheduled
- [ ] Backups for Postgres + object storage
- [ ] See [security.md](security.md) review checklist
