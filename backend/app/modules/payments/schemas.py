"""Payments API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class PlanOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    kind: str
    monthly_credits: int
    credits: int
    price_cents: int
    currency: str
    features: dict

    model_config = {"from_attributes": True}


class CheckoutRequest(BaseModel):
    plan_slug: str


class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str
    provider: str


class PortalResponse(BaseModel):
    portal_url: str


class InvoiceOut(BaseModel):
    id: uuid.UUID
    amount_cents: int
    currency: str
    credits_granted: int
    kind: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class InvoiceUrlOut(BaseModel):
    url: str
