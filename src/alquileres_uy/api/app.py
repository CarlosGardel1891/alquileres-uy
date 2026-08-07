"""FastAPI application factory.

The factory only wires the lifespan and the routers. It does not open
files, load models, create singletons or read from disk beyond
:class:`ApiSettings`.
"""

from __future__ import annotations

from fastapi import FastAPI

from .dependencies import get_settings
from .lifespan import lifespan
from .routes import health, model_info


def create_app() -> FastAPI:
    """Create and return the FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(model_info.router)
    return app


__all__ = ["create_app"]
