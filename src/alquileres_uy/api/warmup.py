"""Startup warmup — one synthetic prediction to prime the model libs.

Runs once from the lifespan, immediately after the bundle passes the
compatibility check. The call goes through the raw :class:`Predictor`
(never through the HTTP stack or the metrics middleware) so it does
not touch ``prediction_requests_total`` or show up as a real request.

If the predictor cannot produce a result for the synthetic payload,
startup fails with :class:`WarmupError` so the deployment is not
served with a broken model.
"""

from __future__ import annotations

from ..api.services.predictor import Predictor, PredictorError
from .logging_config import get_logger
from .schemas.predict import PredictRequest


class WarmupError(RuntimeError):
    """Raised when the startup warmup prediction fails."""


def _synthetic_payload() -> PredictRequest:
    return PredictRequest(
        property_type="apartment",
        price=1000.0,
        bedrooms=2,
        bathrooms=1,
        covered_area=50.0,
        total_area=55.0,
        latitude=-34.9,
        longitude=-56.2,
        neighborhood="__warmup__",
    )


def run_warmup(predictor: Predictor) -> None:
    """Execute a single synthetic prediction and log the outcome."""
    logger = get_logger()
    payload = _synthetic_payload()
    try:
        predictor.predict(payload)
    except PredictorError as exc:
        logger.error("warmup failed: %s", exc)
        raise WarmupError(f"warmup prediction failed: {exc}") from exc
    except Exception as exc:
        logger.exception("warmup failed with unexpected error")
        raise WarmupError(f"warmup prediction failed: {exc}") from exc
    logger.info("warmup completed")


__all__ = ["WarmupError", "run_warmup"]
