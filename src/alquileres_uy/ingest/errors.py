"""Custom exceptions for the ingestion layer."""

from __future__ import annotations


class IngestionError(Exception):
    """Base exception for all ingestion errors."""


class HttpError(IngestionError):
    """Raised for HTTP responses that were not handled by retries."""

    def __init__(self, status_code: int, message: str, url: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.url = url


class ClientHttpError(HttpError):
    """4xx responses that must not be retried automatically."""


class ServerHttpError(HttpError):
    """5xx responses that were retried but did not recover."""


class AuthenticationError(ClientHttpError):
    """401 responses."""


class AuthorizationError(ClientHttpError):
    """403 responses."""


class NotFoundError(ClientHttpError):
    """404 responses."""


class BadRequestError(ClientHttpError):
    """400 responses."""


class RateLimitError(HttpError):
    """429 responses that could not be recovered."""


class TransientNetworkError(IngestionError):
    """Wraps transient connection/timeout failures."""


class MaxRetriesExceeded(IngestionError):
    """Raised when the retry budget is exhausted."""


class SourceGateInconclusive(IngestionError):
    """Raised when the source gate cannot reach a decision."""
