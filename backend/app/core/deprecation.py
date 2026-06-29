"""Deprecation signalling.

Use ``deprecated(sunset=...)`` as a route dependency to emit RFC 8594
``Deprecation`` and ``Sunset`` headers plus a ``Link`` to the replacement, so
clients are warned before an endpoint is removed (API docs requirement 12.4).
"""

from __future__ import annotations

from fastapi import Response


def deprecated(*, sunset: str, successor: str | None = None):
    async def _dep(response: Response) -> None:
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = sunset  # HTTP-date or ISO date
        if successor:
            response.headers["Link"] = f'<{successor}>; rel="successor-version"'

    return _dep
