"""FastAPI application factory.

Wires the lifespan, the request-id middleware, the uniform error
handlers and the routers. Does not open files, load models or create
singletons beyond :class:`ApiSettings`.
"""

from __future__ import annotations

from fastapi import FastAPI

from .dependencies import get_settings
from .errors import register_exception_handlers
from .lifespan import lifespan
from .logging_config import configure_logging
from .middleware import RequestIdMiddleware
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
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(model_info.router)
    app.include_router(predict.router)
    app.include_router(ready.router)
    app.include_router(version.router)
    return app


__all__ = ["create_app"]
