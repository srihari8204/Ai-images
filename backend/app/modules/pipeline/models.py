"""Job and job-result models (generation pipeline domain)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Ordered pipeline stages (design D8).
ALL_STAGES = ["generate", "instantid", "controlnet", "gfpgan", "realesrgan", "bg_removal"]


class Job(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_user_created", "user_id", "created_at"),
        Index("ix_jobs_status", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    style_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("styles.id", ondelete="SET NULL")
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status"), default=JobStatus.QUEUED, nullable=False
    )
    cost_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hold_txn_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("credit_transactions.id", ondelete="SET NULL")
    )
    prompt: Mapped[str] = mapped_column(String(4000), nullable=False, default="")
    negative_prompt: Mapped[str | None] = mapped_column(String(4000))
    seed: Mapped[int | None] = mapped_column(Integer)
    params: Mapped[dict] = mapped_column(default=dict, nullable=False)
    stages: Mapped[list] = mapped_column(default=list, nullable=False)
    reference_image_ids: Mapped[list] = mapped_column(default=list, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_stage: Mapped[str | None] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(512))
    requeued_from: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    results: Mapped[list["JobResult"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class JobResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "job_results"

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    image_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("images.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    job: Mapped[Job] = relationship(back_populates="results")
