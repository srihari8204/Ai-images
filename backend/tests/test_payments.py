"""Payment webhook idempotency and credit fulfillment."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import pytest

from app.modules.credits import service as credits
from app.modules.payments import service as payments
from app.modules.payments.models import Plan, PlanKind
from app.modules.users.models import User, UserStatus


async def _user_and_plan(db):
    user = User(email=f"{uuid.uuid4()}@t.local", status=UserStatus.ACTIVE)
    plan = Plan(
        slug="pack_100", name="100", kind=PlanKind.CREDIT_PACK, credits=100,
        monthly_credits=0, price_cents=900, currency="USD",
    )
    db.add_all([user, plan])
    await db.flush()
    return user, plan


def _signed(event: dict) -> tuple[bytes, str]:
    payload = json.dumps(event).encode()
    sig = hmac.new(b"mock-webhook-secret", payload, hashlib.sha256).hexdigest()
    return payload, sig


@pytest.mark.asyncio
async def test_webhook_grants_credits_once(db):
    user, plan = await _user_and_plan(db)
    event = {
        "id": "evt_1",
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_1",
            "amount_total": 900,
            "metadata": {"user_id": str(user.id), "plan_slug": "pack_100"},
        }},
    }
    payload, sig = _signed(event)

    r1 = await payments.handle_webhook(db, payload, sig)
    assert r1["status"] == "fulfilled"
    # Redelivery of the same event must not double-credit.
    r2 = await payments.handle_webhook(db, payload, sig)
    assert r2["status"] == "duplicate"

    bal = await credits.get_balance(db, user.id)
    assert bal.balance == 100


@pytest.mark.asyncio
async def test_webhook_rejects_bad_signature(db):
    from app.core.errors import AppError

    user, plan = await _user_and_plan(db)
    event = {"id": "evt_2", "type": "checkout.session.completed", "data": {"object": {}}}
    payload, _ = _signed(event)
    with pytest.raises(AppError):
        await payments.handle_webhook(db, payload, "deadbeef")
