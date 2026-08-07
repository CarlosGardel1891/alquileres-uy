"""Structured logging for the production API.

* One project logger (``alquileres_uy.api``) so ops can filter easily.
* Every log record is enriched with the current ``request_id`` via a
  ``ContextVar`` and a :class:`logging.Filter`; when there is no active
  request (startup, shutdown, background) the value is ``"-"``.
* Records carry ``timestamp`` / ``level`` / ``name`` / ``request_id`` /
  ``message`` — machine-parseable single line, no traceback leak by
  default.
* :func:`configure_logging` installs a ``dictConfig`` and is idempotent
  so it can safely run at import time and again from the lifespan.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from logging.config import dictConfig

REQUEST_ID_HEADER: str = "X-Request-ID"
NO_REQUEST_ID: str = "-"
LOGGER_NAME: str = "alquileres_uy.api"

_current_request_id: ContextVar[str] = ContextVar("request_id", default=NO_REQUEST_ID)


def get_request_id() -> str:
    return _current_request_id.get()


def set_request_id(value: str) -> object:
    """Set the current request id, returning a token to reset later."""
    return _current_request_id.set(value)


def reset_request_id(token: object) -> None:
    _current_request_id.reset(token)  # type: ignore[arg-type]


class RequestIdFilter(logging.Filter):
    """Inject the active request id onto every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _current_request_id.get()
        return True


_LOGGING_INITIALIZED = False


def configure_logging(level: str = "INFO", *, force: bool = False) -> None:
    """Install the project logging configuration.

    Idempotent by default: once the config is installed the subsequent
    calls are no-ops (they preserve handlers attached by tests via
    ``caplog`` or by ops via external configuration). Pass ``force=True``
    to rebuild the config (used only from a fresh interpreter).
    """
    global _LOGGING_INITIALIZED
    if _LOGGING_INITIALIZED and not force:
        return
    normalized = (level or "INFO").upper()
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "request_id": {"()": "alquileres_uy.api.logging_config.RequestIdFilter"},
            },
            "formatters": {
                "structured": {
                    "format": (
                        "%(asctime)s | %(levelname)s | %(name)s | "
                        "request_id=%(request_id)s | %(message)s"
                    ),
                    "datefmt": "%Y-%m-%dT%H:%M:%S%z",
                },
            },
            "handlers": {
                "stderr": {
                    "class": "logging.StreamHandler",
                    "level": normalized,
                    "formatter": "structured",
                    "filters": ["request_id"],
                    "stream": "ext://sys.stderr",
                },
            },
            "loggers": {
                LOGGER_NAME: {
                    "handlers": ["stderr"],
                    "level": normalized,
                    "propagate": False,
                },
                # Quiet uvicorn's access log — we log requests ourselves.
                "uvicorn.access": {"handlers": ["stderr"], "level": "WARNING", "propagate": False},
                "uvicorn.error": {"handlers": ["stderr"], "level": "INFO", "propagate": False},
            },
            "root": {"handlers": ["stderr"], "level": "WARNING"},
        }
    )
    _LOGGING_INITIALIZED = True


def get_logger() -> logging.Logger:
    if not _LOGGING_INITIALIZED:
        configure_logging()
    return logging.getLogger(LOGGER_NAME)


__all__ = [
    "LOGGER_NAME",
    "NO_REQUEST_ID",
    "REQUEST_ID_HEADER",
    "RequestIdFilter",
    "configure_logging",
    "get_logger",
    "get_request_id",
    "reset_request_id",
    "set_request_id",
]
