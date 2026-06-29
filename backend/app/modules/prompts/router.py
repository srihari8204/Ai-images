"""Prompt preview endpoint — compose + validate + safety-check without generating."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.dependencies import CurrentUser, DbSession
from app.modules.prompts import service
from app.modules.prompts.schemas import PromptPreviewRequest, PromptPreviewResponse
from app.modules.styles import service as styles_service

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.post("/preview", response_model=PromptPreviewResponse, summary="Preview a prompt")
async def preview(
    req: PromptPreviewRequest, user: CurrentUser, db: DbSession
) -> PromptPreviewResponse:
    template = None
    style_negative = None
    if req.style_slug:
        style = await styles_service.get_by_slug(db, req.style_slug)
        if style:
            template = style.template
            style_negative = style.negative_prompt

    final, final_negative = service.compose(
        req.prompt,
        template=template,
        style_negative=style_negative,
        user_negative=req.negative_prompt,
    )
    # Screen but do not raise here — preview reports safety rather than blocking.
    safe = True
    from app.core import safety

    if not safety.score_prompt(final).allowed:
        safe = False

    return PromptPreviewResponse(
        final_prompt=final,
        final_negative_prompt=final_negative,
        safe=safe,
        estimated_tokens=service._estimate_tokens(final)
        + service._estimate_tokens(final_negative),
    )
