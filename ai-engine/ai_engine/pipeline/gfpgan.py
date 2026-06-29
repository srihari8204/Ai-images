"""GFPGAN face restoration stage."""

from __future__ import annotations

from PIL import Image as PILImage, ImageEnhance

from ai_engine.models import loader
from ai_engine.pipeline.base import StageContext, StageError

name = "gfpgan"


def run(ctx: StageContext) -> None:
    if ctx.image is None:
        raise StageError(name, "no_image", "No image to restore")
    restorer = loader.get_model("gfpgan")
    if restorer is None:
        # Stand-in: mild sharpness/contrast bump approximates restoration.
        ctx.image = ImageEnhance.Sharpness(ctx.image).enhance(1.4)
        ctx.image = ImageEnhance.Contrast(ctx.image).enhance(1.05)
        return
    import numpy as np  # type: ignore

    bgr = np.array(ctx.image.convert("RGB"))[:, :, ::-1]
    _, _, restored = restorer.enhance(
        bgr, has_aligned=False, only_center_face=False, paste_back=True
    )
    ctx.image = PILImage.fromarray(restored[:, :, ::-1])
