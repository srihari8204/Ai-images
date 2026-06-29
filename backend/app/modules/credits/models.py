"""Credit ledger and derived balance models.

Balance is the sum of ``credit_transactions.amount``. ``credit_balances`` is a
denormalised cache updated in the *same* transaction as each ledger write, under
a ``SELECT ... FOR UPDATE`` row lock, with a ``balance >= 0`` CHECK constraint.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TxnType(str, enum.Enum):
    GRANT = "grant"
    HOLD = "hold"
    DEBIT = "debit"
    REFUND = "refund"
    REVERSAL = "reversal"


class CreditBalance(TimestampMixin, Base):
    __tablename__ = "credit_balances"
    __table_args__ = (CheckConstraint("balance >= 0", name="ck_balance_non_negative"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    balance: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    # Held credits are reserved but not yet debited; available = balance - held.
    held: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class CreditTransaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "credit_transactions"
    __table_args__ = (
        Index("ix_credit_txn_user_created", "user_id", "created_at"),
        # Idempotency: a given (user, idempotency_key) yields at most one txn.
        Index(
            "uq_credit_txn_idem",
            "user_id",
            "idempotency_key",
            unique=True,
            postgresql_where=None,
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[TxnType] = mapped_column(Enum(TxnType, name="txn_type"), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)  # signed
    # Stored as text refs (no FK) to keep the append-only ledger decoupled.
    job_id: Mapped[str | None] = mapped_column(String(36))
    payment_id: Mapped[str | None] = mapped_column(String(36))
    idempotency_key: Mapped[str | None] = mapped_column(String(160))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(255))
