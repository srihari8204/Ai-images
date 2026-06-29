"""Style catalog endpoints (cached)."""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.core.dependencies import DbSession
from app.core.errors import NotFoundError
from app.modules.styles import service
from app.modules.styles.schemas import StyleDetail, StyleSummary

router = APIRouter(prefix="/styles", tags=["styles"])


@router.get("", response_model=list[StyleSummary], summary="List active styles")
async def list_styles(db: DbSession, response: Response) -> list[StyleSummary]:
    response.headers["Cache-Control"] = "public, max-age=300"
    return [StyleSummary(**s) for s in await service.list_active_styles(db)]


@router.get("/{slug}", response_model=StyleDetail, summary="Style detail")
async def get_style(slug: str, db: DbSession) -> StyleDetail:
    style = await service.get_by_slug(db, slug)
    if style is None or not style.is_active:
        raise NotFoundError("Style not found")
    return StyleDetail(
        id=str(style.id),
        slug=style.slug,
        name=style.name,
        category=style.category,
        description=style.description,
        cost_multiplier=float(style.cost_multiplier),
        plan_gate=style.plan_gate,
        preview_image_id=str(style.preview_image_id) if style.preview_image_id else None,
        template=style.template,
        negative_prompt=style.negative_prompt,
        model_ref=style.model_ref,
        default_params=style.default_params,
    )
