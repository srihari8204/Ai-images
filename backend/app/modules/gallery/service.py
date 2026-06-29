"""Gallery service: listing, visibility, sharing, favorites, deletion."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.core.security import generate_opaque_token
from app.modules.uploads.models import Image, ImageKind, Visibility
from app.storage import object_store

logger = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def list_gallery(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    limit: int,
    before: datetime | None,
    kind: str | None = None,
    favorite: bool | None = None,
) -> list[Image]:
    stmt = (
        select(Image)
        .where(Image.user_id == user_id, Image.deleted_at.is_(None))
        .order_by(Image.created_at.desc())
        .limit(limit)
    )
    if before:
        stmt = stmt.where(Image.created_at < before)
    if kind:
        stmt = stmt.where(Image.kind == ImageKind(kind))
    if favorite is not None:
        stmt = stmt.where(Image.is_favorite.is_(favorite))
    return list((await db.execute(stmt)).scalars().all())


async def get_owned(db: AsyncSession, user_id: uuid.UUID, image_id: uuid.UUID) -> Image:
    image = (
        await db.execute(
            select(Image).where(
                Image.id == image_id,
                Image.user_id == user_id,
                Image.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if image is None:
        raise NotFoundError("Image not found")
    return image


async def set_visibility(
    db: AsyncSession, user_id: uuid.UUID, image_id: uuid.UUID, visibility: str
) -> Image:
    image = await get_owned(db, user_id, image_id)
    image.visibility = Visibility(visibility)
    # Private images cannot retain a live share token.
    if image.visibility == Visibility.PRIVATE:
        image.share_token = None
    await db.flush()
    return image


async def set_favorite(
    db: AsyncSession, user_id: uuid.UUID, image_id: uuid.UUID, favorite: bool
) -> Image:
    image = await get_owned(db, user_id, image_id)
    image.is_favorite = favorite
    await db.flush()
    return image


async def create_share_link(
    db: AsyncSession, user_id: uuid.UUID, image_id: uuid.UUID, *, rotate: bool = False
) -> Image:
    image = await get_owned(db, user_id, image_id)
    if image.visibility == Visibility.PRIVATE:
        raise ConflictError(
            "Image must be unlisted or public to share",
            code="image_private",
        )
    if image.share_token is None or rotate:
        image.share_token = generate_opaque_token(18)
    await db.flush()
    return image


async def delete_image(db: AsyncSession, user_id: uuid.UUID, image_id: uuid.UUID) -> None:
    image = await get_owned(db, user_id, image_id)
    image.deleted_at = _now()
    image.purge_after = _now() + timedelta(days=settings.purge_retention_days)
    image.share_token = None
    await db.flush()
    logger.info("image_deleted", image_id=str(image_id), purge_after=str(image.purge_after))


async def get_by_share_token(db: AsyncSession, token: str) -> Image:
    image = (
        await db.execute(
            select(Image).where(
                Image.share_token == token,
                Image.deleted_at.is_(None),
                Image.visibility.in_([Visibility.UNLISTED, Visibility.PUBLIC]),
            )
        )
    ).scalar_one_or_none()
    if image is None:
        raise NotFoundError("Shared image not found")
    return image


def presigned_url(image: Image, *, ttl: int | None = None) -> str:
    return object_store.presign_get(image.bucket, image.object_key, ttl)
