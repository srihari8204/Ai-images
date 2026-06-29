"""Image validation + EXIF stripping."""

from __future__ import annotations

import io

import pytest
from PIL import Image as PILImage

from app.core.errors import UnsupportedMediaError, ValidationAppError
from app.modules.uploads.validation import detect_mime, validate_and_normalize


def _png_bytes(size=(128, 128), color=(10, 20, 30)) -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def test_detect_mime_png():
    assert detect_mime(_png_bytes()) == "image/png"


def test_reject_non_image():
    with pytest.raises(UnsupportedMediaError):
        validate_and_normalize(b"this is not an image at all")


def test_reject_tiny_dimensions():
    with pytest.raises(ValidationAppError):
        validate_and_normalize(_png_bytes(size=(10, 10)))


def test_valid_image_normalized():
    meta = validate_and_normalize(_png_bytes())
    assert meta["mime"] == "image/png"
    assert meta["width"] == 128 and meta["height"] == 128
    assert len(meta["content_hash"]) == 64
    assert isinstance(meta["data"], bytes)
