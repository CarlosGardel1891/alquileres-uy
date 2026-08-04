"""HTTP client for the MercadoLibre API.

The client exposes a small surface tailored to the ingestion pipeline:
search, multiget items, item descriptions and category metadata. It
implements rate limiting, selective retries with exponential backoff and
jitter, and structured error handling. All potentially sensitive values
(tokens, authorization headers, cookies) are redacted before logging.

Sleep and time functions are injected so tests can drive the client
deterministically without real waits.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Iterable, Mapping
from typing import Any

import requests
from requests import Response, Session

from alquileres_uy import __version__

from .auth import redact_headers, redact_url
from .config import IngestionConfig
from .errors import (
    AuthenticationError,
    AuthorizationError,
    BadRequestError,
    ClientHttpError,
    HttpError,
    MaxRetriesExceeded,
    NotFoundError,
    RateLimitError,
    ServerHttpError,
    TransientNetworkError,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://api.mercadolibre.com"
USER_AGENT = f"alquileres-uy/{__version__}"

RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})
BACKOFF_BASE_SECONDS = 0.5
BACKOFF_JITTER_SECONDS = 0.25
MAX_MULTIGET_BATCH_SIZE = 20


class MercadoLibreClient:
    """Thin, retry-aware wrapper around the MercadoLibre public API."""

    def __init__(
        self,
        config: IngestionConfig,
        session: Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        rng: random.Random | None = None,
    ) -> None:
        self._config = config
        self._session = session if session is not None else requests.Session()
        self._sleep = sleep
        self._clock = clock
        self._rng = rng if rng is not None else random.Random()
        self._min_interval = 1.0 / config.requests_per_second
        self._last_request_time: float | None = None
        self._session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

    # ---- public API ----------------------------------------------------

    def search_items(
        self,
        site_id: str,
        params: Mapping[str, Any] | None = None,
    ) -> Response:
        query = dict(params or {})
        return self._request("GET", f"/sites/{site_id}/search", params=query)

    def get_items(self, item_ids: Iterable[str]) -> Response:
        ids = list(item_ids)
        if not ids:
            raise ValueError("get_items requires at least one item_id")
        if len(ids) > MAX_MULTIGET_BATCH_SIZE:
            raise ValueError(f"multiget batch of {len(ids)} exceeds max {MAX_MULTIGET_BATCH_SIZE}")
        return self._request("GET", "/items", params={"ids": ",".join(ids)})

    def get_item_description(self, item_id: str) -> Response:
        return self._request("GET", f"/items/{item_id}/description")

    def get_category(self, category_id: str) -> Response:
        return self._request("GET", f"/categories/{category_id}")

    def get_category_attributes(self, category_id: str) -> Response:
        return self._request("GET", f"/categories/{category_id}/attributes")

    def get_site_categories(self, site_id: str) -> Response:
        return self._request("GET", f"/sites/{site_id}/categories")

    # ---- internals -----------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        params: Mapping[str, Any] | None = None,
    ) -> Response:
        url = f"{BASE_URL}{path}"
        headers = self._build_headers()
        loggable_headers = redact_headers(headers)

        attempts = self._config.max_attempts
        for attempt in range(1, attempts + 1):
            self._respect_rate_limit()
            logger.debug(
                "http request",
                extra={
                    "method": method,
                    "url": redact_url(url),
                    "attempt": attempt,
                    "headers": loggable_headers,
                },
            )
            try:
                response = self._session.request(
                    method,
                    url,
                    params=dict(params) if params else None,
                    headers=headers,
                    timeout=self._config.request_timeout_seconds,
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                logger.warning(
                    "transient network error",
                    extra={
                        "url": redact_url(url),
                        "attempt": attempt,
                        "error": exc.__class__.__name__,
                    },
                )
                if attempt == attempts:
                    raise MaxRetriesExceeded(
                        f"transient error after {attempts} attempts: {exc}"
                    ) from exc
                self._sleep(self._backoff_delay(attempt))
                continue
            except TransientNetworkError:
                raise
            self._last_request_time = self._clock()

            if response.status_code < 400:
                return response
            if response.status_code in RETRYABLE_STATUS_CODES:
                if attempt == attempts:
                    return self._raise_for_status(response)
                delay = self._retry_after(response) or self._backoff_delay(attempt)
                logger.warning(
                    "retryable http status",
                    extra={
                        "url": redact_url(url),
                        "status_code": response.status_code,
                        "attempt": attempt,
                        "delay": delay,
                    },
                )
                self._sleep(delay)
                continue
            return self._raise_for_status(response)

        raise MaxRetriesExceeded(f"exhausted retries for {method} {redact_url(url)}")

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._config.access_token:
            headers["Authorization"] = f"Bearer {self._config.access_token}"
        return headers

    def _respect_rate_limit(self) -> None:
        if self._last_request_time is None:
            return
        elapsed = self._clock() - self._last_request_time
        wait = self._min_interval - elapsed
        if wait > 0:
            self._sleep(wait)

    def _backoff_delay(self, attempt: int) -> float:
        base = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
        jitter = self._rng.uniform(0.0, BACKOFF_JITTER_SECONDS)
        return base + jitter

    def _retry_after(self, response: Response) -> float | None:
        value = response.headers.get("Retry-After")
        if value is None:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            return None

    def _raise_for_status(self, response: Response) -> Response:
        code = response.status_code
        url = redact_url(response.url)
        message = self._extract_message(response)
        if code == 400:
            raise BadRequestError(code, message, url=url)
        if code == 401:
            raise AuthenticationError(code, message, url=url)
        if code == 403:
            raise AuthorizationError(code, message, url=url)
        if code == 404:
            raise NotFoundError(code, message, url=url)
        if code == 429:
            raise RateLimitError(code, message, url=url)
        if 400 <= code < 500:
            raise ClientHttpError(code, message, url=url)
        if 500 <= code < 600:
            raise ServerHttpError(code, message, url=url)
        raise HttpError(code, message, url=url)

    @staticmethod
    def _extract_message(response: Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return response.text[:200] or response.reason or ""
        if isinstance(data, dict):
            for key in ("message", "error", "detail"):
                value = data.get(key)
                if isinstance(value, str):
                    return value
        return str(data)[:200]
