"""Upload API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PresignRequest(BaseModel):
    content_type: str = Field(examples=["image/jpeg"])


class PresignResponse(BaseModel):
    image_id: str
    upload_url: str
    object_key: str
    bucket: str
    expires_in: int
    method: str
    headers: dict


class RegisterRequest(BaseModel):
    object_key: str


class ImageOut(BaseModel):
    id: uuid.UUID
    kind: str
    mime: str
    width: int | None
    height: int | None
    bytes: int | None
    safety_status: str
    visibility: str
    is_favorite: bool
    url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
