"""Payment / billing endpoints and the provider webhook handler."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from app.core.dependencies import CurrentUser, DbSession
from app.modules.payments import service
from app.modules.payments.models import PlanKind
from app.modules.payments.schemas import (
    CheckoutRequest,
    CheckoutResponse,
    InvoiceOut,
    InvoiceUrlOut,
    PlanOut,
    PortalResponse,
)

router = APIRouter(prefix="/billing", tags=["payments"])
# Webhook lives outside /api/v1 (design) and is unauthenticated but signature-verified.
webhook_router = APIRouter(tags=["payments"])


@router.get("/plans", response_model=list[PlanOut], summary="Subscription plans")
async def list_plans(db: DbSession) -> list[PlanOut]:
    plans = await service.list_plans(db, PlanKind.SUBSCRIPTION)
    return [PlanOut.model_validate(p) for p in plans]


@router.get("/credit-packs", response_model=list[PlanOut], summary="Credit packs")
async def list_credit_packs(db: DbSession) -> list[PlanOut]:
    plans = await service.list_plans(db, PlanKind.CREDIT_PACK)
    return [PlanOut.model_validate(p) for p in plans]


@router.post("/checkout", response_model=CheckoutResponse, summary="Create checkout session")
async def checkout(req: CheckoutRequest, user: CurrentUser, db: DbSession) -> CheckoutResponse:
    data = await service.create_checkout(db, user, req.plan_slug)
    return CheckoutResponse(**data)


@router.post("/portal", response_model=PortalResponse, summary="Customer portal link")
async def portal(user: CurrentUser, db: DbSession) -> PortalResponse:
    data = await service.create_portal(db, user)
    return PortalResponse(**data)


@router.get("/invoices", response_model=list[InvoiceOut], summary="List invoices")
async def list_invoices(user: CurrentUser, db: DbSession) -> list[InvoiceOut]:
    rows = await service.list_invoices(db, user.id)
    return [InvoiceOut.model_validate(r) for r in rows]


@router.get("/invoices/{invoice_id}", response_model=InvoiceUrlOut, summary="Download invoice")
async def get_invoice(invoice_id: uuid.UUID, user: CurrentUser, db: DbSession) -> InvoiceUrlOut:
    url = await service.get_invoice_url(db, user.id, invoice_id)
    return InvoiceUrlOut(url=url)


@webhook_router.post("/webhooks/payments", summary="Provider webhook (signed)")
async def payments_webhook(request: Request, db: DbSession) -> dict:
    payload = await request.body()
    signature = request.headers.get("stripe-signature") or request.headers.get("x-signature")
    return await service.handle_webhook(db, payload, signature)
