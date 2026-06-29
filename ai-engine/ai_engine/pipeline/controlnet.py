"""ControlNet structural conditioning stage (pose / edge / depth).

Like InstantID, ControlNet conditioning is applied during the *generate* stage
(the control map constrains sampling). This stage validates the reference and the
requested control type, and is otherwise a no-op.
"""

from __future__ import annotations

import io

from PIL import Image as PILImage

from ai_engine.pipeline.base import StageContext, StageError

name = "controlnet"
_SUPPORTED = {"pose", "edge", "depth", "canny"}


def run(ctx: StageContext) -> None:
    control_type = ctx.params.get("control_type", "edge")
    if control_type not in _SUPPORTED:
        raise StageError(name, "unsupported_control", f"Unknown control type: {control_type}")
    if not ctx.reference_images:
        raise StageError(name, "missing_reference", "ControlNet requires a reference image")
    try:
        PILImage.open(io.BytesIO(ctx.reference_images[0])).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise StageError(name, "invalid_reference", "Reference image unreadable") from exc
    # Conditioning already applied at generate (or skipped in CPU stand-in mode).
    return
