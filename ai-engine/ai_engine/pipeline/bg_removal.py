"""Background-removal stage — produces a transparent-background PNG.

The transparent variant is stored as an additional output alongside the original
(the spec requires both).
"""

from __future__ import annotations

from PIL import Image as PILImage

from ai_engine.models import loader
from ai_engine.pipeline.base import StageContext, StageError

name = "bg_removal"


def _naive_alpha(img: PILImage.Image) -> PILImage.Image:
    """Stand-in: make near-corner-colored pixels transparent (no rembg/U^2-Net)."""

    img = img.convert("RGBA")
    bg = img.getpixel((0, 0))
    tol = 40
    out = [
        (px[0], px[1], px[2], 0)
        if abs(px[0] - bg[0]) < tol and abs(px[1] - bg[1]) < tol and abs(px[2] - bg[2]) < tol
        else px
        for px in img.getdata()
    ]
    img.putdata(out)
    return img


def run(ctx: StageContext) -> None:
    if ctx.image is None:
        raise StageError(name, "no_image", "No image for background removal")
    session = loader.get_model("rembg")
    if session is None:
        transparent = _naive_alpha(ctx.image)
    else:
        from rembg import remove  # type: ignore

        transparent = remove(ctx.image.convert("RGBA"), session=session)
    ctx.extra_outputs["transparent"] = transparent
