"""User domain service: profile, settings, consent, export, deletion."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.modules.users.models import Consent, DataExport, User, UserStatus

logger = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def update_profile(
    db: AsyncSession, user: User, *, display_name=None, locale=None, avatar_image_id=None
) -> User:
    if display_name is not None:
        user.display_name = display_name
    if locale is not None:
        user.locale = locale
    if avatar_image_id is not None:
        user.avatar_image_id = avatar_image_id
    await db.flush()
    return user


async def update_settings(db: AsyncSession, user: User, new_settings: dict) -> dict:
    merged = {**(user.settings_json or {}), **new_settings}
    user.settings_json = merged
    await db.flush()
    return merged


# --------------------------------------------------------------------------- #
# Consent
# --------------------------------------------------------------------------- #
async def record_consent(
    db: AsyncSession, user: User, type_: str, version: str, granted: bool
) -> Consent:
    consent = Consent(
        user_id=user.id,
        type=type_,
        version=version,
        granted_at=_now() if granted else None,
        revoked_at=None if granted else _now(),
    )
    db.add(consent)
    await db.flush()
    logger.info("consent_recorded", user_id=str(user.id), type=type_, granted=granted)
    return consent


async def has_active_consent(db: AsyncSession, user_id: uuid.UUID, type_: str) -> bool:
    """True if the user has a current, non-revoked consent of the given type."""

    row = (
        await db.execute(
            select(Consent)
            .where(Consent.user_id == user_id, Consent.type == type_)
            .order_by(Consent.created_at.desc())
        )
    ).scalars().first()
    return bool(row and row.granted_at is not None and row.revoked_at is None)


async def list_consents(db: AsyncSession, user_id: uuid.UUID) -> list[Consent]:
    return list(
        (
            await db.execute(
                select(Consent)
                .where(Consent.user_id == user_id)
                .order_by(Consent.created_at.desc())
            )
        )
        .scalars()
        .all()
    )


# --------------------------------------------------------------------------- #
# Export & deletion
# --------------------------------------------------------------------------- #
async def request_export(db: AsyncSession, user: User) -> DataExport:
    export = DataExport(user_id=user.id, status="pending")
    db.add(export)
    await db.flush()
    # Enqueue async archive build (handled by the worker / a scheduled task).
    from app.queue.producer import _connection
    from rq import Queue

    Queue("maintenance", connection=_connection()).enqueue(
        "ai_engine.tasks.build_data_export", str(export.id)
    )
    logger.info("data_export_requested", user_id=str(user.id), export_id=str(export.id))
    return export


async def soft_delete_account(db: AsyncSession, user: User) -> None:
    """Soft-delete immediately; schedule hard purge within the retention window."""

    from app.modules.auth.service import revoke_all_sessions

    user.status = UserStatus.DELETED
    user.deleted_at = _now()
    user.purge_after = _now() + timedelta(days=settings.purge_retention_days)
    # Scrub directly-identifying fields now; full object purge runs at purge_after.
    user.display_name = None
    await revoke_all_sessions(db, user.id)

    # Schedule purge of stored images + PII.
    from app.modules.uploads.models import Image

    images = (
        await db.execute(select(Image).where(Image.user_id == user.id))
    ).scalars().all()
    for img in images:
        img.deleted_at = _now()
        img.purge_after = user.purge_after
    logger.info("account_soft_deleted", user_id=str(user.id), purge_after=str(user.purge_after))
