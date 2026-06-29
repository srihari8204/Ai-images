"""Cryptographic primitives: password hashing, JWTs, and opaque tokens.

- Passwords use Argon2id (memory-hard) via argon2-cffi.
- Access tokens are short-lived signed JWTs validated statelessly by any replica.
- Refresh / verification / reset tokens are high-entropy opaque strings; only
  their SHA-256 hash is ever stored, so a DB leak cannot replay them.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings

_ph = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2)


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, Exception):  # noqa: BLE001
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _ph.check_needs_rehash(password_hash)
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- #
# JWT access tokens
# --------------------------------------------------------------------------- #
def create_access_token(
    *,
    subject: str,
    roles: list[str],
    extra: dict[str, Any] | None = None,
    ttl_seconds: int | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    ttl = ttl_seconds or settings.access_token_ttl_seconds
    payload: dict[str, Any] = {
        "sub": subject,
        "roles": roles,
        "type": "access",
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl)).timestamp()),
        "jti": secrets.token_urlsafe(8),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and verify an access token. Raises ``jwt.PyJWTError`` on failure."""

    payload = jwt.decode(
        token,
        settings.secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "sub", "type"]},
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("not an access token")
    return payload


# --------------------------------------------------------------------------- #
# Opaque tokens (refresh, email verification, password reset, share)
# --------------------------------------------------------------------------- #
def generate_opaque_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)
