"""Uniform JSON error envelope + global exception handlers.

Every response the API sends on the error path uses:

    {"error": {"code": "<slug>", "message": "<human readable>"}}

No traceback, no internal exception detail, no request payload
echoed back. The X-Request-ID header stays attached (via the
middleware) so operators can correlate the error with the logs.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from .logging_config import NO_REQUEST_ID, REQUEST_ID_HEADER, get_logger, get_request_id


def _request_id_from(request: Request) -> str:
    """Locate the request id independently of the calling task.

    ``BaseHTTPMiddleware`` runs the downstream app in a child task; the
    ContextVar set inside that child is not visible from the outer task
    where the ``ServerErrorMiddleware``-invoked exception handler runs.
    ``request.state`` lives on ``scope['state']`` which IS shared, so
    prefer it, then fall back to the incoming header, and finally to
    the ContextVar for anything that runs in-task.
    """
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        return request_id
    header = request.headers.get(REQUEST_ID_HEADER, "").strip()
    if header:
        return header
    ctx_value = get_request_id()
    if ctx_value and ctx_value != NO_REQUEST_ID:
        return ctx_value
    return NO_REQUEST_ID


def _envelope(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def _json_error(
    status_code: int,
    *,
    code: str,
    message: str,
    request_id: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=_envelope(code, message),
        headers={REQUEST_ID_HEADER: request_id},
    )


def _slug_for_status(status_code: int) -> str:
    if status_code == 404:
        return "not_found"
    if status_code == 400:
        return "bad_request"
    if status_code == 401:
        return "unauthorized"
    if status_code == 403:
        return "forbidden"
    if status_code == 422:
        return "validation_error"
    if status_code == 500:
        return "internal_error"
    if status_code == 501:
        return "not_implemented"
    if status_code == 503:
        return "service_unavailable"
    return f"http_{status_code}"


def register_exception_handlers(app: FastAPI) -> None:
    logger = get_logger()

    @app.exception_handler(RequestValidationError)
    async def _handle_request_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = _request_id_from(request)
        logger.warning("request validation failed at %s", request.url.path)
        return _json_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="validation_error",
            message="Request payload is invalid",
            request_id=request_id,
        )

    @app.exception_handler(ValidationError)
    async def _handle_pydantic_validation(request: Request, exc: ValidationError) -> JSONResponse:
        request_id = _request_id_from(request)
        logger.warning("pydantic validation failed at %s", request.url.path)
        return _json_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="validation_error",
            message="Request payload is invalid",
            request_id=request_id,
        )

    @app.exception_handler(HTTPException)
    async def _handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        request_id = _request_id_from(request)
        code = _slug_for_status(exc.status_code)
        message = str(exc.detail) if exc.detail else code.replace("_", " ").title()
        if exc.status_code >= 500:
            logger.error("http exception %s at %s: %s", exc.status_code, request.url.path, message)
        else:
            logger.info("http exception %s at %s: %s", exc.status_code, request.url.path, message)
        return _json_error(
            exc.status_code,
            code=code,
            message=message,
            request_id=request_id,
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        request_id = _request_id_from(request)
        # Never leak the exception message or traceback to the client;
        # log the failure so ops can investigate via request_id.
        logger.exception("unhandled exception at %s", request.url.path)
        return _json_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="An internal error occurred",
            request_id=request_id,
        )


__all__ = ["register_exception_handlers"]
