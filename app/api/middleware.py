"""
app/api/middleware.py
──────────────────────
Request lifecycle middleware: logging, correlation IDs, timing.

Design: Middleware runs for EVERY request. Keep it fast.
Correlation IDs allow tracing a single request across distributed logs.
"""
from __future__ import annotations

import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

from app.core.logging import get_logger

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Attaches a correlation ID to each request and logs request/response metadata.
    The X-Correlation-ID header propagates to response for client-side tracing.
    """

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        start_time = time.perf_counter()

        # Bind correlation ID to structlog context for this request
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else "unknown",
        )

        logger.info("request_started")

        try:
            response: Response = await call_next(request)
        except Exception:
            logger.exception("request_failed")
            raise

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        logger.info(
            "request_completed",
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"

        return response
