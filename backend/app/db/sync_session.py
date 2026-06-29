"""Synchronous SQLAlchemy session for the RQ worker process.

The worker runs synchronous GPU code, so it uses a blocking psycopg2 engine
rather than asyncpg. It shares the same ORM models and (sync re-implementations
of) the credit-ledger invariants so finalization stays correct and idempotent.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

_sync_kwargs: dict = {"future": True}
if not settings.sync_database_url.startswith("sqlite"):
    _sync_kwargs.update(pool_pre_ping=True, pool_size=10, max_overflow=5)

sync_engine = create_engine(settings.sync_database_url, **_sync_kwargs)

SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
