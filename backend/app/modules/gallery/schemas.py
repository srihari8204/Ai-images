"""Gallery API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class GalleryItem(BaseModel):
    id: uuid.UUID
    kind: str
    mime: str
    width: int | None
    height: int | None
    visibility: str
    is_favorite: bool
    safety_status: str
    share_token: str | None
    url: str = ""  # populated from a presigned URL after model_validate
    created_at: datetime

    model_config = {"from_attributes": True}


class GalleryPage(BaseModel):
    items: list[GalleryItem]
    next_cursor: str | None = None
    has_more: bool = False


class GalleryItemDetail(GalleryItem):
    job_id: uuid.UUID | None
    content_hash: str | None
    meta: dict


class UpdateGalleryItem(BaseModel):
    visibility: str | None = None
    is_favorite: bool | None = None


class ShareRequest(BaseModel):
    rotate: bool = False


class ShareResponse(BaseModel):
    share_token: str
    share_url: str
