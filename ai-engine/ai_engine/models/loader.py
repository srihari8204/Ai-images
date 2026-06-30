"""Model loading and warm pool.

Models are loaded lazily on first use and cached process-wide (warm pool) so the
weights stay resident across jobs. Every loader is wrapped so that a missing
dependency, missing weights, or absent GPU returns ``None`` — the pipeline then
falls back to a deterministic CPU stand-in with the identical I/O contract. This
lets the exact same code run locally (CPU/no models) and in production (GPU with
all models mounted) without branching elsewhere.

Production deployment: see docs/gpu-deployment.md for the weights to mount and the
env to set (``GENERATION_BACKEND=flux``, ``TORCH_DEVICE=cuda``).
"""

from __future__ import annotations

import threading
import time
from typing import Any

from ai_engine import metrics
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("worker.models")

_pool: dict[str, Any] = {}
_lock = threading.Lock()


# --------------------------------------------------------------------------- #
# Individual model loaders (return None on any failure)
# --------------------------------------------------------------------------- #
def _load_flux() -> Any | None:
    import torch  # type: ignore
    from diffusers import FluxPipeline  # type: ignore

    dtype = torch.bfloat16 if settings.torch_device == "cuda" else torch.float32
    pipe = FluxPipeline.from_pretrained(settings.flux_model, torch_dtype=dtype)
    pipe = pipe.to(settings.torch_device)
    try:
        pipe.enable_attention_slicing()
    except Exception:  # noqa: BLE001
        pass
    return pipe


def _load_flux_controlnet() -> Any | None:
    import torch  # type: ignore
    from diffusers import FluxControlNetModel, FluxControlNetPipeline  # type: ignore

    dtype = torch.bfloat16 if settings.torch_device == "cuda" else torch.float32
    controlnet = FluxControlNetModel.from_pretrained(
        settings.flux_controlnet_model, torch_dtype=dtype
    )
    pipe = FluxControlNetPipeline.from_pretrained(
        settings.flux_model, controlnet=controlnet, torch_dtype=dtype
    )
    pipe = pipe.to(settings.torch_device)
    return pipe


def _load_sd_turbo() -> Any | None:
    """Real diffusion on CPU/GPU for local testing or a light backend."""

    import torch  # type: ignore
    from diffusers import AutoPipelineForText2Image  # type: ignore

    dtype = torch.float16 if settings.torch_device == "cuda" else torch.float32
    pipe = AutoPipelineForText2Image.from_pretrained(
        settings.sdturbo_model, torch_dtype=dtype
    )
    pipe = pipe.to(settings.torch_device)
    pipe.set_progress_bar_config(disable=True)
    try:
        pipe.safety_checker = None  # platform does its own moderation
    except Exception:  # noqa: BLE001
        pass
    return pipe


def _load_instantid() -> Any | None:
    """InstantID (SDXL) face-consistency pipeline.

    Requires the InstantID custom pipeline module on PYTHONPATH plus insightface.
    The deployment guide installs these and downloads the weights; here we wire
    them together. Returns a dict bundling the face analyser and the pipeline.
    """

    import torch  # type: ignore
    from diffusers.models import ControlNetModel  # type: ignore
    from huggingface_hub import hf_hub_download  # type: ignore
    from insightface.app import FaceAnalysis  # type: ignore

    # The InstantID pipeline class ships in the InstantID repo (added to PYTHONPATH).
    from pipeline_stable_diffusion_xl_instantid import (  # type: ignore
        StableDiffusionXLInstantIDPipeline,
        draw_kps,  # noqa: F401
    )

    dtype = torch.float16 if settings.torch_device == "cuda" else torch.float32
    face_app = FaceAnalysis(
        name="antelopev2",
        root=settings.insightface_root,
        providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
    )
    face_app.prepare(ctx_id=0, det_size=(640, 640))

    controlnet_path = hf_hub_download(settings.instantid_repo, "ControlNetModel/diffusion_pytorch_model.safetensors")  # noqa: E501
    ip_adapter_path = hf_hub_download(settings.instantid_repo, "ip-adapter.bin")
    controlnet = ControlNetModel.from_pretrained(
        settings.instantid_repo, subfolder="ControlNetModel", torch_dtype=dtype
    )
    pipe = StableDiffusionXLInstantIDPipeline.from_pretrained(
        settings.instantid_base_model, controlnet=controlnet, torch_dtype=dtype
    )
    pipe = pipe.to(settings.torch_device)
    pipe.load_ip_adapter_instantid(ip_adapter_path)
    return {"face_app": face_app, "pipe": pipe}


def _load_gfpgan() -> Any | None:
    from gfpgan import GFPGANer  # type: ignore

    return GFPGANer(
        model_path=settings.gfpgan_model_path,
        upscale=1,
        arch="clean",
        channel_multiplier=2,
        bg_upsampler=None,
    )


def _load_realesrgan() -> Any | None:
    from basicsr.archs.rrdbnet_arch import RRDBNet  # type: ignore
    from realesrgan import RealESRGANer  # type: ignore

    model = RRDBNet(
        num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4
    )
    return RealESRGANer(
        scale=4,
        model_path=settings.realesrgan_model_path,
        model=model,
        tile=512,
        tile_pad=10,
        pre_pad=0,
        half=(settings.torch_device == "cuda"),
        device=settings.torch_device,
    )


def _load_rembg() -> Any | None:
    from rembg import new_session  # type: ignore

    return new_session("u2net")


_LOADERS = {
    "flux.1": _load_flux,
    "flux-controlnet": _load_flux_controlnet,
    "sd-turbo": _load_sd_turbo,
    "instantid": _load_instantid,
    "gfpgan": _load_gfpgan,
    "realesrgan": _load_realesrgan,
    "rembg": _load_rembg,
}


def _load(model_key: str) -> Any | None:
    loader = _LOADERS.get(model_key)
    if loader is None:
        return None
    start = time.perf_counter()
    try:
        return loader()
    except Exception as exc:  # noqa: BLE001 - missing deps/weights/GPU in some envs
        logger.warning("model_unavailable", model=model_key, error=str(exc))
        return None
    finally:
        metrics.model_load_seconds.labels(model=model_key).observe(
            time.perf_counter() - start
        )


def get_model(model_key: str) -> Any | None:
    if model_key in _pool:
        return _pool[model_key]
    with _lock:
        if model_key not in _pool:
            logger.info("model_loading", model=model_key)
            _pool[model_key] = _load(model_key)
    return _pool[model_key]


def warm(model_keys: list[str]) -> None:
    for key in model_keys:
        get_model(key)


def available(model_key: str) -> bool:
    return get_model(model_key) is not None
