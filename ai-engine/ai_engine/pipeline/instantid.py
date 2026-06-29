"""InstantID face-consistency stage.

Identity conditioning is applied during the *generate* stage (the InstantID SDXL
pipeline needs the face embedding at sampling time). This stage therefore just
validates that a usable reference exists and fails early with a user-safe error
otherwise. Consent is enforced upstream at job submission.
"""

from __future__ import annotations

import io

from PIL import Image as PILImage

from ai_engine.pipeline.base import StageContext, StageError

name = "instantid"


def run(ctx: StageContext) -> None:
    if not ctx.reference_images:
        raise StageError(
            name, "missing_reference", "Face consistency requires a reference image"
        )
    try:
        PILImage.open(io.BytesIO(ctx.reference_images[0])).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise StageError(name, "invalid_reference", "Reference image unreadable") from exc
    # Conditioning already applied at generate (or skipped in CPU stand-in mode).
    return
