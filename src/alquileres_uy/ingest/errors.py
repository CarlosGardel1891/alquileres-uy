"""Custom exceptions for the ingestion layer."""

from __future__ import annotations

from typing import Any


class IngestionError(Exception):
    """Base exception for all ingestion errors."""


class HttpError(IngestionError):
    """Raised for HTTP responses that were not handled by retries.

    ``response_body`` carries the parsed body when the response was JSON,
    a truncated string when it was not, or ``None`` when it could not be
    read. It exists so probe artifacts can preserve exactly what
    MercadoLibre answered without a second HTTP call.
    """

    def __init__(
        self,
        status_code: int,
        message: str,
        url: str | None = None,
        response_body: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.url = url
        self.response_body = response_body


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


class SourceGateApprovalMissing(IngestionError):
    """Raised when the ingestion is started without a gate approval file."""


class SourceGateApprovalInvalid(IngestionError):
    """Raised when the approval file exists but is malformed or not APPROVED."""


class SourceGateApprovalIntegrityError(IngestionError):
    """Raised when the coverage.json SHA-256 does not match the approval."""
