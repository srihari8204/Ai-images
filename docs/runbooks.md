# Operator Runbooks

Concise, actionable procedures for running AI Mirror in production.

## Deploy

1. CI builds and pushes `api` and `worker` images tagged with the commit SHA.
2. `kubectl set image deploy/api api=ghcr.io/aimirror/api:<sha> -n ai-mirror`
   (or `helm upgrade ai-mirror deploy/helm --set image.tag=<sha>`).
3. The API runs `alembic upgrade head` on start (idempotent). Migrations are
   forward-only; the latest step ships a paired downgrade.
4. Watch rollout: `kubectl rollout status deploy/api -n ai-mirror`.
5. Verify: `curl https://app.aimirror.example/readyz` → `{"ready": true}`.

### Rollback
`kubectl rollout undo deploy/api -n ai-mirror` (and/or `deploy/worker`). API and
worker are stateless; roll back independently. If a migration must be reverted,
`alembic downgrade -1` (only the latest step has a down-script).

## Scale

- **API**: HPA scales on CPU (3→20). Manual: `kubectl scale deploy/api --replicas=N`.
- **Workers**: KEDA scales on queue depth (`queue_depth` / Redis list length).
  Manual override: `kubectl scale deploy/worker --replicas=N`.
- **Priority tiers**: paid plans enqueue to `generation-high`, drained first.
  Tune KEDA `listLength` thresholds to trade latency vs GPU cost.

## Incident: high error rate
1. Check the Grafana "Platform Overview" → error rate & p95 panels.
2. `kubectl logs -l app=api -n ai-mirror --tail=200` (filter by `correlation_id`).
3. If a dependency is down, `/readyz` will be 503 and traffic stops routing —
   restore Postgres/Redis/MinIO. Workers retry transient failures with backoff.

## Incident: queue backlog
1. Alert `QueueBacklog` fires when depth > 200 for 10m.
2. Confirm workers are processing: `worker_jobs_processed_total` rate > 0.
3. Scale workers (KEDA usually handles this); check GPU saturation panel.
4. If stalled (work present, zero processing) → restart workers; inspect
   `worker_stage_failures_total`.

## Incident: payment/webhook failures
1. Alert `PaymentFailures`. Inspect `payments_total{status="failed"}`.
2. Webhooks are idempotent (dedup by `provider_event_id`) and **replayable** from
   the provider dashboard — re-send failed events; duplicates are safe.
3. Reconcile credits from the append-only ledger if needed.

## Backup & restore
- **Postgres**: nightly `pg_dump` / managed snapshots. Restore: provision DB,
  restore dump, `alembic current` to confirm head.
- **MinIO**: bucket replication or `mc mirror` to a backup target; lifecycle
  rules expire `exports` after 7 days.
- **Redis**: queue/cache only (ephemeral). On loss, in-flight jobs are recovered
  by re-enqueue from `jobs` rows in `queued`/`running` state; idempotency keys
  prevent double-charge.

## Routine maintenance
- Retention purge: schedule `ai_engine.tasks.purge_expired` (e.g. daily) to hard-
  delete soft-deleted images/PII past `PURGE_RETENTION_DAYS`.
- Rotate `SECRET_KEY` with overlap (accept old+new) to avoid mass logout.
