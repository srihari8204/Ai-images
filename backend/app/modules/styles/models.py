"""Style catalog model."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Style(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "styles"

    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="general")
    description: Mapped[str | None] = mapped_column(String(512))
    template: Mapped[str] = mapped_column(String(2000), nullable=False, default="{prompt}")
    negative_prompt: Mapped[str | None] = mapped_column(String(2000))
    model_ref: Mapped[str] = mapped_column(String(128), nullable=False, default="flux.1")
    lora_refs: Mapped[list] = mapped_column(default=list, nullable=False)
    default_params: Mapped[dict] = mapped_column(default=dict, nullable=False)
    cost_multiplier: Mapped[float] = mapped_column(Numeric(6, 2), default=1, nullable=False)
    plan_gate: Mapped[str | None] = mapped_column(String(32))  # null = free
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    preview_image_id: Mapped[uuid.UUID | None] = mapped_column(
        # use_alter: closes the styles->images->jobs->styles FK cycle (ALTER after).
        ForeignKey("images.id", ondelete="SET NULL", use_alter=True, name="fk_styles_preview_image")
    )
