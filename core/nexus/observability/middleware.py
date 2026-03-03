"""Observability middleware for FastAPI."""

from __future__ import annotations

import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from nexus.observability.metrics import (
    http_requests_total,
    http_request_duration_seconds,
    http_requests_in_progress,
)
from nexus.observability.logging import get_logger, set_request_context


logger = get_logger(__name__)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to collect HTTP metrics."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate request ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # Get endpoint path (use route path if available, otherwise use URL path)
        if request.scope.get("route"):
            endpoint = request.scope["route"].path
        else:
            endpoint = request.url.path

        method = request.method

        # Track in-progress requests
        http_requests_in_progress.labels(method=method, endpoint=endpoint).inc()

        start_time = time.time()

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            status_code = 500
            raise
        finally:
            # Record metrics
            duration = time.time() - start_time

            http_requests_total.labels(
                method=method,
                endpoint=endpoint,
                status_code=str(status_code),
            ).inc()

            http_request_duration_seconds.labels(
                method=method,
                endpoint=endpoint,
            ).observe(duration)

            http_requests_in_progress.labels(method=method, endpoint=endpoint).dec()

        # Add headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration:.3f}s"

        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for structured request logging."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # Set request context for logging
        set_request_context(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        start_time = time.time()

        # Log request
        logger.info(
            "Request started",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "query": str(request.query_params),
                "client_ip": request.client.host if request.client else None,
                "user_agent": request.headers.get("User-Agent"),
            },
        )

        try:
            response = await call_next(request)
            status_code = response.status_code
            error = None
        except Exception as e:
            status_code = 500
            error = str(e)
            logger.exception(
                "Request failed with exception",
                extra={
                    "request_id": request_id,
                    "error": error,
                },
            )
            raise

        duration = time.time() - start_time

        # Log response
        log_level = "info" if status_code < 400 else "warning" if status_code < 500 else "error"
        getattr(logger, log_level)(
            "Request completed",
            extra={
                "request_id": request_id,
                "status_code": status_code,
                "duration_ms": int(duration * 1000),
            },
        )

        return response


class TracingMiddleware(BaseHTTPMiddleware):
    """Middleware for distributed tracing headers."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Extract or generate trace context
        trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
        span_id = request.headers.get("X-Span-ID", str(uuid.uuid4())[:16])
        parent_span_id = request.headers.get("X-Parent-Span-ID")

        # Store in request state
        request.state.trace_id = trace_id
        request.state.span_id = span_id
        request.state.parent_span_id = parent_span_id

        response = await call_next(request)

        # Add trace headers to response
        response.headers["X-Trace-ID"] = trace_id
        response.headers["X-Span-ID"] = span_id

        return response
