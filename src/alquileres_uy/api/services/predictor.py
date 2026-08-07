"""Prediction service.

Bridges a :class:`~alquileres_uy.api.schemas.predict.PredictRequest` and
a :class:`~alquileres_uy.api.services.model_loader.LoadedModel` into a
concrete :class:`PredictionResult`. The service is deliberately narrow:
no filesystem, no loading, no feature engineering. It only projects the
user payload onto the model's input contract and formats the reply.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd

from ..schemas.predict import PredictRequest
from .model_loader import LoadedModel

_PREDICTION_CURRENCY: str = "USD"


class PredictorError(RuntimeError):
    """Raised when the underlying model fails to produce a prediction."""


@dataclass(frozen=True)
class PredictionResult:
    prediction: float
    currency: str
    model_version: str
    prediction_timestamp: datetime


class Predictor:
    """Turn a validated request into a prediction using a loaded model."""

    def __init__(self, model: LoadedModel) -> None:
        self._model = model

    @property
    def loaded_model(self) -> LoadedModel:
        return self._model

    def predict(self, request: PredictRequest) -> PredictionResult:
        frame = self._project_to_model_features(request)
        try:
            raw = self._model.model.predict(frame)
        except Exception as exc:
            raise PredictorError(f"model prediction failed: {exc}") from exc
        try:
            value = float(raw[0])
        except (TypeError, IndexError, ValueError) as exc:
            raise PredictorError(f"model returned an unexpected value: {raw!r}") from exc
        return PredictionResult(
            prediction=value,
            currency=_PREDICTION_CURRENCY,
            model_version=self._model.version,
            prediction_timestamp=datetime.now(tz=UTC),
        )

    @staticmethod
    def _project_to_model_features(request: PredictRequest) -> pd.DataFrame:
        """Map the API payload to the model's exact feature contract.

        The serving model consumes ``neighborhood_normalized``,
        ``property_type``, ``bedrooms``, ``bathrooms``, ``total_area_m2``.
        API-only fields (price, covered_area, latitude, longitude) are
        intentionally discarded here — they belong to future feature
        engineering, not to the current serving model.
        """
        return pd.DataFrame(
            [
                {
                    "source_item_id": "api-request",
                    "neighborhood_normalized": request.neighborhood,
                    "property_type": request.property_type,
                    "bedrooms": request.bedrooms,
                    "bathrooms": request.bathrooms,
                    "total_area_m2": request.total_area,
                }
            ]
        )


__all__ = ["PredictionResult", "Predictor", "PredictorError"]
