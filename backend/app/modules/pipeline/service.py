"""Pipeline job submission and lifecycle service (API side).

Submission flow (design D1, D4, D5):
1. Validate request, resolve style, compose + safety-screen the prompt.
2. Enforce consent when face-consistency (InstantID) is requested.
3. Price the job and place a credit *hold* (atomic, idempotent).
4. Create the job row and enqueue it; return ``202``.

The held amount is later converted to a debit on success or refunded on
failure/cancellation by the worker-side finalize module.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics
from app.core.config import settings
from app.core.errors import AppError, ConflictError, NotFoundError, ValidationAppError
from app.core.ids import uuid7
from app.core.logging import get_logger
from app.modules.credits import service as credits
from app.modules.pipeline.models import Job, JobResult, JobStatus
from app.modules.pipeline.pricing import price_job
from app.modules.pipeline.schemas import JobSubmitRequest
from app.modules.prompts import service as prompts
from app.modules.styles import service as styles
from app.modules.users import service as users
from app.queue.producer import Priority, cancel_job as queue_cancel, enqueue_job

logger = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _priority_for(user) -> Priority:
    plans = set((user.settings_json or {}).get("plans", []))
    if plans & {"pro", "studio", "enterprise"}:
        return Priority.HIGH
    return Priority.NORMAL


async def submit_job(
    db: AsyncSession,
    user,
    req: JobSubmitRequest,
    *,
    idempotency_key: str | None,
    correlation_id: str | None = None,
) -> Job:
    # Idempotent re-submit: same key returns the existing job.
    key = idempotency_key or str(uuid7())
    existing = (
        await db.execute(select(Job).where(Job.idempotency_key == key))
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    stages = req.validated_stages()

    # Resolve style (template, negative, params, multiplier, entitlement).
    cost_multiplier = 1.0
    template = style_negative = None
    style_id = None
    if req.style_slug:
        style = await styles.get_by_slug(db, req.style_slug)
        if style is None or not style.is_active:
            raise AppError("Unknown or inactive style", code="unknown_style", status_code=400)
        resolved = await styles.resolve_style(db, style.id, user)
        cost_multiplier = resolved["cost_multiplier"]
        template = resolved["template"]
        style_negative = resolved["negative_prompt"]
        style_id = style.id

    # Compose + screen the prompt.
    final_prompt, final_negative = prompts.compose(
        req.prompt,
        template=template,
        style_negative=style_negative,
        user_negative=req.negative_prompt,
    )
    await prompts.screen_prompt(db, user.id, final_prompt, subject_id=key)

    # Consent gate for biometric/face processing.
    if "instantid" in stages:
        if not req.reference_image_ids:
            raise ValidationAppError(
                "Face consistency requires at least one reference image"
            )
        if not await users.has_active_consent(db, user.id, "biometric"):
            raise AppError(
                "Biometric consent required for face-consistency generation",
                code="consent_required",
                status_code=403,
            )

    # Validate reference images belong to the user.
    for ref_id in req.reference_image_ids:
        from app.modules.uploads.service import get_image_for_owner

        await get_image_for_owner(db, user.id, ref_id)

    # Price + hold credits (skip charge for admin requeues handled elsewhere).
    cost = price_job(
        cost_multiplier=cost_multiplier,
        stages=stages,
        num_outputs=req.params.num_outputs,
        steps=req.params.steps,
    )

    job_id = uuid7()
    hold = await credits.hold(
        db, user.id, cost, job_id=job_id, idempotency_key=f"hold:{key}"
    )

    job = Job(
        id=job_id,
        user_id=user.id,
        idempotency_key=key,
        style_id=style_id,
        status=JobStatus.QUEUED,
        cost_credits=cost,
        hold_txn_id=hold.id,
        prompt=final_prompt,
        negative_prompt=final_negative,
        seed=req.seed,
        params=req.params.model_dump(),
        stages=stages,
        reference_image_ids=[str(r) for r in req.reference_image_ids],
        priority=int(await _priority_for(user)),
    )
    db.add(job)
    await db.flush()

    # Enqueue after the row is persisted so the worker always finds it.
    enqueue_job(
        str(job.id),
        {"job_id": str(job.id)},
        priority=Priority(job.priority),
        correlation_id=correlation_id,
    )
    metrics.jobs_submitted_total.inc()
    logger.info("job_submitted", job_id=str(job.id), cost=cost, stages=stages)
    return job


async def submit_pack(
    db: AsyncSession,
    user,
    req,
    *,
    idempotency_key: str | None,
    correlation_id: str | None = None,
) -> tuple[str, list[tuple[Job, str, int]]]:
    """Submit an avatar pack: one job per (style × variant).

    Each job is priced and credit-held independently and is fully idempotent on a
    per-item key derived from the pack key, so a retried pack request never
    double-charges. Returns ``(pack_id, [(job, style_slug, variant), ...])``.
    """

    from app.modules.pipeline.schemas import JobSubmitRequest

    pack_id = idempotency_key or str(uuid7())
    out: list[tuple[Job, str, int]] = []
    for slug in req.style_slugs:
        for variant in range(req.variants_per_style):
            item_req = JobSubmitRequest(
                prompt=req.prompt,
                negative_prompt=req.negative_prompt,
                style_slug=slug,
                stages=list(req.stages),
                reference_image_ids=list(req.reference_image_ids),
                params=req.params,
            )
            job = await submit_job(
                db,
                user,
                item_req,
                idempotency_key=f"pack:{pack_id}:{slug}:{variant}",
                correlation_id=correlation_id,
            )
            out.append((job, slug, variant))
    logger.info("pack_submitted", pack_id=pack_id, jobs=len(out))
    return pack_id, out


async def get_job(db: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID) -> Job:
    job = (
        await db.execute(
            select(Job).where(Job.id == job_id, Job.user_id == user_id)
        )
    ).scalar_one_or_none()
    if job is None:
        raise NotFoundError("Job not found")
    return job


async def result_image_ids(db: AsyncSession, job_id: uuid.UUID) -> list[str]:
    rows = (
        await db.execute(select(JobResult.image_id).where(JobResult.job_id == job_id))
    ).scalars().all()
    return [str(r) for r in rows]


async def list_jobs(
    db: AsyncSession, user_id: uuid.UUID, *, limit: int, before: datetime | None
) -> list[Job]:
    stmt = (
        select(Job)
        .where(Job.user_id == user_id)
        .order_by(Job.created_at.desc())
        .limit(limit)
    )
    if before:
        stmt = stmt.where(Job.created_at < before)
    return list((await db.execute(stmt)).scalars().all())


async def cancel_job(
    db: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID, *, by_admin: bool = False
) -> Job:
    job = (
        await db.execute(select(Job).where(Job.id == job_id))
    ).scalar_one_or_none()
    if job is None:
        raise NotFoundError("Job not found")
    if not by_admin and job.user_id != user_id:
        raise NotFoundError("Job not found")
    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        raise ConflictError(
            "Job already finished", details={"status": job.status.value}
        )

    # Signal the worker to stop, then refund the hold exactly once.
    queue_cancel(str(job.id))
    job.status = JobStatus.CANCELLED
    job.finished_at = _now()
    await credits.refund_hold(
        db,
        job.user_id,
        job.cost_credits,
        job_id=job.id,
        idempotency_key=f"refund:{job.idempotency_key}",
    )
    metrics.jobs_completed_total.labels(status="cancelled").inc()
    logger.info("job_cancelled", job_id=str(job.id), by_admin=by_admin)
    return job
