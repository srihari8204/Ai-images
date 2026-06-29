# GPU Deployment — switch from local CPU to real FLUX

The codebase runs the **same** pipeline locally (CPU stand-ins / tiny-SD) and in
production (real models on GPU). Flipping to production is **config + weights**,
no code changes.

## 1. Build the GPU worker image

```bash
docker build -f docker/Dockerfile.worker.gpu -t <registry>/aimirror-worker:gpu .
```

The image installs CUDA PyTorch, diffusers, InstantID (insightface), ControlNet,
GFPGAN, RealESRGAN, and rembg. Weights are **not** baked in — they're mounted.

## 2. Environment (worker)

| Var | Value | Purpose |
|-----|-------|---------|
| `GENERATION_BACKEND` | `flux` | Use FLUX.1 (not the CPU stand-in) |
| `TORCH_DEVICE` | `cuda` | Run on GPU |
| `HF_HOME` | `/models/hf` | Persistent HuggingFace cache (mount a volume) |
| `INSIGHTFACE_ROOT` | `/models/insightface` | InstantID face models |
| `ENABLE_NSFW_MODEL` | `true` | Real NSFW screening (API + worker) |
| `FLUX_MODEL` | `black-forest-labs/FLUX.1-dev` | Base model (or your fine-tune) |
| `FLUX_CONTROLNET_MODEL` | `Shakker-Labs/FLUX.1-dev-ControlNet-Union-Pro` | Structure control |
| `INSTANTID_BASE_MODEL` | `stabilityai/stable-diffusion-xl-base-1.0` | InstantID base (SDXL) |
| `GFPGAN_MODEL_PATH` / `REALESRGAN_MODEL_PATH` | (defaults point at the official release URLs) | restoration/upscale |

> FLUX.1-dev is gated on HuggingFace — set `HF_TOKEN` in the worker env and accept
> the license once, or mirror the weights into your own storage.

## 3. Weights to provide (mounted at `/models`)

Mount a large, persistent volume at `/models`. On first run the worker downloads:

- FLUX.1-dev (~24 GB) → `HF_HOME`
- FLUX ControlNet Union (~3 GB)
- SDXL base + InstantID ControlNet + ip-adapter (~7 GB) — InstantID
- InsightFace `antelopev2` → `INSIGHTFACE_ROOT`
- GFPGAN v1.4 + RealESRGAN x4plus (~few hundred MB)
- rembg `u2net` (~170 MB)

Pre-bake the volume (recommended) so pods start fast and don't hammer HF:

```bash
docker run --rm -v aimirror-models:/models -e HF_HOME=/models/hf \
  -e HF_TOKEN=$HF_TOKEN <registry>/aimirror-worker:gpu \
  python -c "from ai_engine.models import loader; loader.warm(['flux.1','flux-controlnet','instantid','gfpgan','realesrgan','rembg'])"
```

## 4. GPU sizing

| Model | Min VRAM |
|-------|----------|
| FLUX.1-dev (bf16) | ~24 GB (A10G/A100/L40S/4090) |
| + ControlNet | ~28 GB |
| InstantID (SDXL) | ~12–16 GB |

For a single 24 GB card, run FLUX **or** InstantID per worker pool, or use an
A100 40/80 GB. Scale worker replicas on queue depth (KEDA — see `deploy/`).

## 5. Kubernetes

Use `docker/Dockerfile.worker.gpu` as the worker image in `deploy/worker/deployment.yaml`,
uncomment the GPU resource limit and node selector:

```yaml
resources:
  limits:
    nvidia.com/gpu: 1
nodeSelector:
  cloud.google.com/gke-accelerator: nvidia-l4   # or your GPU label
volumeMounts:
  - { name: models, mountPath: /models }
volumes:
  - name: models
    persistentVolumeClaim: { claimName: aimirror-models }
```

KEDA already autoscales workers on Redis queue depth (`deploy/worker/keda-scaledobject.yaml`).

## 6. Verify

```bash
# in the worker pod
python -c "from ai_engine.models import loader; print('flux', loader.available('flux.1'))"
# submit a job via the API and confirm GPU utilisation:
#   worker_gpu_utilization_percent rises, job completes in seconds
```

The worker uses `SimpleWorker` (no fork) — required for GPU/ML so PyTorch doesn't
deadlock after `fork()`. Keep that.

## 7. Rollback

Workers are stateless and versioned — `kubectl rollout undo deploy/worker`. The
queue + idempotency keys make in-flight jobs safe across restarts.
