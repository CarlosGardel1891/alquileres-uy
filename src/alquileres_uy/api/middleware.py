"""HTTP middlewares for the prediction API.

Two middlewares:

* :class:`RequestIdMiddleware` — installs / echoes ``X-Request-ID`` and
  publishes it on the request-scoped ContextVar so log records pick it
  up. Nothing here touches Prometheus.
* :class:`MetricsMiddleware` — measures every request's wall-clock
  duration, updates the Prometheus counters + histogram, and emits a
  single structured log line with the safe request metadata (never
  latitude, longitude, price, features or the payload). Guaranteed to
  observe latency even when the downstream stack raises — the metric
  is updated in a ``try/finally``.

Neither middleware alters the response payload.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from . import metrics as metrics_module
from .logging_config import REQUEST_ID_HEADER, get_logger, set_request_id


def _resolve_request_id(request: Request) -> str:
    header = request.headers.get(REQUEST_ID_HEADER, "").strip()
    if header:
        return header
    return uuid.uuid4().hex


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = _resolve_request_id(request)
        # ContextVars are per-task and each ASGI request runs in its own
        # task, so we do not need to reset — the value dies with the task.
        set_request_id(request_id)
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


class MetricsMiddleware(BaseHTTPMiddleware):
    """Observe latency + status_code + log line for every request."""

    def __init__(self, app, *, exclude_paths: tuple[str, ...] = ()) -> None:
        super().__init__(app)
        self._exclude = tuple(exclude_paths)
        self._logger = get_logger()

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        endpoint = request.url.path
        method = request.method
        if endpoint in self._exclude:
            return await call_next(request)

        started = time.perf_counter()
        status_code = 500  # default if downstream raises before status set
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            # ServerErrorMiddleware turns this into a 500 further out.
            # We already record the 500 latency + counters here.
            raise
        finally:
            duration_seconds = time.perf_counter() - started
            metrics_module.record_request(
                endpoint=endpoint,
                method=method,
                status_code=status_code,
                duration_seconds=duration_seconds,
            )
            model_version = self._model_version(request)
            self._logger.info(
                "http request | method=%s | endpoint=%s | status_code=%s "
                "| duration_ms=%.2f | model_version=%s",
                method,
                endpoint,
                status_code,
                duration_seconds * 1000,
                model_version,
            )

    @staticmethod
    def _model_version(request: Request) -> str:
        loaded = getattr(request.app.state, "loaded_model", None)
        if loaded is None:
            return "-"
        return getattr(loaded, "version", "-")


__all__ = ["MetricsMiddleware", "RequestIdMiddleware"]
