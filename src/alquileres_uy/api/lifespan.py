"""Application lifespan.

Loads the serving bundle at startup so the very first request is
already warm and any misconfiguration fails immediately — never during
a client-facing call. The loaded model + a ready-to-use
:class:`Predictor` are stashed on ``app.state`` so route handlers can
pull them via :func:`get_predictor`.

Logs structured startup / shutdown lines through the project logger.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .dependencies import get_settings
from .logging_config import configure_logging, get_logger
from .metrics import set_model_loaded
from .services.model_loader import ModelLoader, ModelUnavailableError
from .services.predictor import Predictor


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load the model, expose the predictor, and yield until shutdown."""
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    logger = get_logger()
    logger.info("api startup begin | bundle_path=%s", settings.MODEL_BUNDLE_PATH)
    loader = ModelLoader(
        bundle_path=settings.MODEL_BUNDLE_PATH,
        allow_fixture=settings.ALLOW_FIXTURE_MODEL,
    )
    try:
        loaded = loader.load()
    except ModelUnavailableError:
        set_model_loaded(False)
        logger.exception("api startup: model rejected")
        raise
    logger.info(
        "api startup: model loaded | model=%s | version=%s",
        loaded.model_type,
        loaded.version,
    )
    app.state.loaded_model = loaded
    app.state.predictor = Predictor(model=loaded)
    set_model_loaded(True)
    try:
        yield
    finally:
        app.state.loaded_model = None
        app.state.predictor = None
        set_model_loaded(False)
        logger.info("api shutdown")


__all__ = ["lifespan"]
