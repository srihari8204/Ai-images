"""Authentication domain service.

Implements registration (Argon2id), email verification, login with rotating
refresh tokens + reuse detection, password reset, and session revocation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.email import send_password_reset_email, send_verification_email
from app.core.errors import AuthError, ValidationAppError
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.core.security import (
    create_access_token,
    generate_opaque_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.modules.users.models import (
    Role,
    Session,
    User,
    UserStatus,
    VerificationToken,
)

logger = get_logger(__name__)

# A small breached-password sample; production wires this to a k-anonymity HIBP
# range query. Kept inline so the strength check works offline in dev/test.
_COMMON_PASSWORDS = {
    "password",
    "12345678",
    "qwerty123",
    "password1",
    "letmein123",
    "iloveyou1",
    "admin1234",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_past(dt: datetime) -> bool:
    """Expiry check that tolerates naive datetimes (treated as UTC)."""

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt < _now()


def validate_password_strength(password: str) -> None:
    if len(password) < settings.password_min_length:
        raise ValidationAppError(
            f"Password must be at least {settings.password_min_length} characters",
            details={"field": "password"},
        )
    if password.lower() in _COMMON_PASSWORDS:
        raise ValidationAppError(
            "Password is too common / has appeared in breaches",
            details={"field": "password"},
        )
    if password.isalpha() or password.isdigit():
        raise ValidationAppError(
            "Password must mix letters and numbers",
            details={"field": "password"},
        )


async def _get_user_by_email(db: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(func.lower(User.email) == email.lower())
    return (await db.execute(stmt)).scalar_one_or_none()


async def _default_role(db: AsyncSession) -> Role:
    role = (
        await db.execute(select(Role).where(Role.name == "user"))
    ).scalar_one_or_none()
    if role is None:
        role = Role(name="user", description="Standard user")
        db.add(role)
        await db.flush()
    return role


# --------------------------------------------------------------------------- #
# Registration & verification
# --------------------------------------------------------------------------- #
async def register(
    db: AsyncSession, email: str, password: str, display_name: str | None
) -> None:
    """Register a new user. Returns nothing — the caller always responds with a
    generic success so account existence is never disclosed."""

    validate_password_strength(password)
    existing = await _get_user_by_email(db, email)
    if existing is not None:
        # Do not reveal existence; silently no-op (optionally resend verification).
        logger.info("register_duplicate_email", email=email)
        return

    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name=display_name,
        status=UserStatus.ACTIVE,
    )
    user.roles.append(await _default_role(db))
    db.add(user)
    await db.flush()

    token = await _issue_verification_token(db, user, "verify_email",
                                            settings.email_verification_ttl_seconds)
    send_verification_email(user.email, token)
    logger.info("user_registered", user_id=str(user.id))


async def _issue_verification_token(
    db: AsyncSession, user: User, purpose: str, ttl: int
) -> str:
    raw = generate_opaque_token()
    db.add(
        VerificationToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=hash_token(raw),
            expires_at=_now() + timedelta(seconds=ttl),
        )
    )
    await db.flush()
    return raw


async def verify_email(db: AsyncSession, token: str) -> None:
    record = (
        await db.execute(
            select(VerificationToken).where(
                VerificationToken.token_hash == hash_token(token),
                VerificationToken.purpose == "verify_email",
            )
        )
    ).scalar_one_or_none()
    if record is None or record.used_at is not None or _is_past(record.expires_at):
        raise AuthError("Invalid or expired verification token", code="invalid_token")
    record.used_at = _now()
    user = await db.get(User, record.user_id)
    if user and user.email_verified_at is None:
        user.email_verified_at = _now()
    logger.info("email_verified", user_id=str(record.user_id))


# --------------------------------------------------------------------------- #
# Login / refresh / logout
# --------------------------------------------------------------------------- #
async def _create_session(
    db: AsyncSession,
    user: User,
    *,
    family_id: uuid.UUID | None = None,
    user_agent: str | None = None,
    ip: str | None = None,
) -> tuple[str, Session]:
    raw_refresh = generate_opaque_token(48)
    session = Session(
        user_id=user.id,
        refresh_token_hash=hash_token(raw_refresh),
        family_id=family_id or uuid.uuid4(),
        user_agent=user_agent,
        ip=ip,
        expires_at=_now() + timedelta(seconds=settings.refresh_token_ttl_seconds),
    )
    db.add(session)
    await db.flush()
    return raw_refresh, session


def _issue_access(user: User) -> str:
    return create_access_token(subject=str(user.id), roles=user.role_names)


async def login(
    db: AsyncSession, email: str, password: str, *, user_agent: str | None, ip: str | None
) -> tuple[str, str, User]:
    user = await _get_user_by_email(db, email)
    # Constant-ish work even on unknown user to reduce timing oracle.
    if user is None or not user.password_hash or not verify_password(password, user.password_hash):
        raise AuthError("Invalid credentials", code="invalid_credentials")
    if user.status == UserStatus.SUSPENDED:
        raise AuthError("Account suspended", code="account_suspended")
    if user.status == UserStatus.DELETED:
        raise AuthError("Invalid credentials", code="invalid_credentials")
    if not user.is_verified:
        raise AuthError("Email not verified", code="email_unverified")

    raw_refresh, _ = await _create_session(db, user, user_agent=user_agent, ip=ip)
    logger.info("login_success", user_id=str(user.id))
    return _issue_access(user), raw_refresh, user


async def refresh(
    db: AsyncSession, raw_refresh: str, *, user_agent: str | None, ip: str | None
) -> tuple[str, str, User]:
    token_hash = hash_token(raw_refresh)
    session = (
        await db.execute(
            select(Session).where(Session.refresh_token_hash == token_hash)
        )
    ).scalar_one_or_none()

    if session is None:
        raise AuthError("Invalid refresh token", code="invalid_refresh")

    # Reuse detection: a token already rotated (revoked) but presented again means
    # the token was leaked — revoke the entire family.
    if session.revoked_at is not None:
        await _revoke_family(db, session.family_id)
        logger.warning("refresh_reuse_detected", family_id=str(session.family_id))
        raise AuthError("Refresh token reuse detected", code="refresh_reuse")

    if _is_past(session.expires_at):
        raise AuthError("Refresh token expired", code="refresh_expired")

    user = await db.get(User, session.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise AuthError("User unavailable", code="user_unavailable")

    # Rotate: revoke current, issue new in same family.
    session.revoked_at = _now()
    new_refresh, _ = await _create_session(
        db, user, family_id=session.family_id, user_agent=user_agent, ip=ip
    )
    # reload roles for token
    await db.refresh(user, attribute_names=["roles"])
    return _issue_access(user), new_refresh, user


async def _revoke_family(db: AsyncSession, family_id: uuid.UUID) -> None:
    sessions = (
        await db.execute(select(Session).where(Session.family_id == family_id))
    ).scalars().all()
    for s in sessions:
        if s.revoked_at is None:
            s.revoked_at = _now()


async def logout(db: AsyncSession, raw_refresh: str) -> None:
    session = (
        await db.execute(
            select(Session).where(Session.refresh_token_hash == hash_token(raw_refresh))
        )
    ).scalar_one_or_none()
    if session and session.revoked_at is None:
        session.revoked_at = _now()


async def revoke_all_sessions(db: AsyncSession, user_id: uuid.UUID) -> None:
    sessions = (
        await db.execute(
            select(Session).where(
                Session.user_id == user_id, Session.revoked_at.is_(None)
            )
        )
    ).scalars().all()
    for s in sessions:
        s.revoked_at = _now()


# --------------------------------------------------------------------------- #
# Password reset
# --------------------------------------------------------------------------- #
async def forgot_password(db: AsyncSession, email: str) -> None:
    user = await _get_user_by_email(db, email)
    if user is None:
        logger.info("forgot_password_unknown_email")
        return  # generic response regardless
    token = await _issue_verification_token(
        db, user, "reset", settings.password_reset_ttl_seconds
    )
    send_password_reset_email(user.email, token)


async def reset_password(db: AsyncSession, token: str, new_password: str) -> None:
    validate_password_strength(new_password)
    record = (
        await db.execute(
            select(VerificationToken).where(
                VerificationToken.token_hash == hash_token(token),
                VerificationToken.purpose == "reset",
            )
        )
    ).scalar_one_or_none()
    if record is None or record.used_at is not None or _is_past(record.expires_at):
        raise AuthError("Invalid or expired reset token", code="invalid_token")
    record.used_at = _now()
    user = await db.get(User, record.user_id)
    if user is None:
        raise AuthError("Invalid or expired reset token", code="invalid_token")
    user.password_hash = hash_password(new_password)
    await revoke_all_sessions(db, user.id)
    logger.info("password_reset", user_id=str(user.id))
