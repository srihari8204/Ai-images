"""Opaque cursor pagination helpers.

Cursors encode the ``(created_at, id)`` of the last item so pages are stable
under inserts. They are base64url-encoded JSON — opaque to clients.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False


def encode_cursor(created_at: Any, item_id: str) -> str:
    raw = json.dumps({"c": str(created_at), "i": str(item_id)}).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode())
        data = json.loads(raw)
        return data["c"], data["i"]
    except Exception as exc:  # noqa: BLE001
        raise ValueError("invalid cursor") from exc
