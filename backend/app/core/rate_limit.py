"""Redis fixed-window rate limiter.

Used to throttle authentication endpoints per-IP and per-account. Returns the
number of seconds the caller must wait when the limit is exceeded so the route
can emit a ``Retry-After`` header.
"""

from __future__ import annotations

from app.core.config import settings
from app.core.redis import get_redis


async def hit(key: str, *, limit: int, window: int) -> tuple[bool, int]:
    """Register one hit against ``key``.

    Returns ``(allowed, retry_after_seconds)``.
    """

    redis = get_redis()
    redis_key = f"rl:{key}"
    pipe = redis.pipeline()
    pipe.incr(redis_key)
    pipe.ttl(redis_key)
    count, ttl = await pipe.execute()
    if count == 1 or ttl < 0:
        await redis.expire(redis_key, window)
        ttl = window
    if count > limit:
        return False, max(ttl, 1)
    return True, 0


async def enforce_auth_limit(ip: str | None, account: str | None) -> None:
    """Throttle an auth attempt by IP and account; raise on breach."""

    from app.core.errors import RateLimitError

    window = settings.rate_limit_window_seconds
    if ip:
        allowed, retry = await hit(
            f"auth:ip:{ip}", limit=settings.rate_limit_auth_per_ip, window=window
        )
        if not allowed:
            raise RateLimitError(
                "Too many attempts from this IP",
                headers={"Retry-After": str(retry)},
            )
    if account:
        allowed, retry = await hit(
            f"auth:acct:{account.lower()}",
            limit=settings.rate_limit_auth_per_account,
            window=window,
        )
        if not allowed:
            raise RateLimitError(
                "Too many attempts for this account",
                headers={"Retry-After": str(retry)},
            )
