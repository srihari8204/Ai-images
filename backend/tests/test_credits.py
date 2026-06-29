"""Credit ledger invariants: balance = sum(ledger), idempotency, hold→debit→refund."""

from __future__ import annotations

import uuid

import pytest

from app.modules.credits import service as credits
from app.modules.credits.models import CreditTransaction
from app.modules.users.models import User, UserStatus
from sqlalchemy import select


async def _make_user(db) -> User:
    user = User(email=f"{uuid.uuid4()}@t.local", status=UserStatus.ACTIVE)
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_grant_then_balance(db):
    user = await _make_user(db)
    await credits.grant(db, user.id, 100, reason="test", idempotency_key="g1")
    bal = await credits.get_balance(db, user.id)
    assert bal.balance == 100


@pytest.mark.asyncio
async def test_grant_is_idempotent(db):
    user = await _make_user(db)
    await credits.grant(db, user.id, 100, reason="test", idempotency_key="g1")
    await credits.grant(db, user.id, 100, reason="test", idempotency_key="g1")
    bal = await credits.get_balance(db, user.id)
    assert bal.balance == 100  # second grant deduped


@pytest.mark.asyncio
async def test_hold_debit_flow(db):
    user = await _make_user(db)
    job_id = uuid.uuid4()
    await credits.grant(db, user.id, 50, reason="seed", idempotency_key="g")
    await credits.hold(db, user.id, 10, job_id=job_id, idempotency_key="hold:k")
    bal = await credits.get_balance(db, user.id)
    assert bal.held == 10
    assert await credits.available(db, user.id) == 40

    await credits.debit(db, user.id, 10, job_id=job_id, idempotency_key="debit:k")
    bal = await credits.get_balance(db, user.id)
    assert bal.balance == 40 and bal.held == 0


@pytest.mark.asyncio
async def test_refund_restores_availability(db):
    user = await _make_user(db)
    job_id = uuid.uuid4()
    await credits.grant(db, user.id, 50, reason="seed", idempotency_key="g")
    await credits.hold(db, user.id, 10, job_id=job_id, idempotency_key="hold:k")
    await credits.refund_hold(db, user.id, 10, job_id=job_id, idempotency_key="refund:k")
    assert await credits.available(db, user.id) == 50


@pytest.mark.asyncio
async def test_insufficient_credits_raises(db):
    from app.core.errors import PaymentRequiredError

    user = await _make_user(db)
    with pytest.raises(PaymentRequiredError):
        await credits.hold(db, user.id, 5, job_id=uuid.uuid4(), idempotency_key="h")


@pytest.mark.asyncio
async def test_balance_equals_ledger_sum(db):
    user = await _make_user(db)
    job_id = uuid.uuid4()
    await credits.grant(db, user.id, 100, reason="seed", idempotency_key="g")
    await credits.hold(db, user.id, 30, job_id=job_id, idempotency_key="hold:k")
    await credits.debit(db, user.id, 30, job_id=job_id, idempotency_key="debit:k")
    rows = (
        await db.execute(select(CreditTransaction).where(CreditTransaction.user_id == user.id))
    ).scalars().all()
    ledger_sum = sum(r.amount for r in rows)
    bal = await credits.get_balance(db, user.id)
    assert bal.balance == ledger_sum
