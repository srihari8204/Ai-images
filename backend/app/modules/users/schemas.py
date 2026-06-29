"""User profile / settings / consent schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProfileOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    avatar_image_id: uuid.UUID | None
    locale: str
    status: str
    roles: list[str]
    email_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    locale: str | None = Field(default=None, max_length=16)
    avatar_image_id: uuid.UUID | None = None


class SettingsOut(BaseModel):
    settings: dict


class SettingsUpdate(BaseModel):
    settings: dict


class ConsentRequest(BaseModel):
    type: str = Field(examples=["biometric"])
    version: str = Field(examples=["2025-01"])
    granted: bool = True


class ConsentOut(BaseModel):
    id: uuid.UUID
    type: str
    version: str
    granted_at: datetime | None
    revoked_at: datetime | None

    model_config = {"from_attributes": True}


class ExportOut(BaseModel):
    id: uuid.UUID
    status: str
    object_key: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
