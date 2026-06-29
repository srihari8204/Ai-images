"""Queue producer/consumer abstraction over Redis (RQ).

The rest of the codebase depends only on this thin interface — ``enqueue_job``,
``cancel_job``, ``queue_depth`` — so the backing technology (RQ today, possibly
Kafka/SQS later) can change without touching the pipeline domain logic.

Priority tiers map to separate RQ queues drained highest-first by the worker.
"""

from __future__ import annotations

from enum import IntEnum
from functools import lru_cache
from typing import Any

import redis as sync_redis
from rq import Queue
from rq.job import Job
from rq.registry import StartedJobRegistry

from app.core.config import settings

WORKER_TASK_PATH = "ai_engine.worker.run_job"


class Priority(IntEnum):
    LOW = 0
    NORMAL = 1
    HIGH = 2


_QUEUE_BY_PRIORITY = {
    Priority.HIGH: f"{settings.queue_name}-high",
    Priority.NORMAL: settings.queue_name,
    Priority.LOW: f"{settings.queue_name}-low",
}

# Worker drains queues in this order (highest priority first).
QUEUE_ORDER = [
    _QUEUE_BY_PRIORITY[Priority.HIGH],
    _QUEUE_BY_PRIORITY[Priority.NORMAL],
    _QUEUE_BY_PRIORITY[Priority.LOW],
]


@lru_cache
def _connection() -> sync_redis.Redis:
    return sync_redis.from_url(settings.redis_url)


def _queue(priority: Priority) -> Queue:
    return Queue(_QUEUE_BY_PRIORITY[priority], connection=_connection())


def enqueue_job(
    job_id: str,
    payload: dict[str, Any],
    *,
    priority: Priority = Priority.NORMAL,
    delay_seconds: int = 0,
    correlation_id: str | None = None,
) -> str:
    """Enqueue a generation job. ``job_id`` is reused as the RQ job id so the
    same database job maps 1:1 to a queue entry (idempotent re-enqueue)."""

    q = _queue(priority)
    meta = {"correlation_id": correlation_id, "db_job_id": job_id}
    kwargs: dict[str, Any] = dict(
        args=(job_id, payload),
        job_id=job_id,
        result_ttl=86400,
        failure_ttl=604800,
        job_timeout=1800,
        meta=meta,
        retry=None,
    )
    if delay_seconds > 0:
        from datetime import timedelta

        q.enqueue_in(timedelta(seconds=delay_seconds), WORKER_TASK_PATH, **kwargs)
    else:
        q.enqueue(WORKER_TASK_PATH, **kwargs)
    return job_id


def cancel_job(job_id: str) -> bool:
    """Best-effort removal of a queued job and a cancel signal for a running one."""

    conn = _connection()
    try:
        job = Job.fetch(job_id, connection=conn)
    except Exception:  # noqa: BLE001
        return False
    try:
        job.cancel()  # marks running job cancelled; worker checks the flag
    except Exception:  # noqa: BLE001
        pass
    # Publish an explicit cancel flag the worker polls between stages.
    conn.set(f"job:cancel:{job_id}", "1", ex=3600)
    return True


def is_cancel_requested(job_id: str) -> bool:
    return bool(_connection().get(f"job:cancel:{job_id}"))


def queue_depth() -> dict[str, int]:
    conn = _connection()
    depths = {name: Queue(name, connection=conn).count for name in QUEUE_ORDER}
    running = sum(
        StartedJobRegistry(name, connection=conn).count for name in QUEUE_ORDER
    )
    depths["__running__"] = running
    depths["__total__"] = sum(v for k, v in depths.items() if not k.startswith("__"))
    return depths


def estimate_wait_seconds(avg_job_seconds: int = 20, worker_count: int = 1) -> int:
    depth = queue_depth()["__total__"]
    return int((depth / max(worker_count, 1)) * avg_job_seconds)
