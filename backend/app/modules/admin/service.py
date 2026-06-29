"""Admin domain service: audit, moderation, users, jobs, reports, flags."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.modules.admin.models import AuditLog, FeatureFlag, ModerationEvent
from app.modules.credits.models import CreditTransaction, TxnType
from app.modules.payments.models import Payment, PaymentKind
from app.modules.pipeline.models import Job, JobStatus
from app.modules.users.models import User, UserStatus

logger = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Audit & moderation (called across modules)
# --------------------------------------------------------------------------- #
async def record_audit(
    db: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    metadata: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        metadata_json=metadata or {},
    )
    db.add(entry)
    await db.flush()
    return entry


async def record_moderation_event(
    db: AsyncSession,
    *,
    subject_type: str,
    subject_id: str | None,
    classifier: str,
    score: float | None,
    decision: str,
    user_id: uuid.UUID | None = None,
    detail: str | None = None,
) -> ModerationEvent:
    event = ModerationEvent(
        subject_type=subject_type,
        subject_id=subject_id,
        user_id=user_id,
        classifier=classifier,
        score=score,
        decision=decision,
        detail=detail,
    )
    db.add(event)
    await db.flush()
    logger.info(
        "moderation_event",
        subject_type=subject_type,
        decision=decision,
        classifier=classifier,
    )
    return event


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #
async def search_users(
    db: AsyncSession, *, query: str | None, limit: int, offset: int
) -> list[User]:
    stmt = select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
    if query:
        stmt = stmt.where(func.lower(User.email).like(f"%{query.lower()}%"))
    return list((await db.execute(stmt)).scalars().all())


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    return user


async def suspend_user(
    db: AsyncSession, admin_id: uuid.UUID, user_id: uuid.UUID, suspend: bool
) -> User:
    from app.modules.auth.service import revoke_all_sessions

    user = await get_user(db, user_id)
    user.status = UserStatus.SUSPENDED if suspend else UserStatus.ACTIVE
    if suspend:
        await revoke_all_sessions(db, user.id)
    await record_audit(
        db,
        actor_id=admin_id,
        action="user.suspend" if suspend else "user.reinstate",
        target_type="user",
        target_id=str(user_id),
    )
    return user


async def grant_user_credits(
    db: AsyncSession, admin_id: uuid.UUID, user_id: uuid.UUID, amount: int, reason: str
) -> None:
    from app.modules.credits import service as credits

    await get_user(db, user_id)
    await credits.grant(
        db,
        user_id,
        amount,
        reason=f"admin_grant:{reason}",
        idempotency_key=f"admin:{admin_id}:{user_id}:{_now().timestamp()}",
    )
    await record_audit(
        db,
        actor_id=admin_id,
        action="user.credits_grant",
        target_type="user",
        target_id=str(user_id),
        metadata={"amount": amount, "reason": reason},
    )


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #
async def list_jobs(
    db: AsyncSession, *, status_filter: str | None, limit: int, offset: int
) -> list[Job]:
    stmt = select(Job).order_by(Job.created_at.desc()).limit(limit).offset(offset)
    if status_filter:
        stmt = stmt.where(Job.status == JobStatus(status_filter))
    return list((await db.execute(stmt)).scalars().all())


async def requeue_job(db: AsyncSession, admin_id: uuid.UUID, job_id: uuid.UUID) -> Job:
    """Create a new attempt without re-charging the user, linked to the original."""

    from app.core.ids import uuid7
    from app.queue.producer import enqueue_job

    original = await db.get(Job, job_id)
    if original is None:
        raise NotFoundError("Job not found")

    clone = Job(
        id=uuid7(),
        user_id=original.user_id,
        idempotency_key=f"requeue:{original.id}:{uuid7()}",
        style_id=original.style_id,
        status=JobStatus.QUEUED,
        cost_credits=0,  # no re-charge
        prompt=original.prompt,
        negative_prompt=original.negative_prompt,
        seed=original.seed,
        params=original.params,
        stages=original.stages,
        reference_image_ids=original.reference_image_ids,
        priority=original.priority,
        requeued_from=original.id,
    )
    db.add(clone)
    await db.flush()
    enqueue_job(
        str(clone.id),
        {"job_id": str(clone.id), "no_charge": True},
    )
    await record_audit(
        db,
        actor_id=admin_id,
        action="job.requeue",
        target_type="job",
        target_id=str(job_id),
        metadata={"clone_id": str(clone.id)},
    )
    return clone


async def admin_cancel_job(db: AsyncSession, admin_id: uuid.UUID, job_id: uuid.UUID) -> Job:
    from app.modules.pipeline import service as pipeline

    job = await db.get(Job, job_id)
    if job is None:
        raise NotFoundError("Job not found")
    await pipeline.cancel_job(db, job.user_id, job_id, by_admin=True)
    await record_audit(
        db,
        actor_id=admin_id,
        action="job.cancel",
        target_type="job",
        target_id=str(job_id),
    )
    return await db.get(Job, job_id)


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #
async def revenue_report(db: AsyncSession, start: datetime, end: datetime) -> dict:
    purchases = (
        await db.execute(
            select(func.coalesce(func.sum(Payment.amount_cents), 0)).where(
                Payment.kind == PaymentKind.PURCHASE,
                Payment.created_at >= start,
                Payment.created_at < end,
            )
        )
    ).scalar_one()
    refunds = (
        await db.execute(
            select(func.coalesce(func.sum(Payment.amount_cents), 0)).where(
                Payment.kind.in_([PaymentKind.REFUND, PaymentKind.CHARGEBACK]),
                Payment.created_at >= start,
                Payment.created_at < end,
            )
        )
    ).scalar_one()
    credits_used = (
        await db.execute(
            select(func.coalesce(func.sum(func.abs(CreditTransaction.amount)), 0)).where(
                CreditTransaction.type == TxnType.DEBIT,
                CreditTransaction.created_at >= start,
                CreditTransaction.created_at < end,
            )
        )
    ).scalar_one()
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "gross_revenue_cents": int(purchases),
        "refunds_cents": int(refunds),
        "net_revenue_cents": int(purchases) - int(refunds),
        "credits_consumed": int(credits_used),
    }


async def usage_report(db: AsyncSession, start: datetime, end: datetime) -> dict:
    total_jobs = (
        await db.execute(
            select(func.count(Job.id)).where(
                Job.created_at >= start, Job.created_at < end
            )
        )
    ).scalar_one()
    completed = (
        await db.execute(
            select(func.count(Job.id)).where(
                Job.created_at >= start,
                Job.created_at < end,
                Job.status == JobStatus.COMPLETED,
            )
        )
    ).scalar_one()
    active_users = (
        await db.execute(
            select(func.count(func.distinct(Job.user_id))).where(
                Job.created_at >= start, Job.created_at < end
            )
        )
    ).scalar_one()
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total_jobs": int(total_jobs),
        "completed_jobs": int(completed),
        "active_users": int(active_users),
    }


# --------------------------------------------------------------------------- #
# Moderation queue
# --------------------------------------------------------------------------- #
async def list_moderation(
    db: AsyncSession, *, decision: str | None, limit: int, offset: int
) -> list[ModerationEvent]:
    stmt = (
        select(ModerationEvent)
        .order_by(ModerationEvent.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if decision:
        stmt = stmt.where(ModerationEvent.decision == decision)
    return list((await db.execute(stmt)).scalars().all())


async def decide_moderation(
    db: AsyncSession, moderator_id: uuid.UUID, event_id: uuid.UUID, decision: str
) -> ModerationEvent:
    event = await db.get(ModerationEvent, event_id)
    if event is None:
        raise NotFoundError("Moderation event not found")
    event.decision = decision
    event.moderator_id = moderator_id
    event.decided_at = _now()

    if decision == "rejected" and event.subject_type in ("upload", "output") and event.subject_id:
        from app.modules.uploads.models import Image, SafetyStatus

        try:
            image = await db.get(Image, uuid.UUID(event.subject_id))
            if image is not None:
                image.safety_status = SafetyStatus.QUARANTINED
                image.deleted_at = _now()
        except (ValueError, Exception):  # noqa: BLE001
            pass

    await record_audit(
        db,
        actor_id=moderator_id,
        action=f"moderation.{decision}",
        target_type=event.subject_type,
        target_id=event.subject_id,
    )
    return event


# --------------------------------------------------------------------------- #
# Feature flags
# --------------------------------------------------------------------------- #
async def list_flags(db: AsyncSession) -> list[FeatureFlag]:
    return list((await db.execute(select(FeatureFlag))).scalars().all())


async def set_flag(
    db: AsyncSession, admin_id: uuid.UUID, key: str, value: dict, description: str | None
) -> FeatureFlag:
    flag = await db.get(FeatureFlag, key)
    if flag is None:
        flag = FeatureFlag(key=key, value=value, description=description, updated_by=admin_id)
        db.add(flag)
    else:
        flag.value = value
        if description is not None:
            flag.description = description
        flag.updated_by = admin_id
    await db.flush()
    await record_audit(
        db,
        actor_id=admin_id,
        action="flag.set",
        target_type="feature_flag",
        target_id=key,
        metadata={"value": value},
    )
    return flag


async def get_flag(db: AsyncSession, key: str, default: dict | None = None) -> dict:
    flag = await db.get(FeatureFlag, key)
    return flag.value if flag else (default or {})
