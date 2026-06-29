"""Shared async Redis client (cache, rate-limit counters, token denylist)."""

from __future__ import annotations

from functools import lru_cache

import redis.asyncio as aioredis

from app.core.config import settings


@lru_cache
def get_redis() -> aioredis.Redis:
    return aioredis.from_url(
        settings.redis_url, encoding="utf-8", decode_responses=True
    )


async def redis_health_check() -> bool:
    try:
        return bool(await get_redis().ping())
    except Exception:  # noqa: BLE001
        return False
