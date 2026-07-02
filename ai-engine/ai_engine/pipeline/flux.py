"""Base image generation stage.

Selects the generation pipeline based on the configured backend and the requested
stages:

- ``GENERATION_BACKEND=flux`` (production GPU):
    * InstantID requested + reference present  -> InstantID (SDXL) identity gen
    * ControlNet requested + reference present  -> FLUX + ControlNet structure gen
    * otherwise                                 -> FLUX base
- ``GENERATION_BACKEND=sdturbo`` (local CPU test): real SD-Turbo / small-SD
- if no real model is available the job fails loudly (never a placeholder)

Resolution, seed, guidance, and steps are honoured within configured bounds.
InstantID/ControlNet conditioning happens HERE (at generation), so their dedicated
stages become light validators downstream.
"""

from __future__ import annotations

import hashlib
import io

from PIL import Image as PILImage

from ai_engine.models import loader
from ai_engine.pipeline.base import StageContext, StageError
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

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


def _frame_reference(ref, faces, w: int, h: int):
    """Crop a head-and-shoulders region centered on the largest face, with
    headroom, then resize to (w, h). Prevents the output from being cropped at
    the forehead/chin. Falls back to a plain cover-crop if no face is found."""
    from PIL import Image as _PILImage
    from PIL import ImageOps as _ImageOps

    if not faces:
        return _ImageOps.fit(ref, (w, h))
    f = sorted(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))[-1]
    x1, y1, x2, y2 = f.bbox
    fw, fh = (x2 - x1), (y2 - y1)
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    side = max(fw, fh) * 2.3  # room for full head + shoulders + margin
    left = int(round(cx - side / 2.0))
    top = int(round(cy - side * 0.42))  # extra room above for hair/headroom
    side = int(round(side))
    # PIL.crop pads out-of-bounds regions with black; paste onto a canvas first
    # so we always get a clean square without hard black bars from the crop.
    canvas = _PILImage.new("RGB", (side, side), (20, 20, 20))
    sx, sy = max(0, -left), max(0, -top)
    region = ref.crop((max(0, left), max(0, top),
                       min(ref.width, left + side), min(ref.height, top + side)))
    canvas.paste(region, (sx, sy))
    return canvas.resize((w, h))


def _run_instantid(ctx: StageContext, seed: int, w: int, h: int, steps: int, guidance: float) -> bool:
    bundle = loader.get_model("instantid")
    ref = _ref_image(ctx)
    if bundle is None or ref is None:
        return False
    import numpy as np  # type: ignore
    import torch  # type: ignore
    from pipeline_stable_diffusion_xl_instantid import draw_kps  # type: ignore

    face_app, pipe = bundle["face_app"], bundle["pipe"]

    # Face-aware framing: detect the face on the original reference, crop a proper
    # head-and-shoulders region (with headroom) sized to the output, then use that
    # as the keypoint control reference so the result is a well-framed portrait.
    faces0 = face_app.get(np.array(ref)[:, :, ::-1])  # BGR
    ref_fit = _frame_reference(ref, faces0, w, h)
    faces = face_app.get(np.array(ref_fit)[:, :, ::-1])
    if not faces:
        ref_fit = ref
        faces = face_app.get(np.array(ref_fit)[:, :, ::-1])
    if not faces:
        raise StageError("instantid", "no_face_detected", "No face found in reference")
    face = sorted(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))[-1]
    kps = draw_kps(ref_fit, face.kps)

    # Anchor the subject to the DETECTED gender/age so identity is preserved even
    # with a minimal prompt, and force clean head-and-shoulders framing so the
    # result is a proper portrait (not a cropped macro of the nose).
    # Only anchor gender (age/ethnicity come from the face embedding — forcing a
    # detected age biased results older). Keep the prompt light so the identity
    # embedding, not the base model's stock-photo bias, drives the face.
    sex = getattr(face, "sex", None)
    subject = "man" if sex == "M" else "woman" if sex == "F" else "person"
    style_prompt = ctx.prompt or "portrait"
    prompt = (
        f"a {subject}, {style_prompt}, head and shoulders portrait, centered composition, "
        "looking at camera, natural pose, high quality, sharp focus"
    )
    negative = ctx.negative_prompt or (
        "extreme close-up, cropped face, out of frame, zoomed in, macro, "
        "lowres, worst quality, low quality, blurry, deformed, disfigured, "
        "extra limbs, extra fingers, mutated hands, bad anatomy, wrong gender, "
        "watermark, text"
    )
    # SDXL/InstantID follows prompts poorly below ~5; the pipeline's global 3.5
    # default (FLUX-oriented) causes drift, so enforce a sensible minimum.
    cfg = guidance if guidance and guidance >= 4.0 else 5.0

    ctx.image = pipe(
        prompt=prompt,
        negative_prompt=negative,
        image_embeds=torch.from_numpy(face.normed_embedding).unsqueeze(0),
        image=kps,
        # Official InstantID demo balance (with the YamerMIX base): keypoints for
        # face geometry (0.8) and IP-adapter identity (0.8). This pairing tracks
        # the input face faithfully; pushing the adapter to 1.0 distorts.
        controlnet_conditioning_scale=0.8,
        ip_adapter_scale=0.8,
        num_inference_steps=min(max(steps, 30), 40),
        guidance_scale=cfg,
        height=h,
        width=w,
        generator=torch.Generator(device=settings.torch_device).manual_seed(seed),
    ).images[0]

    # Face swap: transplant the user's ACTUAL face onto the generated portrait.
    # InstantID only approximates the face; swapping the real face in gives
    # high-fidelity likeness ("that's actually me"). Reuses the source face
    # already detected from the reference. Best-effort: if it fails, keep the
    # InstantID result.
    swapper = loader.get_model("inswapper")
    if swapper is None:
        logger.warning("face_swap_unavailable", job_id=ctx.job_id)
    else:
        try:
            gen_bgr = np.array(ctx.image)[:, :, ::-1].copy()
            targets = face_app.get(gen_bgr)
            if not targets:
                logger.warning("face_swap_no_target", job_id=ctx.job_id)
            else:
                tgt = sorted(
                    targets, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])
                )[-1]
                swapped = swapper.get(gen_bgr, tgt, face, paste_back=True)
                ctx.image = PILImage.fromarray(swapped[:, :, ::-1])
                logger.info("face_swap_applied", job_id=ctx.job_id)
        except Exception as exc:  # noqa: BLE001 - non-fatal; keep the InstantID output
            logger.warning("face_swap_failed", job_id=ctx.job_id, error=repr(exc))
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
            raise StageError(
                name,
                "model_unavailable",
                "SD-Turbo backend is configured but the model could not be loaded.",
            )

        # Production GPU backends, in priority order.
        if "instantid" in ctx.stages and ctx.reference_images and _run_instantid(ctx, seed, w, h, steps, guidance):
            return
        if "controlnet" in ctx.stages and ctx.reference_images and _run_flux_controlnet(ctx, seed, w, h, steps, guidance):
            return
        if _run_flux(ctx, seed, w, h, steps, guidance):
            return
        # No real model produced an image -> fail loudly. We never emit a
        # placeholder: a failed job is refunded, a fake gradient would not be.
        raise StageError(
            name,
            "model_unavailable",
            "No generation model was available. For portraits, upload a reference "
            "image and enable InstantID; text-only jobs need a configured "
            "text-to-image model.",
        )
    except StageError:
        raise
    except Exception as exc:  # noqa: BLE001
        transient = any(s in str(exc).lower() for s in ("out of memory", "cuda", "oom"))
        raise StageError(name, "generation_failed", str(exc), transient=transient) from exc
