"""Health, readiness, and metrics endpoints.

- ``/healthz`` — liveness: the process is up. Never touches dependencies.
- ``/readyz``  — readiness: Postgres, Redis, and MinIO are all reachable. Flips
  to 503 on any dependency outage so orchestration stops routing traffic.
- ``/metrics`` — Prometheus exposition (intended for the internal network only).
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from app.core import metrics
from app.core.redis import redis_health_check
from app.db.session import SessionLocal
from app.queue.producer import queue_depth
from app.storage import object_store

router = APIRouter(tags=["monitoring"])


@router.get("/healthz", summary="Liveness probe")
async def healthz() -> dict:
    return {"status": "ok"}


async def _check_db() -> bool:
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        return False


@router.get("/readyz", summary="Readiness probe")
async def readyz(response: Response) -> dict:
    checks = {
        "postgres": await _check_db(),
        "redis": await redis_health_check(),
        "minio": object_store.health_check(),
    }
    ready = all(checks.values())
    if not ready:
        response.status_code = 503
    return {"ready": ready, "checks": checks}


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics() -> Response:
    # Refresh queue-depth gauges at scrape time.
    try:
        for name, depth in queue_depth().items():
            if not name.startswith("__"):
                metrics.queue_depth_gauge.labels(queue=name).set(depth)
    except Exception:  # noqa: BLE001
        pass
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
