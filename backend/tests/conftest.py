"""Test fixtures.

Tests run against an in-memory SQLite database with the storage, redis, queue,
and safety layers stubbed so the domain logic (auth, credits, pipeline pricing,
payments idempotency) is exercised without external services.
"""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base, import_all_models


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    import_all_models()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture(autouse=True)
def stub_externals(monkeypatch):
    """Stub Redis-backed rate limiting and object storage."""

    async def _no_limit(*args, **kwargs):
        return None

    monkeypatch.setattr("app.core.rate_limit.enforce_auth_limit", _no_limit)
    monkeypatch.setattr("app.storage.object_store.put_object", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.storage.object_store.presign_get", lambda *a, **k: "http://obj/url"
    )
    yield
