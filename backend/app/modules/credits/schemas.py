"""Credit API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class BalanceOut(BaseModel):
    balance: int
    held: int
    available: int


class TransactionOut(BaseModel):
    id: uuid.UUID
    type: str
    amount: int
    reason: str | None
    job_id: str | None
    payment_id: str | None
    expires_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    next_cursor: str | None = None
    has_more: bool = False
