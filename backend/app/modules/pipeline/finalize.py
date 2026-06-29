"""Worker-side job finalization (synchronous).

These functions are called by the GPU worker (ai-engine) using a sync session.
They implement the check-before-charge idempotency guarantee: the same job
delivered twice converts the hold to a debit only once and never duplicates
outputs.

Progress is published to a Redis channel (``job:progress:{id}``) consumed by the
API's SSE endpoint, and persisted on the job row for pollers.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import redis as sync_redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.credits.models import CreditBalance, CreditTransaction, TxnType
from app.modules.pipeline.models import Job, JobResult, JobStatus
from app.modules.uploads.models import Image, ImageKind, SafetyStatus, Visibility

_redis = sync_redis.from_url(settings.redis_url, decode_responses=True)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def publish_progress(job_id: str, status: str, progress: int, stage: str | None = None) -> None:
    _redis.publish(
        f"job:progress:{job_id}",
        json.dumps({"status": status, "progress": progress, "stage": stage}),
    )


def is_cancel_requested(job_id: str) -> bool:
    return bool(_redis.get(f"job:cancel:{job_id}"))


# --------------------------------------------------------------------------- #
# Sync credit operations (mirror credits.service, FOR UPDATE serialized)
# --------------------------------------------------------------------------- #
def _existing_txn(db: Session, user_id: uuid.UUID, idem: str) -> CreditTransaction | None:
    return db.execute(
        select(CreditTransaction).where(
            CreditTransaction.user_id == user_id,
            CreditTransaction.idempotency_key == idem,
        )
    ).scalar_one_or_none()


def _locked_balance(db: Session, user_id: uuid.UUID) -> CreditBalance:
    row = db.execute(
        select(CreditBalance).where(CreditBalance.user_id == user_id).with_for_update()
    ).scalar_one_or_none()
    if row is None:
        row = CreditBalance(user_id=user_id, balance=0, held=0, version=0)
        db.add(row)
        db.flush()
    return row


def debit_sync(db: Session, job: Job) -> None:
    idem = f"debit:{job.idempotency_key}"
    if _existing_txn(db, job.user_id, idem):
        return
    bal = _locked_balance(db, job.user_id)
    db.add(
        CreditTransaction(
            user_id=job.user_id,
            type=TxnType.DEBIT,
            amount=-job.cost_credits,
            job_id=str(job.id),
            reason="job_debit",
            idempotency_key=idem,
        )
    )
    bal.balance -= job.cost_credits
    bal.held = max(0, bal.held - job.cost_credits)
    bal.version += 1
    db.flush()


def refund_sync(db: Session, job: Job) -> None:
    idem = f"refund:{job.idempotency_key}"
    if _existing_txn(db, job.user_id, idem):
        return
    bal = _locked_balance(db, job.user_id)
    db.add(
        CreditTransaction(
            user_id=job.user_id,
            type=TxnType.REFUND,
            amount=0,  # reservation release; balance was never reduced by the hold
            job_id=str(job.id),
            reason=f"job_refund:{job.cost_credits}",
            idempotency_key=idem,
        )
    )
    bal.held = max(0, bal.held - job.cost_credits)
    bal.version += 1
    db.flush()


# --------------------------------------------------------------------------- #
# Job lifecycle
# --------------------------------------------------------------------------- #
def claim_job(db: Session, job_id: str) -> Job | None:
    """Load the job and mark it running. Returns None if it should not run
    (already terminal, cancelled, or unknown) — the idempotency guard."""

    job = db.get(Job, uuid.UUID(job_id))
    if job is None:
        return None
    if job.status in (JobStatus.COMPLETED, JobStatus.CANCELLED, JobStatus.FAILED):
        return None  # duplicate delivery of a finished job
    if is_cancel_requested(job_id):
        return None
    job.status = JobStatus.RUNNING
    job.started_at = job.started_at or _now()
    job.attempts += 1
    db.flush()
    publish_progress(job_id, "running", job.progress)
    return job


def set_progress(db: Session, job: Job, progress: int, stage: str | None = None) -> None:
    job.progress = max(job.progress, progress)
    db.flush()
    publish_progress(str(job.id), "running", job.progress, stage)


def record_output(
    db: Session,
    job: Job,
    *,
    data: bytes,
    mime: str,
    width: int,
    height: int,
    stage: str,
    is_primary: bool,
    object_key: str,
) -> Image:
    from app.storage import object_store
    import hashlib

    object_store.put_object(settings.bucket_outputs, object_key, data, mime)
    image = Image(
        user_id=job.user_id,
        kind=ImageKind.GENERATION,
        bucket=settings.bucket_outputs,
        object_key=object_key,
        mime=mime,
        width=width,
        height=height,
        bytes=len(data),
        content_hash=hashlib.sha256(data).hexdigest(),
        safety_status=SafetyStatus.APPROVED,
        visibility=Visibility.PRIVATE,
        job_id=job.id,
    )
    db.add(image)
    db.flush()
    db.add(JobResult(job_id=job.id, image_id=image.id, stage=stage, is_primary=is_primary))
    db.flush()
    return image


def finalize_success(db: Session, job: Job, *, no_charge: bool = False) -> None:
    if not no_charge:
        debit_sync(db, job)
    job.status = JobStatus.COMPLETED
    job.progress = 100
    job.finished_at = _now()
    db.flush()
    publish_progress(str(job.id), "completed", 100)


def finalize_failure(
    db: Session,
    job: Job,
    *,
    stage: str,
    code: str,
    message: str,
    no_charge: bool = False,
) -> None:
    if not no_charge:
        refund_sync(db, job)
    job.status = JobStatus.FAILED
    job.error_stage = stage
    job.error_code = code
    job.error_message = message[:512]
    job.finished_at = _now()
    db.flush()
    publish_progress(str(job.id), "failed", job.progress, stage)


def mark_cancelled(db: Session, job: Job, *, no_charge: bool = False) -> None:
    if not no_charge:
        refund_sync(db, job)
    job.status = JobStatus.CANCELLED
    job.finished_at = _now()
    db.flush()
    publish_progress(str(job.id), "cancelled", job.progress)
