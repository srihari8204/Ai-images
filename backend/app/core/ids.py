"""UUIDv7 generation (time-ordered ids).

UUIDv7 keeps primary keys roughly insertion-ordered which is friendly to B-tree
indexes while remaining globally unique. Implemented locally to avoid a hard
dependency on a specific uuid7 library / Python version.
"""

from __future__ import annotations

import os
import time
import uuid


def uuid7() -> uuid.UUID:
    """Return a UUID version 7 (RFC 9562) using millisecond Unix time."""

    unix_ms = int(time.time() * 1000)
    rand_a = int.from_bytes(os.urandom(2), "big") & 0x0FFF
    rand_b = int.from_bytes(os.urandom(8), "big")

    value = (unix_ms & 0xFFFFFFFFFFFF) << 80
    value |= 0x7 << 76  # version 7
    value |= rand_a << 64
    value |= (0b10 << 62)  # variant
    value |= rand_b & ((1 << 62) - 1)
    return uuid.UUID(int=value)


def uuid7_str() -> str:
    return str(uuid7())
