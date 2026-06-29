"""GPU worker entrypoint and the RQ task ``run_job``.

The worker consumes jobs from the Redis queue (highest priority first), executes
the staged pipeline, and finalizes credits idempotently:

- check-before-charge via ``finalize.claim_job`` so duplicate deliveries are safe
- per-stage retry (transient) handled in the runner; whole-job retry-with-backoff
  re-enqueues the same idempotency key up to ``JOB_MAX_RETRIES``
- cancellation is honoured between stages
- graceful no-capacity handling re-queues the job with a short delay rather than
  dropping it, surfacing queue depth / wait via the API
"""

from __future__ import annotations

import os
import time

from ai_engine import gpu, metrics
from ai_engine.models import loader
from ai_engine.pipeline import runner
from ai_engine.pipeline.base import StageContext, StageError
from app.core.config import settings
from app.core.ids import uuid7
from app.core.logging import configure_logging, get_logger, job_id_ctx
from app.db.base import import_all_models
from app.db.sync_session import session_scope

# Register every ORM model at import time so the worker process can resolve all
# cross-table foreign keys (e.g. jobs.user_id -> users) when querying. RQ imports
# this module to run jobs, so this runs in every worker.
import_all_models()
from app.modules.pipeline import finalize
from app.storage import object_store

logger = get_logger("worker")


def _load_reference_images(reference_image_ids: list[str]) -> list[bytes]:
    from app.modules.uploads.models import Image

    out: list[bytes] = []
    if not reference_image_ids:
        return out
    with session_scope() as db:
        import uuid as _uuid

        for rid in reference_image_ids:
            img = db.get(Image, _uuid.UUID(rid))
            if img is not None:
                out.append(object_store.get_object(img.bucket, img.object_key))
    return out


def _requeue_no_capacity(job_id: str, payload: dict) -> None:
    from app.queue.producer import enqueue_job

    enqueue_job(job_id, payload, delay_seconds=15)
    logger.info("job_requeued_no_capacity", job_id=job_id)


def run_job(job_id: str, payload: dict | None = None) -> dict:
    """Entry called by RQ for each queued job."""

    payload = payload or {}
    no_charge = bool(payload.get("no_charge"))
    job_id_ctx.set(job_id)
    metrics.inflight_jobs.inc()
    try:
        # Graceful no-capacity handling: keep the job queued instead of failing.
        if not gpu.has_capacity():
            _requeue_no_capacity(job_id, payload)
            return {"status": "requeued_no_capacity"}

        with session_scope() as db:
            job = finalize.claim_job(db, job_id)
            if job is None:
                logger.info("job_skipped_idempotent", job_id=job_id)
                return {"status": "skipped"}
            stages = runner.ordered_stages(list(job.stages or ["generate"]))
            ctx = StageContext(
                job_id=str(job.id),
                user_id=str(job.user_id),
                prompt=job.prompt,
                negative_prompt=job.negative_prompt or "",
                seed=job.seed,
                params=dict(job.params or {}),
                reference_images=[],
                stages=stages,
            )
            ref_ids = list(job.reference_image_ids or [])
            attempts = job.attempts
            idem_key = job.idempotency_key

        # Load references outside the claim transaction (network I/O).
        ctx.reference_images = _load_reference_images(ref_ids)

        # Execute stages, persisting progress between each.
        total = len(stages)
        for index, stage_name in enumerate(stages):
            if finalize.is_cancel_requested(job_id):
                with session_scope() as db:
                    job = _reload(db, job_id)
                    finalize.mark_cancelled(db, job, no_charge=no_charge)
                metrics.jobs_processed_total.labels(status="cancelled").inc()
                return {"status": "cancelled"}
            try:
                runner.run_stage(stage_name, ctx)
            except StageError as err:
                return _handle_failure(job_id, payload, err, attempts, idem_key, no_charge)
            progress = int(((index + 1) / total) * 95)
            with session_scope() as db:
                job = _reload(db, job_id)
                finalize.set_progress(db, job, progress, stage_name)

        # Persist outputs + finalize debit.
        with session_scope() as db:
            job = _reload(db, job_id)
            _persist_outputs(db, job, ctx)
            finalize.finalize_success(db, job, no_charge=no_charge)
        metrics.jobs_processed_total.labels(status="completed").inc()
        logger.info("job_completed", job_id=job_id)
        return {"status": "completed"}
    finally:
        metrics.inflight_jobs.dec()
        job_id_ctx.set(None)


def _reload(db, job_id: str):
    import uuid as _uuid

    from app.modules.pipeline.models import Job

    return db.get(Job, _uuid.UUID(job_id))


def _persist_outputs(db, job, ctx: StageContext) -> None:
    primary_bytes = ctx.image_bytes("PNG")
    finalize.record_output(
        db,
        job,
        data=primary_bytes,
        mime="image/png",
        width=ctx.image.width,
        height=ctx.image.height,
        stage="final",
        is_primary=True,
        object_key=f"{job.user_id}/{job.id}/primary.png",
    )
    # Auxiliary outputs (e.g. transparent background).
    import io

    for label, image in ctx.extra_outputs.items():
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        finalize.record_output(
            db,
            job,
            data=buf.getvalue(),
            mime="image/png",
            width=image.width,
            height=image.height,
            stage=label,
            is_primary=False,
            object_key=f"{job.user_id}/{job.id}/{label}.png",
        )


def _handle_failure(job_id, payload, err: StageError, attempts, idem_key, no_charge) -> dict:
    """Retry transient failures with backoff; otherwise fail + refund."""

    from app.queue.producer import enqueue_job

    if err.transient and attempts < settings.job_max_retries:
        delay = settings.job_retry_base_delay_seconds * (2 ** attempts)
        with session_scope() as db:
            job = _reload(db, job_id)
            # Reset to queued; preserve idempotency key so credits aren't re-held.
            from app.modules.pipeline.models import JobStatus

            job.status = JobStatus.QUEUED
            finalize.publish_progress(job_id, "queued", job.progress, err.stage)
        enqueue_job(job_id, payload, delay_seconds=delay)
        logger.warning("job_retry_scheduled", job_id=job_id, stage=err.stage, delay=delay)
        metrics.jobs_processed_total.labels(status="retried").inc()
        return {"status": "retry_scheduled", "stage": err.stage}

    with session_scope() as db:
        job = _reload(db, job_id)
        finalize.finalize_failure(
            db,
            job,
            stage=err.stage,
            code=err.code,
            message=err.message,
            no_charge=no_charge,
        )
    metrics.jobs_processed_total.labels(status="failed").inc()
    logger.error("job_failed", job_id=job_id, stage=err.stage, code=err.code)
    return {"status": "failed", "stage": err.stage, "code": err.code}


def main() -> None:
    """Run the RQ worker, draining queues highest-priority first."""

    import redis as sync_redis
    from rq import Queue, SimpleWorker

    configure_logging(json_logs=settings.is_prod, level="INFO")
    metrics.start_metrics_server(int(os.getenv("WORKER_METRICS_PORT", "9100")))

    # Warm the model pool so the first job isn't penalised by load time.
    backend = settings.generation_backend.lower()
    warm_key = {"sdturbo": "sd-turbo", "flux": "flux.1", "auto": "flux.1"}.get(backend)
    if warm_key:
        logger.info("warming_model", backend=backend, model=warm_key)
        loader.warm([warm_key])

    conn = sync_redis.from_url(settings.redis_url)
    from app.queue.producer import QUEUE_ORDER

    queues = [Queue(name, connection=conn) for name in QUEUE_ORDER]
    # SimpleWorker runs jobs in-process (no os.fork). Forking after PyTorch/OpenMP
    # is initialised deadlocks GPU/ML inference, so ML workers must not fork; this
    # also keeps the warm model resident across jobs.
    worker = SimpleWorker(queues, connection=conn)
    logger.info("worker_started", queues=QUEUE_ORDER, mode="simple")
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
