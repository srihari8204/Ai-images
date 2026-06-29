"""Prompt API schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PromptPreviewRequest(BaseModel):
    prompt: str = Field(max_length=4000)
    style_slug: str | None = None
    negative_prompt: str | None = Field(default=None, max_length=4000)


class PromptPreviewResponse(BaseModel):
    final_prompt: str
    final_negative_prompt: str
    safe: bool
    estimated_tokens: int
