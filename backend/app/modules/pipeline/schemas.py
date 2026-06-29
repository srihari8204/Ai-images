"""Pipeline / job API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.config import settings
from app.modules.pipeline.models import ALL_STAGES


class JobParams(BaseModel):
    width: int = Field(default=1024, ge=256, le=settings.max_resolution)
    height: int = Field(default=1024, ge=256, le=settings.max_resolution)
    steps: int = Field(default=28, ge=1, le=settings.max_steps)
    guidance: float = Field(default=3.5, ge=0, le=20)
    num_outputs: int = Field(default=1, ge=1, le=4)


class JobSubmitRequest(BaseModel):
    prompt: str = Field(max_length=4000)
    negative_prompt: str | None = Field(default=None, max_length=4000)
    style_slug: str | None = None
    stages: list[str] = Field(default_factory=lambda: ["generate"])
    reference_image_ids: list[uuid.UUID] = Field(default_factory=list)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    params: JobParams = Field(default_factory=JobParams)

    def validated_stages(self) -> list[str]:
        # Keep only known stages, preserve canonical order, ensure "generate" first.
        requested = set(self.stages) | {"generate"}
        return [s for s in ALL_STAGES if s in requested]


class JobOut(BaseModel):
    id: uuid.UUID
    status: str
    progress: int
    cost_credits: int
    prompt: str
    negative_prompt: str | None
    seed: int | None
    stages: list
    params: dict
    error_stage: str | None
    error_code: str | None
    error_message: str | None
    priority: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    result_image_ids: list[str] = []

    model_config = {"from_attributes": True}


class JobAccepted(BaseModel):
    job_id: uuid.UUID
    status: str
    cost_credits: int
    queue_position: int | None = None
    estimated_wait_seconds: int | None = None


class JobPage(BaseModel):
    items: list[JobOut]
    next_cursor: str | None = None
    has_more: bool = False


class PackRequest(BaseModel):
    """Avatar pack: generate across multiple styles (and variants) in one request."""

    prompt: str = Field(max_length=4000)
    negative_prompt: str | None = Field(default=None, max_length=4000)
    style_slugs: list[str] = Field(min_length=1, max_length=20)
    variants_per_style: int = Field(default=1, ge=1, le=4)
    stages: list[str] = Field(default_factory=lambda: ["generate"])
    reference_image_ids: list[uuid.UUID] = Field(default_factory=list)
    params: JobParams = Field(default_factory=JobParams)


class PackItem(BaseModel):
    job_id: uuid.UUID
    style_slug: str
    variant: int
    cost_credits: int
    status: str


class PackResponse(BaseModel):
    pack_id: str
    total_cost_credits: int
    jobs: list[PackItem]
