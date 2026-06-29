"""Image validation and EXIF stripping.

Validation order matters: cheap checks (size, magic bytes) run before decoding
the full image so a malicious or oversized payload is rejected early.
"""

from __future__ import annotations

import hashlib
import io

from PIL import Image as PILImage

from app.core.config import settings
from app.core.errors import (
    PayloadTooLargeError,
    UnsupportedMediaError,
    ValidationAppError,
)

# Magic-byte signatures for the allowed formats.
_MAGIC = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"RIFF": "image/webp",  # plus "WEBP" at offset 8, checked below
}


def detect_mime(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_and_normalize(data: bytes) -> dict:
    """Validate raw bytes and return normalized image metadata + clean bytes.

    Returns a dict: ``{mime, width, height, bytes, content_hash, data}`` where
    ``data`` is re-encoded with all EXIF/metadata stripped.
    Raises the appropriate ``AppError`` subclass on any violation.
    """

    if len(data) > settings.upload_max_bytes:
        raise PayloadTooLargeError(
            "File exceeds maximum allowed size",
            details={"max_bytes": settings.upload_max_bytes},
        )
    if not data:
        raise ValidationAppError("Empty file")

    mime = detect_mime(data)
    if mime is None or mime not in settings.upload_allowed_mime:
        raise UnsupportedMediaError(
            "File is not an allowed image type",
            details={"allowed": settings.upload_allowed_mime},
        )

    try:
        with PILImage.open(io.BytesIO(data)) as img:
            img.verify()  # detect truncated/corrupt files
        with PILImage.open(io.BytesIO(data)) as img:
            width, height = img.size
            fmt = img.format
            # Re-encode WITHOUT EXIF/metadata (strips GPS, device info, etc.).
            clean = io.BytesIO()
            save_kwargs = {}
            out_format = {"JPEG": "JPEG", "PNG": "PNG", "WEBP": "WEBP"}.get(fmt, "PNG")
            converted = img
            if out_format == "JPEG" and img.mode in ("RGBA", "P"):
                converted = img.convert("RGB")
            converted.save(clean, format=out_format, **save_kwargs)
            clean_bytes = clean.getvalue()
    except Exception as exc:  # noqa: BLE001
        raise ValidationAppError(f"Invalid or corrupt image: {exc}") from exc

    if width < settings.upload_min_dimension or height < settings.upload_min_dimension:
        raise ValidationAppError(
            "Image dimensions below minimum",
            details={"min": settings.upload_min_dimension},
        )
    if width > settings.upload_max_dimension or height > settings.upload_max_dimension:
        raise ValidationAppError(
            "Image dimensions exceed maximum",
            details={"max": settings.upload_max_dimension},
        )

    return {
        "mime": mime,
        "width": width,
        "height": height,
        "bytes": len(clean_bytes),
        "content_hash": hashlib.sha256(clean_bytes).hexdigest(),
        "data": clean_bytes,
    }
