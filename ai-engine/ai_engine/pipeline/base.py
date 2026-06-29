"""Pipeline stage contract and shared context (design D8).

Each stage is a composable unit with its own retry/timeout that consumes the
artifact produced by the previous stage and emits the next. Failures raise
``StageError`` carrying the stage name, an error code, and whether the error is
transient (eligible for retry-with-backoff).
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Protocol

from PIL import Image as PILImage


class StageError(Exception):
    def __init__(self, stage: str, code: str, message: str, *, transient: bool = False):
        super().__init__(message)
        self.stage = stage
        self.code = code
        self.message = message
        self.transient = transient


@dataclass
class StageContext:
    """Mutable state threaded through the stage sequence."""

    job_id: str
    user_id: str
    prompt: str
    negative_prompt: str
    seed: int | None
    params: dict
    reference_images: list[bytes] = field(default_factory=list)
    # Requested stage list, so the generate stage can apply conditioning
    # (InstantID / ControlNet) at generation time when those stages are requested.
    stages: list[str] = field(default_factory=list)
    # Current working image (PIL). The "generate" stage seeds it.
    image: PILImage.Image | None = None
    # Auxiliary outputs (e.g. transparent-bg variant) keyed by label.
    extra_outputs: dict[str, PILImage.Image] = field(default_factory=dict)

    def image_bytes(self, fmt: str = "PNG") -> bytes:
        if self.image is None:
            raise StageError("finalize", "no_image", "No image produced")
        buf = io.BytesIO()
        self.image.save(buf, format=fmt)
        return buf.getvalue()


class Stage(Protocol):
    name: str

    def run(self, ctx: StageContext) -> None:
        ...
