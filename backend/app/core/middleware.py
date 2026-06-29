"""HTTP middleware: correlation ids, structured access logs, and metrics."""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core import metrics
from app.core.logging import correlation_id_ctx, get_logger

logger = get_logger("http")

CORRELATION_HEADER = "X-Correlation-ID"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        cid = request.headers.get(CORRELATION_HEADER) or str(uuid.uuid4())
        token = correlation_id_ctx.set(cid)
        request.state.correlation_id = cid
        try:
            response = await call_next(request)
        finally:
            correlation_id_ctx.reset(token)
        response.headers[CORRELATION_HEADER] = cid
        return response


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        # Use the route template (not the concrete path) to bound label cardinality.
        path_label = request.url.path
        try:
            response: Response = await call_next(request)
            status_code = response.status_code
        except Exception:
            metrics.http_errors_total.labels(path=path_label).inc()
            raise
        finally:
            elapsed = time.perf_counter() - start

        route = request.scope.get("route")
        if route is not None and getattr(route, "path", None):
            path_label = route.path

        metrics.http_requests_total.labels(
            method=request.method, path=path_label, status=str(status_code)
        ).inc()
        metrics.http_request_duration_seconds.labels(
            method=request.method, path=path_label
        ).observe(elapsed)
        if status_code >= 500:
            metrics.http_errors_total.labels(path=path_label).inc()

        logger.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=status_code,
            duration_ms=round(elapsed * 1000, 2),
            client=request.client.host if request.client else None,
        )
        return response
