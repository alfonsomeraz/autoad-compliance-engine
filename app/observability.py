"""Structured logging (structlog).

Every compliance run emits a structured, machine-parseable audit event carrying
its run ID — the traceability story the spec calls for. A per-request
correlation ID is bound via contextvars so all logs within a request share it.
JSON in non-dev environments; human-readable console output in development.
"""

from __future__ import annotations

import logging

import structlog

from app.config import get_settings

_configured = False


def configure_logging() -> None:
    """Configure structlog once. Idempotent."""
    global _configured
    if _configured:
        return

    settings = get_settings()
    json_logs = settings.environment != "development"

    renderer = structlog.processors.JSONRenderer() if json_logs else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(settings.log_level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str | None = None):
    configure_logging()
    return structlog.get_logger(name)
