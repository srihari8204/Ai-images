"""Style catalog service: cached listing, resolution, and entitlement checks."""

from __future__ import annotations

import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ForbiddenError
from app.core.redis import get_redis
from app.modules.styles.models import Style

_CACHE_KEY = "styles:catalog:v1"
_CACHE_TTL = 300


def _serialize(style: Style) -> dict:
    return {
        "id": str(style.id),
        "slug": style.slug,
        "name": style.name,
        "category": style.category,
        "description": style.description,
        "cost_multiplier": float(style.cost_multiplier),
        "plan_gate": style.plan_gate,
        "preview_image_id": str(style.preview_image_id) if style.preview_image_id else None,
    }


async def list_active_styles(db: AsyncSession) -> list[dict]:
    """Return the active style catalog, served from a short-lived Redis cache."""

    redis = get_redis()
    cached = await redis.get(_CACHE_KEY)
    if cached:
        return json.loads(cached)

    rows = (
        await db.execute(
            select(Style).where(Style.is_active.is_(True)).order_by(Style.category, Style.name)
        )
    ).scalars().all()
    payload = [_serialize(s) for s in rows]
    await redis.set(_CACHE_KEY, json.dumps(payload), ex=_CACHE_TTL)
    return payload


async def invalidate_cache() -> None:
    await get_redis().delete(_CACHE_KEY)


async def get_by_slug(db: AsyncSession, slug: str) -> Style | None:
    return (
        await db.execute(select(Style).where(Style.slug == slug))
    ).scalar_one_or_none()


async def get_active_or_400(db: AsyncSession, style_id: uuid.UUID) -> Style:
    style = await db.get(Style, style_id)
    if style is None or not style.is_active:
        raise AppError("Unknown or inactive style", code="unknown_style", status_code=400)
    return style


def _user_plan_slugs(user) -> set[str]:
    # Plan entitlements are derived from the user's settings (set on subscription
    # fulfilment). Free users have the implicit "free" entitlement.
    plans = set((user.settings_json or {}).get("plans", []))
    plans.add("free")
    return plans


async def resolve_style(db: AsyncSession, style_id: uuid.UUID, user) -> dict:
    """Resolve a style id into concrete generation parameters, enforcing the
    plan gate. Returns the style's template/negative/params/cost_multiplier."""

    style = await get_active_or_400(db, style_id)
    if style.plan_gate and style.plan_gate not in _user_plan_slugs(user):
        raise ForbiddenError(
            "This style requires a higher plan",
            code="style_not_entitled",
            details={"required_plan": style.plan_gate},
        )
    return {
        "style_id": str(style.id),
        "template": style.template,
        "negative_prompt": style.negative_prompt,
        "model_ref": style.model_ref,
        "lora_refs": style.lora_refs,
        "default_params": style.default_params,
        "cost_multiplier": float(style.cost_multiplier),
    }
