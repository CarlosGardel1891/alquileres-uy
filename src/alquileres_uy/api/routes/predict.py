"""POST /predict router.

Thin transport layer: validate the request via Pydantic, hand it to
the :class:`PredictionService` (which owns the semaphore + timeout +
shutdown coordination), and shape the reply. No ML logic here.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import get_prediction_service
from ..logging_config import get_logger
from ..prediction_service import (
    PredictionService,
    PredictionTimeoutError,
    ServiceShuttingDownError,
)
from ..schemas.predict import PredictRequest, PredictResponse
from ..services.predictor import PredictorError

router = APIRouter()

_LOGGER = get_logger()


@router.post("/predict", response_model=PredictResponse)
async def predict(
    payload: PredictRequest,
    service: PredictionService = Depends(get_prediction_service),  # noqa: B008 — FastAPI DI
) -> PredictResponse:
    started = time.perf_counter()
    model_type = service.predictor.loaded_model.model_type
    try:
        result = await service.predict(payload)
    except PredictionTimeoutError as exc:
        duration_ms = (time.perf_counter() - started) * 1000
        _LOGGER.error(
            "predict timeout | model=%s | duration_ms=%.2f | result=timeout",
            model_type,
            duration_ms,
        )
        raise exc
    except ServiceShuttingDownError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service is shutting down",
        ) from exc
    except PredictorError as exc:
        duration_ms = (time.perf_counter() - started) * 1000
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
