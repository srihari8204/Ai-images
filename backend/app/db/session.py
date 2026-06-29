"""Async SQLAlchemy engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

_engine_kwargs: dict = {"echo": settings.db_echo, "future": True}
# SQLite (used in tests/local) does not support the QueuePool sizing options.
if not settings.database_url.startswith("sqlite"):
    _engine_kwargs.update(
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
    )
# Managed Postgres (e.g. Neon) requires TLS; asyncpg takes it via connect_args.
if settings.db_requires_ssl:
    _engine_kwargs["connect_args"] = {"ssl": True}

engine = create_async_engine(settings.async_database_url, **_engine_kwargs)

SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
    class_=AsyncSession,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a session and commits / rolls back."""

    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
