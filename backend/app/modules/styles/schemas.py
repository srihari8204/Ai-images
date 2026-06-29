"""Style API schemas."""

from __future__ import annotations

from pydantic import BaseModel


class StyleSummary(BaseModel):
    id: str
    slug: str
    name: str
    category: str
    description: str | None
    cost_multiplier: float
    plan_gate: str | None
    preview_image_id: str | None


class StyleDetail(StyleSummary):
    template: str
    negative_prompt: str | None
    model_ref: str
    default_params: dict
