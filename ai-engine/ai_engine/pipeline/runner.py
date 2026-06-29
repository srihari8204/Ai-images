"""Stage sequencing with per-stage retry and failure attribution (design D8)."""

from __future__ import annotations

import time

from ai_engine import metrics
from ai_engine.pipeline import (
    bg_removal,
    controlnet,
    flux,
    gfpgan,
    instantid,
    realesrgan,
)
from ai_engine.pipeline.base import StageContext, StageError
from app.core.logging import get_logger

logger = get_logger("worker.runner")

# Stage registry keyed by name; order is enforced by the caller's stage list.
STAGE_IMPLS = {
    flux.name: flux,
    instantid.name: instantid,
    controlnet.name: controlnet,
    gfpgan.name: gfpgan,
    realesrgan.name: realesrgan,
    bg_removal.name: bg_removal,
}

# Canonical execution order.
ORDER = ["generate", "instantid", "controlnet", "gfpgan", "realesrgan", "bg_removal"]

STAGE_MAX_RETRIES = 2
STAGE_RETRY_DELAY = 1.0


def ordered_stages(requested: list[str]) -> list[str]:
    wanted = set(requested) | {"generate"}
    return [s for s in ORDER if s in wanted]


def run_stage(stage_name: str, ctx: StageContext) -> None:
    impl = STAGE_IMPLS[stage_name]
    attempt = 0
    while True:
        start = time.perf_counter()
        try:
            impl.run(ctx)
            metrics.stage_duration_seconds.labels(stage=stage_name).observe(
                time.perf_counter() - start
            )
            return
        except StageError as err:
            metrics.stage_failures_total.labels(
                stage=stage_name, transient=str(err.transient).lower()
            ).inc()
            if err.transient and attempt < STAGE_MAX_RETRIES:
                attempt += 1
                logger.warning(
                    "stage_retry", stage=stage_name, attempt=attempt, code=err.code
                )
                time.sleep(STAGE_RETRY_DELAY * (2 ** (attempt - 1)))
                continue
            raise
        except Exception as exc:  # noqa: BLE001 - unexpected → attribute to stage
            metrics.stage_failures_total.labels(stage=stage_name, transient="false").inc()
            raise StageError(stage_name, "stage_crashed", str(exc)) from exc
