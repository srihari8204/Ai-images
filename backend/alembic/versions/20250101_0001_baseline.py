"""Baseline schema for the AI Mirror Platform.

Creates all core tables (users, roles, sessions, images, jobs, credit ledger,
plans, subscriptions, payments, styles, moderation, feature flags, audit log)
from the ORM metadata, then layers on DDL that the ORM cannot express directly:
a case-insensitive unique index on user email and supporting partial indexes.

Revision ID: 0001_baseline
Revises:
Create Date: 2025-01-01
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.db.base import Base, import_all_models

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    import_all_models()
    # pgcrypto provides gen_random_uuid() used by the role seed below.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
    # Create every table defined on the shared metadata.
    Base.metadata.create_all(bind=bind)

    # Case-insensitive uniqueness on email (acts like citext without the ext).
    op.create_index(
        "uq_users_email_lower",
        "users",
        [sa.text("lower(email)")],
        unique=True,
    )

    # Seed the role catalog so registration can assign the default "user" role.
    op.execute(
        """
        INSERT INTO roles (id, name, description, created_at, updated_at)
        VALUES
          (gen_random_uuid(), 'user', 'Standard user', now(), now()),
          (gen_random_uuid(), 'moderator', 'Content moderator', now(), now()),
          (gen_random_uuid(), 'admin', 'Administrator', now(), now())
        ON CONFLICT (name) DO NOTHING;
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    import_all_models()
    op.drop_index("uq_users_email_lower", table_name="users")
    Base.metadata.drop_all(bind=bind)
