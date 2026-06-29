"""Upload domain service: presign, validate, EXIF-strip, screen, dedup, record."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import safety
from app.core.config import settings
from app.core.errors import NotFoundError, PolicyError, ValidationAppError
from app.core.ids import uuid7
from app.core.logging import get_logger
from app.modules.admin.service import record_moderation_event
from app.modules.uploads.models import Image, ImageKind, SafetyStatus, Visibility
from app.modules.uploads.validation import validate_and_normalize
from app.storage import object_store

logger = get_logger(__name__)


def _ext_for_mime(mime: str) -> str:
    return {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(mime, "bin")


def build_upload_key(user_id: uuid.UUID, image_id: uuid.UUID, mime: str) -> str:
    return f"{user_id}/{image_id}.{_ext_for_mime(mime)}"


async def presign_upload(
    db: AsyncSession, user_id: uuid.UUID, content_type: str
) -> dict:
    """Issue a presigned PUT URL for direct-to-MinIO upload.

    Returns the object key the client must later register. We don't create the
    image row yet — it's created at registration after validation.
    """

    if content_type not in settings.upload_allowed_mime:
        raise ValidationAppError(
            "Unsupported content type",
            details={"allowed": settings.upload_allowed_mime},
        )
    image_id = uuid7()
    key = build_upload_key(user_id, image_id, content_type)
    url = object_store.presign_put(settings.bucket_uploads, key, content_type)
    return {
        "image_id": str(image_id),
        "upload_url": url,
        "object_key": key,
        "bucket": settings.bucket_uploads,
        "expires_in": settings.presign_ttl_seconds,
        "method": "PUT",
        "headers": {"Content-Type": content_type},
    }


async def _dedupe(
    db: AsyncSession, user_id: uuid.UUID, content_hash: str
) -> Image | None:
    return (
        await db.execute(
            select(Image).where(
                Image.user_id == user_id,
                Image.content_hash == content_hash,
                Image.deleted_at.is_(None),
            )
        )
    ).scalars().first()


async def _finalize_image(
    db: AsyncSession,
    user_id: uuid.UUID,
    meta: dict,
    *,
    image_id: uuid.UUID | None = None,
) -> Image:
    """Run dedup + safety, persist the clean object, and create the image row."""

    # Deduplication: reference the existing owned object, store nothing new.
    existing = await _dedupe(db, user_id, meta["content_hash"])
    if existing is not None:
        logger.info("upload_deduplicated", user_id=str(user_id), image_id=str(existing.id))
        return existing

    # Safety screening.
    result = safety.score_image(meta["data"], meta["mime"])
    image_id = image_id or uuid7()
    key = build_upload_key(user_id, image_id, meta["mime"])

    if not result.allowed:
        await record_moderation_event(
            db,
            subject_type="upload",
            subject_id=str(image_id),
            user_id=user_id,
            classifier=result.classifier,
            score=result.score,
            decision="rejected",
            detail=result.reason,
        )
        raise PolicyError(
            "Image rejected by content safety policy",
            code="content_policy_violation",
            status_code=422,
        )

    # Persist the EXIF-stripped, re-encoded bytes.
    object_store.put_object(settings.bucket_uploads, key, meta["data"], meta["mime"])

    image = Image(
        id=image_id,
        user_id=user_id,
        kind=ImageKind.UPLOAD,
        bucket=settings.bucket_uploads,
        object_key=key,
        mime=meta["mime"],
        width=meta["width"],
        height=meta["height"],
        bytes=meta["bytes"],
        content_hash=meta["content_hash"],
        safety_status=SafetyStatus.APPROVED,
        visibility=Visibility.PRIVATE,
    )
    db.add(image)
    await db.flush()
    logger.info("upload_recorded", user_id=str(user_id), image_id=str(image.id))
    return image


async def register_presigned(
    db: AsyncSession, user_id: uuid.UUID, object_key: str
) -> Image:
    """Validate an object the client uploaded via a presigned URL."""

    if not object_key.startswith(f"{user_id}/"):
        raise ValidationAppError("Object key does not belong to the caller")
    if not object_store.object_exists(settings.bucket_uploads, object_key):
        raise NotFoundError("Uploaded object not found; did the PUT succeed?")
    raw = object_store.get_object(settings.bucket_uploads, object_key)
    meta = validate_and_normalize(raw)
    # Derive a fresh image id; the stripped object is stored under it.
    return await _finalize_image(db, user_id, meta)


async def upload_multipart(
    db: AsyncSession, user_id: uuid.UUID, raw: bytes
) -> Image:
    """Validate and store an image sent directly (multipart fallback)."""

    meta = validate_and_normalize(raw)
    return await _finalize_image(db, user_id, meta)


async def get_image_for_owner(
    db: AsyncSession, user_id: uuid.UUID, image_id: uuid.UUID
) -> Image:
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


def presigned_get_url(image: Image) -> str:
    return object_store.presign_get(image.bucket, image.object_key)
