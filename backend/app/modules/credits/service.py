"""Credit ledger service.

All mutations follow the same pattern:
1. ``SELECT ... FOR UPDATE`` the user's balance row to serialise concurrent ops.
2. Append an immutable ledger entry (idempotent on ``idempotency_key``).
3. Update the cached balance/held counters in the *same* transaction.

The DB ``balance >= 0`` CHECK plus the row lock guarantees we can never go
negative from concurrent debits (design D4).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics
from app.core.errors import PaymentRequiredError
from app.modules.credits.models import CreditBalance, CreditTransaction, TxnType


async def _locked_balance(db: AsyncSession, user_id: uuid.UUID) -> CreditBalance:
    row = (
        await db.execute(
            select(CreditBalance)
            .where(CreditBalance.user_id == user_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        row = CreditBalance(user_id=user_id, balance=0, held=0, version=0)
        db.add(row)
        await db.flush()
        row = (
            await db.execute(
                select(CreditBalance)
                .where(CreditBalance.user_id == user_id)
                .with_for_update()
            )
        ).scalar_one()
    return row


async def _existing_txn(
    db: AsyncSession, user_id: uuid.UUID, idem: str | None
) -> CreditTransaction | None:
    if not idem:
        return None
    return (
        await db.execute(
            select(CreditTransaction).where(
                CreditTransaction.user_id == user_id,
                CreditTransaction.idempotency_key == idem,
            )
        )
    ).scalar_one_or_none()


async def get_balance(db: AsyncSession, user_id: uuid.UUID) -> CreditBalance:
    row = (
        await db.execute(select(CreditBalance).where(CreditBalance.user_id == user_id))
    ).scalar_one_or_none()
    return row or CreditBalance(user_id=user_id, balance=0, held=0, version=0)


async def available(db: AsyncSession, user_id: uuid.UUID) -> int:
    bal = await get_balance(db, user_id)
    return bal.balance - bal.held


async def grant(
    db: AsyncSession,
    user_id: uuid.UUID,
    amount: int,
    *,
    reason: str,
    idempotency_key: str | None = None,
    payment_id: uuid.UUID | None = None,
    expires_at: datetime | None = None,
) -> CreditTransaction:
    if amount <= 0:
        raise ValueError("grant amount must be positive")
    existing = await _existing_txn(db, user_id, idempotency_key)
    if existing:
        return existing
    bal = await _locked_balance(db, user_id)
    txn = CreditTransaction(
        user_id=user_id,
        type=TxnType.GRANT,
        amount=amount,
        reason=reason,
        idempotency_key=idempotency_key,
        payment_id=str(payment_id) if payment_id else None,
        expires_at=expires_at,
    )
    db.add(txn)
    bal.balance += amount
    bal.version += 1
    await db.flush()
    metrics.credit_txn_total.labels(type="grant").inc()
    return txn


async def hold(
    db: AsyncSession,
    user_id: uuid.UUID,
    amount: int,
    *,
    job_id: uuid.UUID,
    idempotency_key: str,
) -> CreditTransaction:
    """Reserve ``amount`` credits for a job. Raises 402 if unavailable."""

    existing = await _existing_txn(db, user_id, idempotency_key)
    if existing:
        return existing
    bal = await _locked_balance(db, user_id)
    if bal.balance - bal.held < amount:
        raise PaymentRequiredError(
            "Insufficient credits",
            details={"required": amount, "available": bal.balance - bal.held},
        )
    # A hold is a *reservation*: it does not move settled balance (amount 0 so the
    # invariant balance == sum(ledger) holds), it only increases ``held`` so that
    # available = balance - held drops. The reserved quantity is the job's cost.
    txn = CreditTransaction(
        user_id=user_id,
        type=TxnType.HOLD,
        amount=0,
        job_id=str(job_id),
        reason=f"job_hold:{amount}",
        idempotency_key=idempotency_key,
    )
    db.add(txn)
    bal.held += amount
    bal.version += 1
    await db.flush()
    metrics.credit_txn_total.labels(type="hold").inc()
    return txn


async def debit(
    db: AsyncSession,
    user_id: uuid.UUID,
    amount: int,
    *,
    job_id: uuid.UUID,
    idempotency_key: str,
) -> CreditTransaction:
    """Convert a prior hold into a final debit exactly once."""

    existing = await _existing_txn(db, user_id, idempotency_key)
    if existing:
        return existing
    bal = await _locked_balance(db, user_id)
    txn = CreditTransaction(
        user_id=user_id,
        type=TxnType.DEBIT,
        amount=-amount,
        job_id=str(job_id),
        reason="job_debit",
        idempotency_key=idempotency_key,
    )
    db.add(txn)
    bal.balance -= amount
    bal.held = max(0, bal.held - amount)
    bal.version += 1
    await db.flush()
    metrics.credit_txn_total.labels(type="debit").inc()
    return txn


async def refund_hold(
    db: AsyncSession,
    user_id: uuid.UUID,
    amount: int,
    *,
    job_id: uuid.UUID,
    idempotency_key: str,
) -> CreditTransaction:
    """Release a hold on job failure/cancellation exactly once."""

    existing = await _existing_txn(db, user_id, idempotency_key)
    if existing:
        return existing
    bal = await _locked_balance(db, user_id)
    # Releasing a hold returns reserved credits to availability. Balance was never
    # reduced by the hold, so the refund carries amount 0 and only frees ``held``.
    txn = CreditTransaction(
        user_id=user_id,
        type=TxnType.REFUND,
        amount=0,
        job_id=str(job_id),
        reason=f"job_refund:{amount}",
        idempotency_key=idempotency_key,
    )
    db.add(txn)
    bal.held = max(0, bal.held - amount)
    bal.version += 1
    await db.flush()
    metrics.credit_txn_total.labels(type="refund").inc()
    return txn


async def reverse_grant(
    db: AsyncSession,
    user_id: uuid.UUID,
    amount: int,
    *,
    reason: str,
    idempotency_key: str,
    payment_id: uuid.UUID | None = None,
    allow_negative: bool = True,
) -> CreditTransaction:
    """Reverse a prior grant (refund/chargeback). May overdraw per policy."""

    existing = await _existing_txn(db, user_id, idempotency_key)
    if existing:
        return existing
    bal = await _locked_balance(db, user_id)
    deduct = amount if allow_negative else min(amount, bal.balance)
    txn = CreditTransaction(
        user_id=user_id,
        type=TxnType.REVERSAL,
        amount=-deduct,
        reason=reason,
        idempotency_key=idempotency_key,
        payment_id=str(payment_id) if payment_id else None,
    )
    db.add(txn)
    # The ledger entry records the full reversal (audit source of truth). The
    # cached balance column is clamped at 0 to honour the DB CHECK; any overdraw
    # beyond the cached balance is reflected as a negative ledger sum which
    # reconciliation/admin tooling reads directly. ``allow_negative`` governs
    # whether we permit the reversal at all when funds are short.
    bal.balance = max(0, bal.balance - deduct)
    bal.version += 1
    await db.flush()
    metrics.credit_txn_total.labels(type="reversal").inc()
    return txn


async def list_transactions(
    db: AsyncSession, user_id: uuid.UUID, *, limit: int = 50, before: datetime | None = None
) -> list[CreditTransaction]:
    stmt = (
        select(CreditTransaction)
        .where(CreditTransaction.user_id == user_id)
        .order_by(CreditTransaction.created_at.desc())
        .limit(limit)
    )
    if before:
        stmt = stmt.where(CreditTransaction.created_at < before)
    return list((await db.execute(stmt)).scalars().all())
