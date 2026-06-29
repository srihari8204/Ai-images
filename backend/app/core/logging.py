"""Structured JSON logging with correlation-id propagation.

A correlation id is carried in a ``contextvar`` so every log line emitted while
handling a request (or processing a job) can be tied back to the originating
API call — the same id is propagated across the queue into the worker.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar

import structlog

correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id", default=None)
job_id_ctx: ContextVar[str | None] = ContextVar("job_id", default=None)
user_id_ctx: ContextVar[str | None] = ContextVar("user_id", default=None)


def _inject_context(_logger, _method, event_dict: dict) -> dict:
    cid = correlation_id_ctx.get()
    if cid:
        event_dict.setdefault("correlation_id", cid)
    jid = job_id_ctx.get()
    if jid:
        event_dict.setdefault("job_id", jid)
    uid = user_id_ctx.get()
    if uid:
        event_dict.setdefault("user_id", uid)
    return event_dict


def configure_logging(*, json_logs: bool = True, level: str = "INFO") -> None:
    """Configure structlog + stdlib logging to emit a single JSON stream."""

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    # NB: no ``add_logger_name`` — it requires a stdlib logger, but we use
    # structlog's PrintLogger (which has no ``.name``) for the primary stream.
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        _inject_context,
        structlog.processors.add_log_level,
        timestamper,
        structlog.processors.StackInfoRenderer(),
    ]

    renderer = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(level)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging (uvicorn, sqlalchemy) through the same renderer.
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=renderer,
            foreign_pre_chain=shared_processors,
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for noisy in ("uvicorn.access", "botocore", "boto3", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
