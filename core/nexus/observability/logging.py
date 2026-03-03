"""Structured logging for Nexus."""

from __future__ import annotations

import logging
import json
import sys
from datetime import datetime
from typing import Any
from contextvars import ContextVar

# Context variables for request-scoped data
_request_context: ContextVar[dict] = ContextVar("request_context", default={})


def set_request_context(**kwargs):
    """Set request context for logging."""
    ctx = _request_context.get().copy()
    ctx.update(kwargs)
    _request_context.set(ctx)


def get_request_context() -> dict:
    """Get current request context."""
    return _request_context.get()


def clear_request_context():
    """Clear request context."""
    _request_context.set({})


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add location info
        if record.pathname:
            log_data["location"] = {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName,
            }

        # Add exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add request context
        ctx = get_request_context()
        if ctx:
            log_data["context"] = ctx

        # Add extra fields
        if hasattr(record, "extra"):
            log_data.update(record.extra)

        # Check for extra attributes added via extra= parameter
        for key in ["request_id", "method", "path", "query", "client_ip",
                    "user_agent", "status_code", "duration_ms", "error",
                    "agent_id", "device_id", "job_id"]:
            if hasattr(record, key):
                log_data[key] = getattr(record, key)

        return json.dumps(log_data, default=str)


class ConsoleFormatter(logging.Formatter):
    """Human-readable console formatter."""

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        # Build message
        msg = f"{color}[{timestamp}] {record.levelname:8}{self.RESET} {record.name}: {record.getMessage()}"

        # Add context
        ctx = get_request_context()
        if ctx.get("request_id"):
            msg = f"{msg} [req:{ctx['request_id'][:8]}]"

        # Add extra fields
        extras = []
        for key in ["status_code", "duration_ms", "error"]:
            if hasattr(record, key):
                extras.append(f"{key}={getattr(record, key)}")
        if extras:
            msg = f"{msg} ({', '.join(extras)})"

        # Add exception
        if record.exc_info:
            msg = f"{msg}\n{self.formatException(record.exc_info)}"

        return msg


def setup_logging(
    level: str = "INFO",
    format: str = "json",  # json or console
    log_file: str | None = None,
):
    """Configure logging for Nexus."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Choose formatter
    if format == "json":
        formatter = JSONFormatter()
    else:
        formatter = ConsoleFormatter()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(JSONFormatter())  # Always JSON for files
        root_logger.addHandler(file_handler)

    # Set levels for noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)


class LoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that includes context."""

    def process(self, msg: str, kwargs: dict) -> tuple[str, dict]:
        # Merge context into extra
        extra = kwargs.get("extra", {})
        extra.update(get_request_context())
        kwargs["extra"] = extra
        return msg, kwargs


def get_context_logger(name: str) -> LoggerAdapter:
    """Get a logger that includes request context."""
    return LoggerAdapter(logging.getLogger(name), {})
