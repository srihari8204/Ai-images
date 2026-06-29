"""Payments service: catalog, checkout, webhook fulfillment, refunds, invoices."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics
from app.core.config import settings
from app.core.errors import NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.modules.credits import service as credits
from app.modules.payments.models import (
    Payment,
    PaymentKind,
    Plan,
    PlanKind,
    Subscription,
)
from app.modules.payments.provider import get_provider
from app.storage import object_store

logger = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #
async def list_plans(db: AsyncSession, kind: PlanKind | None = None) -> list[Plan]:
    stmt = select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.price_cents)
    if kind:
        stmt = stmt.where(Plan.kind == kind)
    return list((await db.execute(stmt)).scalars().all())


async def get_plan(db: AsyncSession, slug: str) -> Plan:
    plan = (await db.execute(select(Plan).where(Plan.slug == slug))).scalar_one_or_none()
    if plan is None or not plan.is_active:
        raise NotFoundError("Plan not found")
    return plan


# --------------------------------------------------------------------------- #
# Checkout
# --------------------------------------------------------------------------- #
async def create_checkout(db: AsyncSession, user, plan_slug: str) -> dict:
    plan = await get_plan(db, plan_slug)
    provider = get_provider()
    session = provider.create_checkout_session(
        user_id=str(user.id),
        plan=plan,
        success_url=f"{settings.frontend_base_url}/billing?status=success",
        cancel_url=f"{settings.frontend_base_url}/billing?status=cancelled",
    )
    logger.info("checkout_created", user_id=str(user.id), plan=plan_slug, session=session.id)
    return {"checkout_url": session.url, "session_id": session.id, "provider": provider.name}


async def create_portal(db: AsyncSession, user) -> dict:
    provider = get_provider()
    customer_ref = (user.settings_json or {}).get("provider_customer_id", str(user.id))
    url = provider.create_portal_link(
        customer_ref=customer_ref, return_url=f"{settings.frontend_base_url}/billing"
    )
    return {"portal_url": url}


# --------------------------------------------------------------------------- #
# Webhook fulfillment (idempotent by provider_event_id)
# --------------------------------------------------------------------------- #
async def handle_webhook(db: AsyncSession, payload: bytes, signature: str | None) -> dict:
    provider = get_provider()
    event = provider.verify_and_parse_webhook(payload, signature)

    event_id = event.get("id") or event.get("event_id")
    event_type = event.get("type")
    data = event.get("data", {}).get("object", event.get("data", {}))
    if not event_id:
        raise ValidationAppError("Webhook missing event id")

    # Idempotency: a duplicate provider_event_id is a no-op.
    existing = (
        await db.execute(select(Payment).where(Payment.provider_event_id == event_id))
    ).scalar_one_or_none()
    if existing is not None:
        logger.info("webhook_duplicate_ignored", event_id=event_id)
        return {"status": "duplicate", "payment_id": str(existing.id)}

    handler = {
        "checkout.session.completed": _fulfill_purchase,
        "payment_succeeded": _fulfill_purchase,
        "charge.refunded": _handle_refund,
        "refund": _handle_refund,
        "charge.dispute.created": _handle_chargeback,
        "chargeback": _handle_chargeback,
    }.get(event_type)

    if handler is None:
        logger.info("webhook_unhandled_type", event_type=event_type)
        return {"status": "ignored", "type": event_type}

    return await handler(db, event_id, data)


async def _fulfill_purchase(db: AsyncSession, event_id: str, data: dict) -> dict:
    metadata = data.get("metadata", {})
    user_id = metadata.get("user_id") or data.get("client_reference_id")
    plan_slug = metadata.get("plan_slug")
    if not user_id or not plan_slug:
        raise ValidationAppError("Webhook missing user/plan metadata")

    plan = await get_plan(db, plan_slug)
    user_uuid = uuid.UUID(user_id)
    credits_to_grant = plan.credits if plan.kind == PlanKind.CREDIT_PACK else plan.monthly_credits

    payment = Payment(
        user_id=user_uuid,
        provider=get_provider().name,
        provider_event_id=event_id,
        provider_session_id=data.get("id"),
        kind=PaymentKind.PURCHASE,
        plan_id=plan.id,
        amount_cents=int(data.get("amount_total", plan.price_cents)),
        currency=plan.currency,
        credits_granted=credits_to_grant,
        status="succeeded",
    )
    db.add(payment)
    await db.flush()

    # Grant credits exactly once (idempotent on the event id).
    await credits.grant(
        db,
        user_uuid,
        credits_to_grant,
        reason=f"purchase:{plan.slug}",
        idempotency_key=f"grant:{event_id}",
        payment_id=payment.id,
    )

    # Subscriptions: record/refresh the subscription row.
    if plan.kind == PlanKind.SUBSCRIPTION:
        await _upsert_subscription(db, user_uuid, plan, data)
        # Mark plan entitlement on the user for style gating / priority.
        await _grant_plan_entitlement(db, user_uuid, plan.slug)

    invoice_key = await _store_invoice(payment)
    payment.invoice_object_key = invoice_key
    await db.flush()

    metrics.payments_total.labels(kind="purchase", status="succeeded").inc()
    metrics.revenue_cents_total.inc(payment.amount_cents)
    logger.info("purchase_fulfilled", event_id=event_id, user_id=user_id, credits=credits_to_grant)
    return {"status": "fulfilled", "payment_id": str(payment.id), "credits": credits_to_grant}


async def _handle_refund(db: AsyncSession, event_id: str, data: dict) -> dict:
    original = await _find_original_payment(db, data)
    user_id = original.user_id if original else _user_from_data(data)
    credits_to_reverse = original.credits_granted if original else int(data.get("credits", 0))

    payment = Payment(
        user_id=user_id,
        provider=get_provider().name,
        provider_event_id=event_id,
        kind=PaymentKind.REFUND,
        amount_cents=int(data.get("amount_refunded", data.get("amount", 0))),
        currency=(original.currency if original else "USD"),
        credits_granted=-credits_to_reverse,
        status="succeeded",
        related_payment_id=original.id if original else None,
    )
    db.add(payment)
    await db.flush()

    if credits_to_reverse:
        await credits.reverse_grant(
            db,
            user_id,
            credits_to_reverse,
            reason=f"refund:{event_id}",
            idempotency_key=f"reverse:{event_id}",
            payment_id=payment.id,
            allow_negative=settings.payments_allow_negative_balance,
        )
    metrics.payments_total.labels(kind="refund", status="succeeded").inc()
    logger.info("refund_processed", event_id=event_id)
    return {"status": "refunded", "payment_id": str(payment.id)}


async def _handle_chargeback(db: AsyncSession, event_id: str, data: dict) -> dict:
    original = await _find_original_payment(db, data)
    user_id = original.user_id if original else _user_from_data(data)
    credits_to_reverse = original.credits_granted if original else 0

    payment = Payment(
        user_id=user_id,
        provider=get_provider().name,
        provider_event_id=event_id,
        kind=PaymentKind.CHARGEBACK,
        amount_cents=int(data.get("amount", 0)),
        currency=(original.currency if original else "USD"),
        credits_granted=-credits_to_reverse,
        status="lost",
        related_payment_id=original.id if original else None,
    )
    db.add(payment)
    await db.flush()
    if credits_to_reverse:
        await credits.reverse_grant(
            db,
            user_id,
            credits_to_reverse,
            reason=f"chargeback:{event_id}",
            idempotency_key=f"reverse:{event_id}",
            payment_id=payment.id,
            allow_negative=True,
        )
    metrics.payments_total.labels(kind="chargeback", status="lost").inc()
    return {"status": "chargeback", "payment_id": str(payment.id)}


async def _find_original_payment(db: AsyncSession, data: dict) -> Payment | None:
    session_id = data.get("payment_intent") or data.get("session_id") or data.get("id")
    if not session_id:
        return None
    return (
        await db.execute(
            select(Payment).where(
                Payment.provider_session_id == session_id,
                Payment.kind == PaymentKind.PURCHASE,
            )
        )
    ).scalar_one_or_none()


def _user_from_data(data: dict) -> uuid.UUID:
    uid = data.get("metadata", {}).get("user_id") or data.get("client_reference_id")
    if not uid:
        raise ValidationAppError("Cannot resolve user for payment event")
    return uuid.UUID(uid)


async def _upsert_subscription(db: AsyncSession, user_id: uuid.UUID, plan: Plan, data: dict) -> None:
    sub_id = data.get("subscription") or data.get("id")
    sub = (
        await db.execute(
            select(Subscription).where(Subscription.user_id == user_id, Subscription.plan_id == plan.id)
        )
    ).scalar_one_or_none()
    if sub is None:
        sub = Subscription(
            user_id=user_id, plan_id=plan.id, provider_subscription_id=sub_id, status="active"
        )
        db.add(sub)
    else:
        sub.status = "active"
        sub.provider_subscription_id = sub_id
    await db.flush()


async def _grant_plan_entitlement(db: AsyncSession, user_id: uuid.UUID, plan_slug: str) -> None:
    from app.modules.users.models import User

    user = await db.get(User, user_id)
    if user is None:
        return
    s = dict(user.settings_json or {})
    plans = set(s.get("plans", []))
    plans.add(plan_slug)
    s["plans"] = sorted(plans)
    user.settings_json = s
    await db.flush()


async def _store_invoice(payment: Payment) -> str:
    """Render a minimal JSON invoice and store it in the exports bucket."""

    invoice = {
        "invoice_id": str(payment.id),
        "issued_at": _now().isoformat(),
        "amount_cents": payment.amount_cents,
        "currency": payment.currency,
        "credits_granted": payment.credits_granted,
        "kind": payment.kind.value,
    }
    key = f"invoices/{payment.user_id}/{payment.id}.json"
    object_store.put_object(
        settings.bucket_exports, key, json.dumps(invoice, indent=2).encode(), "application/json"
    )
    return key


# --------------------------------------------------------------------------- #
# Invoices
# --------------------------------------------------------------------------- #
async def list_invoices(db: AsyncSession, user_id: uuid.UUID) -> list[Payment]:
    return list(
        (
            await db.execute(
                select(Payment)
                .where(Payment.user_id == user_id, Payment.kind == PaymentKind.PURCHASE)
                .order_by(Payment.created_at.desc())
            )
        )
        .scalars()
        .all()
    )


async def get_invoice_url(db: AsyncSession, user_id: uuid.UUID, payment_id: uuid.UUID) -> str:
    payment = await db.get(Payment, payment_id)
    if payment is None or payment.user_id != user_id or not payment.invoice_object_key:
        raise NotFoundError("Invoice not found")
    return object_store.presign_get(settings.bucket_exports, payment.invoice_object_key)
