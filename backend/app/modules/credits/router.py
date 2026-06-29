"""Credit balance and ledger endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.dependencies import CurrentUser, DbSession
from app.core.pagination import decode_cursor, encode_cursor
from app.modules.credits import service
from app.modules.credits.schemas import (
    BalanceOut,
    TransactionOut,
    TransactionPage,
)

router = APIRouter(prefix="/credits", tags=["credits"])


@router.get("/balance", response_model=BalanceOut, summary="Current credit balance")
async def get_balance(user: CurrentUser, db: DbSession) -> BalanceOut:
    bal = await service.get_balance(db, user.id)
    return BalanceOut(
        balance=bal.balance, held=bal.held, available=bal.balance - bal.held
    )


@router.get(
    "/transactions", response_model=TransactionPage, summary="Paginated credit ledger"
)
async def list_transactions(
    user: CurrentUser,
    db: DbSession,
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
) -> TransactionPage:
    before = None
    if cursor:
        created, _ = decode_cursor(cursor)
        before = created
    rows = await service.list_transactions(db, user.id, limit=limit + 1, before=before)
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = (
        encode_cursor(rows[-1].created_at, rows[-1].id) if has_more and rows else None
    )
    return TransactionPage(
        items=[TransactionOut.model_validate(r) for r in rows],
        next_cursor=next_cursor,
        has_more=has_more,
    )
