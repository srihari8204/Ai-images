"""Admin API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    status: str
    roles: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class SuspendRequest(BaseModel):
    suspend: bool = True


class GrantCreditsRequest(BaseModel):
    amount: int = Field(gt=0)
    reason: str = Field(default="manual grant", max_length=255)


class AdminJobOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    status: str
    cost_credits: int
    error_stage: str | None
    error_code: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ModerationEventOut(BaseModel):
    id: uuid.UUID
    subject_type: str
    subject_id: str | None
    classifier: str
    score: float | None
    decision: str
    detail: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ModerationDecisionRequest(BaseModel):
    decision: str = Field(examples=["approved", "rejected"])


class FlagOut(BaseModel):
    key: str
    value: dict
    description: str | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class FlagUpdateRequest(BaseModel):
    value: dict
    description: str | None = None
