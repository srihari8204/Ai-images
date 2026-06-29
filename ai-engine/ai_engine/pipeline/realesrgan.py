"""RealESRGAN upscaling stage."""

from __future__ import annotations

from PIL import Image as PILImage

from ai_engine.models import loader
from ai_engine.pipeline.base import StageContext, StageError
from app.core.config import settings

name = "realesrgan"


def run(ctx: StageContext) -> None:
    if ctx.image is None:
        raise StageError(name, "no_image", "No image to upscale")
    scale = max(2, min(int(ctx.params.get("upscale", 4)), 4))

    upsampler = loader.get_model("realesrgan")
    if upsampler is None:
        # Stand-in: high-quality Lanczos resample (bounded).
        target_w = min(ctx.image.width * scale, settings.max_resolution * 2)
        target_h = min(ctx.image.height * scale, settings.max_resolution * 2)
        ctx.image = ctx.image.resize((target_w, target_h), PILImage.LANCZOS)
        return
    import numpy as np  # type: ignore

    bgr = np.array(ctx.image.convert("RGB"))[:, :, ::-1]
    output, _ = upsampler.enhance(bgr, outscale=scale)
    ctx.image = PILImage.fromarray(output[:, :, ::-1])
