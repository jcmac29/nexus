"""Observability module - Metrics, logging, and health checks for Nexus."""

from nexus.observability.metrics import (
    get_metrics,
    set_app_info,
    http_requests_total,
    http_request_duration_seconds,
)
from nexus.observability.logging import (
    setup_logging,
    get_logger,
    get_context_logger,
    set_request_context,
)
from nexus.observability.middleware import (
    MetricsMiddleware,
    LoggingMiddleware,
    TracingMiddleware,
)
from nexus.observability.health import router as health_router

__all__ = [
    "get_metrics",
    "set_app_info",
    "setup_logging",
    "get_logger",
    "get_context_logger",
    "set_request_context",
    "MetricsMiddleware",
    "LoggingMiddleware",
    "TracingMiddleware",
    "health_router",
]
