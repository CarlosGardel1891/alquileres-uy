"""POST /predict router.

Thin transport layer: validate the request via Pydantic, invoke the
:class:`Predictor` obtained through dependency injection, and return
the response schema. Wraps the call with structured logging so every
request emits ``request_id`` / model / duration_ms / result — but
never latitude, longitude, price or the full payload.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import get_predictor
from ..logging_config import get_logger
from ..schemas.predict import PredictRequest, PredictResponse
from ..services.predictor import Predictor, PredictorError

router = APIRouter()

_LOGGER = get_logger()


@router.post("/predict", response_model=PredictResponse)
async def predict(
    payload: PredictRequest,
    predictor: Predictor = Depends(get_predictor),  # noqa: B008 — FastAPI DI pattern
) -> PredictResponse:
    started = time.perf_counter()
    model_type = predictor.loaded_model.model_type
    try:
        result = predictor.predict(payload)
    except PredictorError as exc:
        duration_ms = (time.perf_counter() - started) * 1000
        # Never log the payload — only safe metadata.
        _LOGGER.error(
            "predict failure | model=%s | duration_ms=%.2f | result=error",
            model_type,
            duration_ms,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    duration_ms = (time.perf_counter() - started) * 1000
    _LOGGER.info(
        "predict ok | model=%s | duration_ms=%.2f | result=ok",
        model_type,
        duration_ms,
    )
    return PredictResponse(
        prediction=result.prediction,
        currency=result.currency,
        model_version=result.model_version,
        prediction_timestamp=result.prediction_timestamp,
    )


__all__ = ["router"]
