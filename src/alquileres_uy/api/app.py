"""FastAPI application factory.

Wires the lifespan, the request-id middleware, the Prometheus metrics
middleware + exposition endpoint, the uniform error handlers and the
routers. Does not open files, load models or create singletons beyond
:class:`ApiSettings`.
"""

from __future__ import annotations

from fastapi import FastAPI
from starlette.responses import Response

from .dependencies import get_settings
from .errors import register_exception_handlers
from .lifespan import lifespan
from .logging_config import configure_logging
from .metrics import render_latest
from .middleware import MetricsMiddleware, RequestIdMiddleware
from .routes import health, model_info, predict, ready, version


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
