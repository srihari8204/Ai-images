"""Base image generation stage.

Selects the generation pipeline based on the configured backend and the requested
stages:

- ``GENERATION_BACKEND=flux`` (production GPU):
    * InstantID requested + reference present  -> InstantID (SDXL) identity gen
    * ControlNet requested + reference present  -> FLUX + ControlNet structure gen
    * otherwise                                 -> FLUX base
- ``GENERATION_BACKEND=sdturbo`` (local CPU test): real SD-Turbo / small-SD
- anything unavailable                          -> deterministic CPU stand-in

Resolution, seed, guidance, and steps are honoured within configured bounds.
InstantID/ControlNet conditioning happens HERE (at generation), so their dedicated
stages become light validators downstream.
"""

from __future__ import annotations

import hashlib
import io

from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont

from ai_engine.models import loader
from ai_engine.pipeline.base import StageContext, StageError
from app.core.config import settings

name = "generate"

MAX_STEPS = settings.max_steps
MAX_RES = settings.max_resolution


def _clamp_params(params: dict) -> tuple[int, int, int, float]:
    width = min(max(int(params.get("width", 1024)), 256), MAX_RES)
    height = min(max(int(params.get("height", 1024)), 256), MAX_RES)
    steps = min(max(int(params.get("steps", 28)), 1), MAX_STEPS)
    guidance = float(params.get("guidance", 3.5))
    return width, height, steps, guidance


def _seed(ctx: StageContext) -> int:
    if ctx.seed is not None:
        return ctx.seed
    return int(hashlib.sha256(ctx.job_id.encode()).hexdigest()[:8], 16)


def _ref_image(ctx: StageContext):
    if not ctx.reference_images:
        return None
    return PILImage.open(io.BytesIO(ctx.reference_images[0])).convert("RGB")


def _deterministic_image(prompt: str, seed: int, w: int, h: int) -> PILImage.Image:
    """Reproducible placeholder so seed/prompt -> stable output (no model)."""

    digest = hashlib.sha256(f"{prompt}:{seed}".encode()).digest()
    r, g, b = digest[0], digest[1], digest[2]
    r2, g2, b2 = digest[3], digest[4], digest[5]
    img = PILImage.new("RGB", (w, h), (r, g, b))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(h - 1, 1)
        draw.line([(0, y), (w, y)], fill=(int(r + (r2 - r) * t), int(g + (g2 - g) * t), int(b + (b2 - b) * t)))
    try:
        draw.text((12, 12), f"AI Mirror\nseed={seed}", fill=(255, 255, 255), font=ImageFont.load_default())
    except Exception:  # noqa: BLE001
        pass
    return img


# --------------------------------------------------------------------------- #
# Backends
# --------------------------------------------------------------------------- #
def _run_sd(ctx: StageContext, seed: int) -> bool:
    pipe = loader.get_model("sd-turbo")
    if pipe is None:
        return False
    import torch  # type: ignore

    side = 512
    steps = max(1, min(settings.sdturbo_steps, 50))
    guidance = float(settings.sdturbo_guidance)
    kwargs = dict(
        prompt=ctx.prompt,
        num_inference_steps=steps,
        guidance_scale=guidance,
        height=side,
        width=side,
        generator=torch.Generator(device=settings.torch_device).manual_seed(seed),
    )
    if guidance > 1 and ctx.negative_prompt:
        kwargs["negative_prompt"] = ctx.negative_prompt
    ctx.image = pipe(**kwargs).images[0]
    return True


def _run_instantid(ctx: StageContext, seed: int, w: int, h: int, steps: int, guidance: float) -> bool:
    bundle = loader.get_model("instantid")
    ref = _ref_image(ctx)
    if bundle is None or ref is None:
        return False
    import numpy as np  # type: ignore
    import torch  # type: ignore
    from pipeline_stable_diffusion_xl_instantid import draw_kps  # type: ignore

    face_app, pipe = bundle["face_app"], bundle["pipe"]
    faces = face_app.get(np.array(ref)[:, :, ::-1])  # BGR
    if not faces:
        raise StageError("instantid", "no_face_detected", "No face found in reference")
    face = sorted(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))[-1]
    kps = draw_kps(ref, face.kps)
    ctx.image = pipe(
        prompt=ctx.prompt,
        negative_prompt=ctx.negative_prompt or None,
        image_embeds=torch.from_numpy(face.normed_embedding).unsqueeze(0),
        image=kps,
        controlnet_conditioning_scale=0.8,
        ip_adapter_scale=0.8,
        num_inference_steps=min(steps, 40),
        guidance_scale=guidance,
        height=h,
        width=w,
        generator=torch.Generator(device=settings.torch_device).manual_seed(seed),
    ).images[0]
    return True


def _run_flux_controlnet(ctx: StageContext, seed: int, w: int, h: int, steps: int, guidance: float) -> bool:
    pipe = loader.get_model("flux-controlnet")
    ref = _ref_image(ctx)
    if pipe is None or ref is None:
        return False
    import torch  # type: ignore
    from PIL import ImageFilter

    # Derive a control map (edges) from the reference at the target size.
    control = ref.resize((w, h)).filter(ImageFilter.FIND_EDGES).convert("RGB")
    ctx.image = pipe(
        prompt=ctx.prompt,
        control_image=control,
        controlnet_conditioning_scale=0.6,
        num_inference_steps=steps,
        guidance_scale=guidance,
        height=h,
        width=w,
        generator=torch.Generator(device=settings.torch_device).manual_seed(seed),
    ).images[0]
    return True


def _run_flux(ctx: StageContext, seed: int, w: int, h: int, steps: int, guidance: float) -> bool:
    pipe = loader.get_model("flux.1")
    if pipe is None:
        return False
    import torch  # type: ignore

    ctx.image = pipe(
        prompt=ctx.prompt,
        negative_prompt=ctx.negative_prompt or None,
        width=w,
        height=h,
        num_inference_steps=steps,
        guidance_scale=guidance,
        generator=torch.Generator(device=settings.torch_device).manual_seed(seed),
    ).images[0]
    return True


def run(ctx: StageContext) -> None:
    w, h, steps, guidance = _clamp_params(ctx.params)
    seed = _seed(ctx)
    ctx.seed = seed
    backend = settings.generation_backend.lower()

    try:
        # Local/light real backend.
        if backend == "sdturbo":
            if _run_sd(ctx, seed):
                return
            ctx.image = _deterministic_image(ctx.prompt, seed, w, h)
            return

        # Production GPU backends, in priority order.
        if "instantid" in ctx.stages and ctx.reference_images and _run_instantid(ctx, seed, w, h, steps, guidance):
            return
        if "controlnet" in ctx.stages and ctx.reference_images and _run_flux_controlnet(ctx, seed, w, h, steps, guidance):
            return
        if _run_flux(ctx, seed, w, h, steps, guidance):
            return
        # Nothing available -> deterministic stand-in (keeps the flow working).
        ctx.image = _deterministic_image(ctx.prompt, seed, w, h)
    except StageError:
        raise
    except Exception as exc:  # noqa: BLE001
        transient = any(s in str(exc).lower() for s in ("out of memory", "cuda", "oom"))
        raise StageError(name, "generation_failed", str(exc), transient=transient) from exc
