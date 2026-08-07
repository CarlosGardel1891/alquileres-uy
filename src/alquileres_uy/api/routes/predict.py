"""POST /predict router.

Thin transport layer: validate the request via Pydantic, invoke the
:class:`Predictor` obtained through dependency injection, and return
the response schema. No ML logic lives here on purpose.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import get_predictor
from ..schemas.predict import PredictRequest, PredictResponse
from ..services.predictor import Predictor, PredictorError

router = APIRouter()


@router.post("/predict", response_model=PredictResponse)
async def predict(
    payload: PredictRequest,
    predictor: Predictor = Depends(get_predictor),  # noqa: B008 — FastAPI DI pattern
) -> PredictResponse:
    try:
        result = predictor.predict(payload)
    except PredictorError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    return PredictResponse(
        prediction=result.prediction,
        currency=result.currency,
        model_version=result.model_version,
        prediction_timestamp=result.prediction_timestamp,
    )


__all__ = ["router"]
