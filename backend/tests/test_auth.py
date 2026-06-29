"""Auth flows: registration, password strength, login, refresh rotation/reuse."""

from __future__ import annotations

import pytest

from app.core.errors import AuthError, ValidationAppError
from app.modules.auth import service
from app.modules.users.models import User, UserStatus
from sqlalchemy import select


@pytest.mark.asyncio
async def test_weak_password_rejected(db):
    with pytest.raises(ValidationAppError):
        await service.register(db, "a@b.com", "short", None)


@pytest.mark.asyncio
async def test_register_creates_unverified_user(db):
    await service.register(db, "new@user.com", "Str0ngPassw0rd", "New")
    user = (await db.execute(select(User).where(User.email == "new@user.com"))).scalar_one()
    assert user.email_verified_at is None
    assert user.password_hash and user.password_hash != "Str0ngPassw0rd"


@pytest.mark.asyncio
async def test_duplicate_email_no_second_record(db):
    await service.register(db, "dup@user.com", "Str0ngPassw0rd", None)
    await service.register(db, "dup@user.com", "Str0ngPassw0rd", None)
    rows = (await db.execute(select(User).where(User.email == "dup@user.com"))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_login_requires_verification(db):
    await service.register(db, "v@user.com", "Str0ngPassw0rd", None)
    with pytest.raises(AuthError):
        await service.login(db, "v@user.com", "Str0ngPassw0rd", user_agent=None, ip=None)


@pytest.mark.asyncio
async def test_refresh_rotation_and_reuse_detection(db):
    await service.register(db, "r@user.com", "Str0ngPassw0rd", None)
    user = (await db.execute(select(User).where(User.email == "r@user.com"))).scalar_one()
    # register() already assigned the default 'user' role; just verify the email.
    from datetime import datetime, timezone

    user.email_verified_at = datetime.now(timezone.utc)
    await db.flush()

    _, refresh1, _ = await service.login(db, "r@user.com", "Str0ngPassw0rd", user_agent=None, ip=None)
    _, refresh2, _ = await service.refresh(db, refresh1, user_agent=None, ip=None)
    assert refresh1 != refresh2

    # Reusing the old (rotated) token triggers reuse detection.
    with pytest.raises(AuthError):
        await service.refresh(db, refresh1, user_agent=None, ip=None)
