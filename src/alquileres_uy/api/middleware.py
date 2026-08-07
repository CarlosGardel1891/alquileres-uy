"""Request-ID middleware.

Reads ``X-Request-ID`` from the incoming request. If absent (or empty
after strip) a fresh ``uuid4().hex`` is generated. The chosen id is
stored in a :class:`ContextVar` (so log records pick it up) and
echoed back to the client on every response, including error responses
that never reach a route handler.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .logging_config import REQUEST_ID_HEADER, set_request_id


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


__all__ = ["RequestIdMiddleware"]
