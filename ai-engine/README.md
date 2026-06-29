# AI Engine (GPU Worker)

Separate deployable that consumes the Redis generation queue and runs the staged
pipeline. It shares the backend `app.*` package (DB models, credit finalization,
storage) so credit/idempotency invariants stay consistent across processes.

## Pipeline stages (composable, individually retryable)

`generate` → `instantid` → `controlnet` → `gfpgan` → `realesrgan` → `bg_removal`

- **FLUX.1** base generation (bounded resolution/steps/guidance/seed).
- **InstantID** face consistency (gated on consent + a valid reference).
- **ControlNet** pose/edge/depth conditioning.
- **GFPGAN** face restoration, **RealESRGAN** upscaling, **bg_removal** (transparent PNG).

Each stage has its own retry/timeout; transient failures retry with backoff and a
whole-job retry re-enqueues the same idempotency key. Cancellation is honoured
between stages. Progress is published to Redis (`job:progress:{id}`) for the SSE
endpoint and persisted on the job row for pollers.

## Graceful degradation (dev/CPU)

The heavy GPU stack (torch/diffusers/insightface/…) is **optional**. When it is
absent, each stage falls back to a deterministic CPU stand-in with the identical
input/output contract, so the full job lifecycle (queue → stages → outputs →
credit debit) runs end-to-end without a GPU. Enable real models by uncommenting
the GPU deps in `requirements.txt` and mounting weights.

## Run

```bash
# from the worker image (PYTHONPATH includes backend + ai-engine):
python -m ai_engine.worker
```

The worker drains queues highest-priority first (`generation-high` → `generation`
→ `generation-low`), reports GPU/VRAM + per-stage metrics on `:9100`, and warms
the model pool on start.

## Idempotency & money safety

`finalize.claim_job` performs a check-before-charge: a duplicate delivery of a
finished job is a no-op. Success converts the hold to a debit exactly once;
failure/cancel refunds the hold exactly once — all via row-locked ledger writes.
