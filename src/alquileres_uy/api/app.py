"""FastAPI application factory.

Wires the lifespan, the request-id middleware, the Prometheus metrics
middleware + exposition endpoint, the uniform error handlers (plus the
new ``prediction_timeout`` handler wrapping :class:`PredictionTimeoutError`)
and the routers. Does not open files, load models or create singletons
beyond :class:`ApiSettings`.
"""

from __future__ import annotations

from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from . import metrics as metrics_module
from .dependencies import get_settings
from .errors import _request_id_from, register_exception_handlers
from .lifespan import lifespan
from .logging_config import REQUEST_ID_HEADER, configure_logging, get_logger
from .metrics import render_latest
from .middleware import MetricsMiddleware, RequestIdMiddleware
from .prediction_service import PredictionTimeoutError
from .routes import health, model_info, predict, ready, version


def _register_prediction_timeout_handler(app: FastAPI) -> None:
    logger = get_logger()

    @app.exception_handler(PredictionTimeoutError)
    async def _handle_prediction_timeout(
        request: Request, exc: PredictionTimeoutError
    ) -> JSONResponse:
        request_id = _request_id_from(request)
        endpoint = request.url.path
        method = request.method
        # Feed the metrics collectors so the timeout shows up in
        # prediction_errors_total exactly like other 5xx failures — the
        # metrics middleware saw a raised exception and already
        # observed the latency, but the ExceptionMiddleware here catches
        # it before that finally block runs on some Starlette versions.
        # A defensive update keeps the number correct regardless.
        metrics_module.record_request(
            endpoint=endpoint,
            method=method,
            status_code=503,
            duration_seconds=0.0,
        )
        logger.warning("prediction timeout | endpoint=%s | method=%s", endpoint, method)
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "prediction_timeout",
                    "message": "Prediction timed out.",
                }
            },
            headers={REQUEST_ID_HEADER: request_id},
        )


def create_app() -> FastAPI:
    """Create and return the FastAPI application."""
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
        lifespan=lifespan,
    )
    # Middleware order: MetricsMiddleware is added LAST → runs FIRST on
    # the inbound path, so latency covers the RequestIdMiddleware and
    # everything downstream.
    app.add_middleware(RequestIdMiddleware)
    if settings.ENABLE_METRICS:
        app.add_middleware(MetricsMiddleware, exclude_paths=(settings.METRICS_PATH,))
    register_exception_handlers(app)
    _register_prediction_timeout_handler(app)
    app.include_router(health.router)
    app.include_router(model_info.router)
    app.include_router(predict.router)
    app.include_router(ready.router)
    app.include_router(version.router)
    if settings.ENABLE_METRICS:

        async def _metrics_endpoint() -> Response:
            body, content_type = render_latest()
            return Response(content=body, media_type=content_type)

        app.add_api_route(
            settings.METRICS_PATH,
            _metrics_endpoint,
            methods=["GET"],
            include_in_schema=False,
        )
    return app


__all__ = ["create_app"]
