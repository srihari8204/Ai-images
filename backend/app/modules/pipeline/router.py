"""Generation job endpoints (async pipeline)."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sse_starlette.sse import EventSourceResponse

from app.core.dependencies import CurrentUser, DbSession, get_idempotency_key
from app.core.pagination import decode_cursor, encode_cursor
from app.core.redis import get_redis
from app.modules.pipeline import service
from app.modules.pipeline.models import JobStatus
from app.modules.pipeline.schemas import (
    JobAccepted,
    JobOut,
    JobPage,
    JobSubmitRequest,
    PackItem,
    PackRequest,
    PackResponse,
)
from app.queue.producer import estimate_wait_seconds, queue_depth

router = APIRouter(prefix="/jobs", tags=["generation"])


async def _to_out(db, job) -> JobOut:
    out = JobOut.model_validate(job)
    out.status = job.status.value
    out.result_image_ids = await service.result_image_ids(db, job.id)
    return out


@router.post(
    "",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a generation job",
)
async def submit_job(
    req: JobSubmitRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)] = None,
) -> JobAccepted:
    job = await service.submit_job(
        db,
        user,
        req,
        idempotency_key=idempotency_key,
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    depth = queue_depth()["__total__"]
    return JobAccepted(
        job_id=job.id,
        status=job.status.value,
        cost_credits=job.cost_credits,
        queue_position=depth,
        estimated_wait_seconds=estimate_wait_seconds(),
    )


@router.post(
    "/pack",
    response_model=PackResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit an avatar pack (multiple styles/variants)",
)
async def submit_pack(
    req: PackRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    idempotency_key: Annotated[str | None, Depends(get_idempotency_key)] = None,
) -> PackResponse:
    pack_id, items = await service.submit_pack(
        db,
        user,
        req,
        idempotency_key=idempotency_key,
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    jobs = [
        PackItem(
            job_id=job.id, style_slug=slug, variant=variant,
            cost_credits=job.cost_credits, status=job.status.value,
        )
        for (job, slug, variant) in items
    ]
    return PackResponse(
        pack_id=pack_id,
        total_cost_credits=sum(j.cost_credits for j in jobs),
        jobs=jobs,
    )


@router.get("", response_model=JobPage, summary="List your jobs")
async def list_jobs(
    user: CurrentUser,
    db: DbSession,
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
) -> JobPage:
    before = None
    if cursor:
        created, _ = decode_cursor(cursor)
        before = created
    jobs = await service.list_jobs(db, user.id, limit=limit + 1, before=before)
    has_more = len(jobs) > limit
    jobs = jobs[:limit]
    items = [await _to_out(db, j) for j in jobs]
    next_cursor = encode_cursor(jobs[-1].created_at, jobs[-1].id) if has_more and jobs else None
    return JobPage(items=items, next_cursor=next_cursor, has_more=has_more)


@router.get("/{job_id}", response_model=JobOut, summary="Job status / progress")
async def get_job(job_id: uuid.UUID, user: CurrentUser, db: DbSession) -> JobOut:
    job = await service.get_job(db, user.id, job_id)
    return await _to_out(db, job)


@router.post("/{job_id}/cancel", response_model=JobOut, summary="Cancel a job")
async def cancel_job(job_id: uuid.UUID, user: CurrentUser, db: DbSession) -> JobOut:
    job = await service.cancel_job(db, user.id, job_id)
    return await _to_out(db, job)


@router.get("/{job_id}/events", summary="SSE progress stream")
async def job_events(
    job_id: uuid.UUID,
    db: DbSession,
    request: Request,
    access_token: str | None = Query(None),
):
    # EventSource cannot set an Authorization header, so the SSE route also
    # accepts the access token as a query param. Resolve the user from either.
    import jwt as _jwt

    from app.core.errors import AuthError
    from app.core.security import decode_access_token

    token = access_token
    auth_header = request.headers.get("authorization")
    if not token and auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1]
    if not token:
        raise AuthError("Missing access token")
    try:
        payload = decode_access_token(token)
    except _jwt.PyJWTError as exc:
        raise AuthError("Invalid access token") from exc
    user_id = uuid.UUID(payload["sub"])

    # Authorize ownership before opening the stream.
    job = await service.get_job(db, user_id, job_id)
    channel = f"job:progress:{job_id}"
    terminal = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}

    async def event_generator():
        # Emit current state immediately.
        yield {
            "event": "status",
            "data": json.dumps({"status": job.status.value, "progress": job.progress}),
        }
        if job.status in terminal:
            return

        redis = get_redis()
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=15
                )
                if message is None:
                    yield {"event": "ping", "data": "{}"}
                    continue
                data = message["data"]
                yield {"event": "progress", "data": data}
                try:
                    payload = json.loads(data)
                    if payload.get("status") in {s.value for s in terminal}:
                        break
                except (ValueError, TypeError):
                    pass
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    return EventSourceResponse(event_generator())
