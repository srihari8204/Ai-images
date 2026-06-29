"""Image model — shared by uploads, generation outputs, and the gallery."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ImageKind(str, enum.Enum):
    UPLOAD = "upload"
    GENERATION = "generation"


class SafetyStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    QUARANTINED = "quarantined"
    REJECTED = "rejected"


class Visibility(str, enum.Enum):
    PRIVATE = "private"
    UNLISTED = "unlisted"
    PUBLIC = "public"


class Image(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "images"
    __table_args__ = (
        Index("ix_images_user_created", "user_id", "created_at"),
        Index("ix_images_content_hash", "content_hash"),
        Index("ix_images_share_token", "share_token"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[ImageKind] = mapped_column(Enum(ImageKind, name="image_kind"), nullable=False)
    bucket: Mapped[str] = mapped_column(String(64), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    mime: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    bytes: Mapped[int | None] = mapped_column(BigInteger)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    safety_status: Mapped[SafetyStatus] = mapped_column(
        Enum(SafetyStatus, name="safety_status"),
        default=SafetyStatus.PENDING,
        nullable=False,
    )
    visibility: Mapped[Visibility] = mapped_column(
        Enum(Visibility, name="visibility"), default=Visibility.PRIVATE, nullable=False
    )
    share_token: Mapped[str | None] = mapped_column(String(64), unique=True)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        # use_alter: closes the images->jobs->styles->images FK cycle (ALTER after).
        ForeignKey("jobs.id", ondelete="SET NULL", use_alter=True, name="fk_images_job")
    )
    meta: Mapped[dict] = mapped_column(default=dict, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purge_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
