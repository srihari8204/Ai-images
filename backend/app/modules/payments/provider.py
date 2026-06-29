"""Payment provider abstraction.

Wraps Stripe behind a small interface so the rest of the module is provider
agnostic (design open-question: provider may change). When no Stripe key is
configured a deterministic *mock* provider is used so checkout/webhook flows are
fully exercisable in dev and tests without external calls.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from app.core.config import settings
from app.core.errors import AppError


class CheckoutSession:
    def __init__(self, session_id: str, url: str):
        self.id = session_id
        self.url = url


class PaymentProvider:
    name = "mock"

    def create_checkout_session(
        self, *, user_id: str, plan, success_url: str, cancel_url: str
    ) -> CheckoutSession:
        raise NotImplementedError

    def create_portal_link(self, *, customer_ref: str, return_url: str) -> str:
        raise NotImplementedError

    def verify_and_parse_webhook(self, payload: bytes, signature: str | None) -> dict:
        raise NotImplementedError


class MockProvider(PaymentProvider):
    name = "mock"

    def create_checkout_session(self, *, user_id, plan, success_url, cancel_url):
        sid = f"cs_mock_{hashlib.sha256((user_id + plan.slug).encode()).hexdigest()[:24]}"
        # The mock "checkout" page is the frontend's simulated success page.
        url = f"{settings.frontend_base_url}/billing/mock-checkout?session_id={sid}&plan={plan.slug}"
        return CheckoutSession(sid, url)

    def create_portal_link(self, *, customer_ref, return_url):
        return f"{settings.frontend_base_url}/billing?portal=mock&return={return_url}"

    def verify_and_parse_webhook(self, payload: bytes, signature: str | None) -> dict:
        # HMAC-SHA256 over the body keyed by the webhook secret.
        secret = settings.stripe_webhook_secret or "mock-webhook-secret"
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        if not signature or not hmac.compare_digest(signature, expected):
            raise AppError("Invalid webhook signature", code="invalid_signature", status_code=400)
        return json.loads(payload)


class StripeProvider(PaymentProvider):
    name = "stripe"

    def __init__(self) -> None:
        import stripe

        stripe.api_key = settings.stripe_secret_key
        self._stripe = stripe

    def create_checkout_session(self, *, user_id, plan, success_url, cancel_url):
        mode = "subscription" if plan.kind.value == "subscription" else "payment"
        session = self._stripe.checkout.Session.create(
            mode=mode,
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=user_id,
            metadata={"user_id": user_id, "plan_slug": plan.slug},
            line_items=[{"price": plan.provider_price_id, "quantity": 1}],
        )
        return CheckoutSession(session.id, session.url)

    def create_portal_link(self, *, customer_ref, return_url):
        portal = self._stripe.billing_portal.Session.create(
            customer=customer_ref, return_url=return_url
        )
        return portal.url

    def verify_and_parse_webhook(self, payload: bytes, signature: str | None) -> dict:
        try:
            event = self._stripe.Webhook.construct_event(
                payload, signature, settings.stripe_webhook_secret
            )
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                "Invalid webhook signature", code="invalid_signature", status_code=400
            ) from exc
        return event


def get_provider() -> PaymentProvider:
    if settings.stripe_secret_key:
        return StripeProvider()
    return MockProvider()
