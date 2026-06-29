# Failure Game-Days

Run these chaos drills in staging before production launch and quarterly after.
Each lists the injection, the expected behaviour, and the pass criteria.

## 1. Payment webhook retries / duplicates
- **Inject**: replay the same `payment_succeeded` event 3×; send an out-of-order
  refund before its purchase.
- **Expect**: credits granted exactly once (dedup by `provider_event_id`); refund
  records a reversing ledger entry; balance reconciles.
- **Pass**: ledger sum == derived balance; no double-credit; audit entries present.

## 2. GPU / worker outage
- **Inject**: kill all worker pods mid-job; or simulate `has_capacity()=False`.
- **Expect**: jobs stay `queued` (not dropped); no-capacity re-enqueues with delay;
  on worker return, jobs resume; idempotency prevents double-charge.
- **Pass**: no lost jobs; no double debit; queue drains after recovery.

## 3. Database failover
- **Inject**: fail over Postgres primary (or restart it).
- **Expect**: `/readyz` flips to 503; LB stops routing; requests fail cleanly with
  the error envelope; recovery restores readiness. In-flight credit transactions
  either commit fully or roll back (atomic).
- **Pass**: no partial credit writes; no negative balances; readiness recovers.

## 4. Redis outage
- **Inject**: stop Redis.
- **Expect**: `/readyz` 503; new submissions fail cleanly; rate-limit/denylist
  degrade safely. On recovery, `queued`/`running` jobs are re-enqueued from the DB.
- **Pass**: no double-processing (idempotency keys hold); queue resumes.

## 5. Object storage (MinIO) outage
- **Inject**: stop MinIO.
- **Expect**: uploads/outputs fail with clear errors; `/readyz` 503; jobs needing
  storage fail and **refund** the hold.
- **Pass**: failed jobs refund credits exactly once; users not charged for losses.

## 6. Deploy rollback drill
- **Inject**: deploy a deliberately broken image.
- **Expect**: readiness probe fails → rollout blocked / `rollout undo` restores
  previous version with zero data loss.
- **Pass**: recovery < 5 min; no migration corruption (downgrade tested).

## Recording
Capture timings (detection → mitigation → recovery), gaps found, and follow-up
actions. Feed alert-threshold tuning back into `monitoring/prometheus/alerts.yml`.
