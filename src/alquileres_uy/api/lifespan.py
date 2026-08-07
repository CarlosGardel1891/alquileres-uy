"""Application lifespan.

Order at startup:

1. Configure logging.
2. Load the serving bundle (raises ``ModelUnavailableError`` on failure).
3. Verify ``minimum_api_version`` against the running API — refuse to
   serve an incompatible bundle.
4. Run a synthetic warmup prediction to prime numpy / sklearn /
   lightgbm so the very first user-visible call is not slow.
5. Publish the raw :class:`Predictor`, the :class:`PredictionService`
   wrapper (semaphore + timeout + graceful shutdown) and the loaded
   bundle on ``app.state``.
6. Flip the ``model_loaded`` gauge to 1.

Order at shutdown:

1. Flip the service into ``shutting_down`` — new predictions get a
   503 ``service_unavailable``.
2. Wait for in-flight predictions to drain (bounded by the timeout).
3. Clear ``app.state`` and set the gauge to 0.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .compatibility import verify_bundle_compatibility
from .dependencies import get_settings
from .logging_config import configure_logging, get_logger
from .metrics import set_model_loaded
from .prediction_service import PredictionService
from .services.model_loader import ModelLoader, ModelUnavailableError
from .services.predictor import Predictor
from .warmup import run_warmup


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load the model, prime it, expose the service, and drain on shutdown."""
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

    # Compatibility gate happens BEFORE we mutate app.state so a
    # rejected bundle leaves the process in a clean not-ready state.
    verify_bundle_compatibility(loaded, api_version=settings.APP_VERSION)

    predictor = Predictor(model=loaded)
    # Warmup goes through the raw Predictor — never the HTTP stack, so
    # Prometheus counters stay at zero and no request line is emitted.
    run_warmup(predictor)

    service = PredictionService(
        predictor=predictor,
        max_concurrent=settings.MAX_CONCURRENT_PREDICTIONS,
        timeout_seconds=settings.PREDICT_TIMEOUT,
    )

    logger.info(
        "api startup: model loaded | model=%s | version=%s | max_concurrent=%d | timeout_s=%.2f",
        loaded.model_type,
        loaded.version,
        settings.MAX_CONCURRENT_PREDICTIONS,
        settings.PREDICT_TIMEOUT,
    )
    app.state.loaded_model = loaded
    app.state.predictor = predictor
    app.state.prediction_service = service
    set_model_loaded(True)

    try:
        yield
    finally:
        service.begin_shutdown()
        # Bounded drain so a stuck request cannot delay shutdown forever.
        await service.wait_for_drain(timeout=max(settings.PREDICT_TIMEOUT, 5.0))
        app.state.loaded_model = None
        app.state.predictor = None
        app.state.prediction_service = None
        set_model_loaded(False)
        logger.info("api shutdown")


__all__ = ["lifespan"]
