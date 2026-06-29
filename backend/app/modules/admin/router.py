"""Admin dashboard endpoints (role: admin / moderator)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import DbSession, require_admin, require_staff
from app.modules.admin import service
from app.modules.admin.schemas import (
    AdminJobOut,
    AdminUserOut,
    FlagOut,
    FlagUpdateRequest,
    GrantCreditsRequest,
    ModerationDecisionRequest,
    ModerationEventOut,
    SuspendRequest,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _parse_range(start: str | None, end: str | None) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    e = datetime.fromisoformat(end) if end else now
    s = datetime.fromisoformat(start) if start else (e - timedelta(days=30))
    return s, e


# ---- Users ----
@router.get("/users", response_model=list[AdminUserOut], summary="Search users")
async def search_users(
    db: DbSession,
    admin=Depends(require_staff),
    q: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[AdminUserOut]:
    users = await service.search_users(db, query=q, limit=limit, offset=offset)
    return [
        AdminUserOut(
            id=u.id, email=u.email, display_name=u.display_name,
            status=u.status.value, roles=u.role_names, created_at=u.created_at,
        )
        for u in users
    ]


@router.get("/users/{user_id}", response_model=AdminUserOut, summary="User detail")
async def get_user(user_id: uuid.UUID, db: DbSession, admin=Depends(require_staff)) -> AdminUserOut:
    u = await service.get_user(db, user_id)
    return AdminUserOut(
        id=u.id, email=u.email, display_name=u.display_name,
        status=u.status.value, roles=u.role_names, created_at=u.created_at,
    )


@router.post("/users/{user_id}/suspend", response_model=AdminUserOut, summary="Suspend user")
async def suspend_user(
    user_id: uuid.UUID, req: SuspendRequest, db: DbSession, admin=Depends(require_admin)
) -> AdminUserOut:
    u = await service.suspend_user(db, admin.id, user_id, req.suspend)
    return AdminUserOut(
        id=u.id, email=u.email, display_name=u.display_name,
        status=u.status.value, roles=u.role_names, created_at=u.created_at,
    )


@router.post("/users/{user_id}/credits", summary="Grant credits to a user")
async def grant_credits(
    user_id: uuid.UUID, req: GrantCreditsRequest, db: DbSession, admin=Depends(require_admin)
) -> dict:
    await service.grant_user_credits(db, admin.id, user_id, req.amount, req.reason)
    return {"message": "Credits granted", "amount": req.amount}


# ---- Jobs ----
@router.get("/jobs", response_model=list[AdminJobOut], summary="Inspect jobs")
async def list_jobs(
    db: DbSession,
    admin=Depends(require_staff),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[AdminJobOut]:
    jobs = await service.list_jobs(db, status_filter=status, limit=limit, offset=offset)
    return [AdminJobOut.model_validate(j) for j in jobs]


@router.post("/jobs/{job_id}/requeue", response_model=AdminJobOut, summary="Requeue (no re-charge)")
async def requeue_job(
    job_id: uuid.UUID, db: DbSession, admin=Depends(require_admin)
) -> AdminJobOut:
    job = await service.requeue_job(db, admin.id, job_id)
    return AdminJobOut.model_validate(job)


@router.post("/jobs/{job_id}/cancel", response_model=AdminJobOut, summary="Cancel a job")
async def cancel_job(
    job_id: uuid.UUID, db: DbSession, admin=Depends(require_admin)
) -> AdminJobOut:
    job = await service.admin_cancel_job(db, admin.id, job_id)
    return AdminJobOut.model_validate(job)


# ---- Reports ----
@router.get("/reports/revenue", summary="Revenue report")
async def revenue_report(
    db: DbSession,
    admin=Depends(require_staff),
    start: str | None = Query(None),
    end: str | None = Query(None),
) -> dict:
    s, e = _parse_range(start, end)
    return await service.revenue_report(db, s, e)


@router.get("/reports/usage", summary="Usage report")
async def usage_report(
    db: DbSession,
    admin=Depends(require_staff),
    start: str | None = Query(None),
    end: str | None = Query(None),
) -> dict:
    s, e = _parse_range(start, end)
    return await service.usage_report(db, s, e)


# ---- Moderation ----
@router.get("/moderation", response_model=list[ModerationEventOut], summary="Moderation queue")
async def moderation_queue(
    db: DbSession,
    admin=Depends(require_staff),
    decision: str | None = Query("pending"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[ModerationEventOut]:
    events = await service.list_moderation(db, decision=decision, limit=limit, offset=offset)
    return [ModerationEventOut.model_validate(ev) for ev in events]


@router.post(
    "/moderation/{event_id}/decision",
    response_model=ModerationEventOut,
    summary="Approve/reject flagged content",
)
async def decide_moderation(
    event_id: uuid.UUID,
    req: ModerationDecisionRequest,
    db: DbSession,
    admin=Depends(require_staff),
) -> ModerationEventOut:
    ev = await service.decide_moderation(db, admin.id, event_id, req.decision)
    return ModerationEventOut.model_validate(ev)


# ---- Feature flags ----
@router.get("/flags", response_model=list[FlagOut], summary="List feature flags")
async def list_flags(db: DbSession, admin=Depends(require_admin)) -> list[FlagOut]:
    return [FlagOut.model_validate(f) for f in await service.list_flags(db)]


@router.put("/flags/{key}", response_model=FlagOut, summary="Set a feature flag")
async def set_flag(
    key: str, req: FlagUpdateRequest, db: DbSession, admin=Depends(require_admin)
) -> FlagOut:
    flag = await service.set_flag(db, admin.id, key, req.value, req.description)
    return FlagOut.model_validate(flag)
