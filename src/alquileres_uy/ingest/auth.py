"""Token loading and redaction utilities.

Tokens are read exclusively from the ``MELI_ACCESS_TOKEN`` environment variable.
Nothing in this module logs or otherwise emits the token itself.
"""

from __future__ import annotations

import os

ACCESS_TOKEN_ENV_VAR = "MELI_ACCESS_TOKEN"
_REDACTED = "***REDACTED***"


def load_access_token() -> str | None:
    """Return the token from the environment, or ``None`` if not set."""
    value = os.environ.get(ACCESS_TOKEN_ENV_VAR)
    if value is None:
        return None
    value = value.strip()
    return value or None


def redact_headers(headers: dict[str, str] | None) -> dict[str, str]:
    """Return a copy of ``headers`` with sensitive values masked."""
    if not headers:
        return {}
    redacted: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in {"authorization", "x-auth-token", "cookie"}:
            redacted[key] = _REDACTED
        else:
            redacted[key] = value
    return redacted


def redact_url(url: str) -> str:
    """Remove any ``access_token`` query parameter from a URL."""
    if "access_token=" not in url:
        return url
    prefix, _, query = url.partition("?")
    if not query:
        return url
    parts = []
    for pair in query.split("&"):
        if pair.startswith("access_token="):
            parts.append("access_token=" + _REDACTED)
        else:
            parts.append(pair)
    return f"{prefix}?{'&'.join(parts)}"
