"""Maintenance tasks: data-export archive build and retention purge.

These run on the ``maintenance`` queue (export) and via the scheduler (purge).
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.email import send_export_ready_email
from app.core.logging import get_logger
from app.db.sync_session import session_scope
from app.storage import object_store

logger = get_logger("worker.tasks")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def build_data_export(export_id: str) -> dict:
    """Assemble a downloadable ZIP of the user's profile, generations, ledger."""

    from app.modules.credits.models import CreditTransaction
    from app.modules.pipeline.models import Job
    from app.modules.uploads.models import Image
    from app.modules.users.models import DataExport, User

    with session_scope() as db:
        export = db.get(DataExport, uuid.UUID(export_id))
        if export is None:
            return {"status": "missing"}
        user = db.get(User, export.user_id)
        if user is None:
            export.status = "failed"
            return {"status": "failed"}

        images = db.execute(select(Image).where(Image.user_id == user.id)).scalars().all()
        jobs = db.execute(select(Job).where(Job.user_id == user.id)).scalars().all()
        txns = db.execute(
            select(CreditTransaction).where(CreditTransaction.user_id == user.id)
        ).scalars().all()

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "profile.json",
                json.dumps(
                    {
                        "id": str(user.id),
                        "email": user.email,
                        "display_name": user.display_name,
                        "locale": user.locale,
                        "created_at": user.created_at.isoformat(),
                    },
                    indent=2,
                ),
            )
            zf.writestr(
                "generations.json",
                json.dumps(
                    [
                        {"id": str(j.id), "prompt": j.prompt, "status": j.status.value,
                         "created_at": j.created_at.isoformat()}
                        for j in jobs
                    ],
                    indent=2,
                ),
            )
            zf.writestr(
                "ledger.json",
                json.dumps(
                    [
                        {"id": str(t.id), "type": t.type.value, "amount": t.amount,
                         "created_at": t.created_at.isoformat()}
                        for t in txns
                    ],
                    indent=2,
                ),
            )
            # Include the actual image objects.
            for img in images:
                try:
                    data = object_store.get_object(img.bucket, img.object_key)
                    zf.writestr(f"images/{img.id}.{img.mime.split('/')[-1]}", data)
                except Exception:  # noqa: BLE001
                    continue

        key = f"exports/{user.id}/{export_id}.zip"
        object_store.put_object(settings.bucket_exports, key, buf.getvalue(), "application/zip")
        export.object_key = key
        export.status = "ready"
        export.completed_at = _now()
        email = user.email

    url = object_store.presign_get(settings.bucket_exports, key, ttl=86400)
    send_export_ready_email(email, url)
    logger.info("data_export_ready", export_id=export_id)
    return {"status": "ready", "object_key": key}


def purge_expired() -> dict:
    """Hard-purge soft-deleted images/users past their retention window."""

    from app.modules.uploads.models import Image
    from app.modules.users.models import User, UserStatus

    purged = 0
    with session_scope() as db:
        images = db.execute(
            select(Image).where(
                Image.deleted_at.is_not(None), Image.purge_after < _now()
            )
        ).scalars().all()
        for img in images:
            try:
                object_store.delete_object(img.bucket, img.object_key)
            except Exception:  # noqa: BLE001
                pass
            db.delete(img)
            purged += 1

        users = db.execute(
            select(User).where(
                User.status == UserStatus.DELETED, User.purge_after < _now()
            )
        ).scalars().all()
        for user in users:
            # Scrub remaining PII; keep the row for audit/ledger integrity.
            user.email = f"purged_{user.id}@deleted.local"
            user.password_hash = None
            user.settings_json = {}
            user.purge_after = None

    logger.info("purge_complete", images_purged=purged)
    return {"images_purged": purged}
