"""Plan, subscription, and payment models."""

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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PlanKind(str, enum.Enum):
    SUBSCRIPTION = "subscription"
    CREDIT_PACK = "credit_pack"


class PaymentKind(str, enum.Enum):
    PURCHASE = "purchase"
    REFUND = "refund"
    CHARGEBACK = "chargeback"


class Plan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "plans"

    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[PlanKind] = mapped_column(
        Enum(PlanKind, name="plan_kind"), default=PlanKind.SUBSCRIPTION, nullable=False
    )
    monthly_credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # one-off packs
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    provider_price_id: Mapped[str | None] = mapped_column(String(128))
    features: Mapped[dict] = mapped_column(default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Subscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "subscriptions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False
    )
    provider_subscription_id: Mapped[str | None] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Payment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payments"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), default="stripe", nullable=False)
    provider_event_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    provider_session_id: Mapped[str | None] = mapped_column(String(255), index=True)
    kind: Mapped[PaymentKind] = mapped_column(
        Enum(PaymentKind, name="payment_kind"), default=PaymentKind.PURCHASE, nullable=False
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("plans.id", ondelete="SET NULL")
    )
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    credits_granted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="succeeded", nullable=False)
    invoice_object_key: Mapped[str | None] = mapped_column(String(512))
    related_payment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payments.id", ondelete="SET NULL")
    )
