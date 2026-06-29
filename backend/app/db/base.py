"""SQLAlchemy declarative base and common column mixins."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.ids import uuid7

# JSONB on Postgres, plain JSON elsewhere (e.g. SQLite in tests).
JSONType = JSON().with_variant(JSONB, "postgresql")


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    # Resolve bare ``Mapped[dict]`` / ``Mapped[list]`` annotations to a JSON column.
    type_annotation_map = {
        dict: JSONType,
        list: JSONType,
    }


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)


# Import all model modules so Alembic autogenerate / metadata.create_all see them.
def import_all_models() -> None:  # pragma: no cover - import side effects only
    from app.modules.users import models as _users  # noqa: F401
    from app.modules.uploads import models as _uploads  # noqa: F401
    from app.modules.styles import models as _styles  # noqa: F401
    from app.modules.pipeline import models as _pipeline  # noqa: F401
    from app.modules.credits import models as _credits  # noqa: F401
    from app.modules.payments import models as _payments  # noqa: F401
    from app.modules.admin import models as _admin  # noqa: F401
