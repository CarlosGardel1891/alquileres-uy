"""Application lifespan.

Loads the serving bundle at startup so the very first request is
already warm and any misconfiguration fails immediately — never during
a client-facing call. The loaded model + a ready-to-use
:class:`Predictor` are stashed on ``app.state`` so route handlers can
pull them via :func:`get_predictor`.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .dependencies import get_settings
from .services.model_loader import ModelLoader
from .services.predictor import Predictor

_LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load the model, expose the predictor, and yield until shutdown."""
    settings = get_settings()
    loader = ModelLoader(
        bundle_path=settings.MODEL_BUNDLE_PATH,
        allow_fixture=settings.ALLOW_FIXTURE_MODEL,
    )
    loaded = loader.load()  # raises ModelUnavailableError if missing / invalid
    _LOGGER.info(
        "api startup: model=%s version=%s bundle=%s",
        loaded.model_type,
        loaded.version,
        loaded.bundle_path,
    )
    app.state.loaded_model = loaded
    app.state.predictor = Predictor(model=loaded)
    try:
        yield
    finally:
        app.state.loaded_model = None
        app.state.predictor = None
        _LOGGER.info("api shutdown")


__all__ = ["lifespan"]
