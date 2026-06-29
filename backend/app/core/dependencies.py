"""Shared FastAPI dependencies: auth, current user, RBAC, idempotency."""

from __future__ import annotations

import uuid
from typing import Annotated

import jwt
from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import AuthError, ForbiddenError
from app.core.logging import user_id_ctx
from app.core.redis import get_redis
from app.core.security import decode_access_token
from app.db.session import get_db
from app.modules.users.models import User, UserStatus

DbSession = Annotated[AsyncSession, Depends(get_db)]


def get_client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


async def _load_user(db: AsyncSession, user_id: str) -> User | None:
    stmt = (
        select(User)
        .options(selectinload(User.roles))
        .where(User.id == uuid.UUID(user_id))
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_current_user(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("Missing or malformed Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Access token expired", code="token_expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthError("Invalid access token") from exc

    # Access-token revocation list (set on logout / password reset / suspend).
    jti = payload.get("jti")
    if jti and await get_redis().get(f"jwt:revoked:{jti}"):
        raise AuthError("Token has been revoked")

    user = await _load_user(db, payload["sub"])
    if user is None or user.status == UserStatus.DELETED:
        raise AuthError("User not found")
    if user.status == UserStatus.SUSPENDED:
        raise ForbiddenError("Account suspended", code="account_suspended")

    user_id_ctx.set(str(user.id))
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: str):
    """Dependency factory enforcing that the current user has any of ``roles``."""

    async def _guard(user: CurrentUser) -> User:
        if not set(roles) & set(user.role_names):
            raise ForbiddenError(
                f"Requires one of roles: {', '.join(roles)}", code="forbidden_role"
            )
        return user

    return _guard


require_admin = require_roles("admin")
require_staff = require_roles("admin", "moderator")


async def get_idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str | None:
    return idempotency_key
