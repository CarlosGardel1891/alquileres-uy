"""Prediction service.

Bridges a :class:`~alquileres_uy.api.schemas.predict.PredictRequest` and
a :class:`~alquileres_uy.api.services.model_loader.LoadedModel` into a
concrete :class:`PredictionResult`. The service is deliberately narrow:

* it never touches the filesystem;
* it never trains or fits anything;
* it never keeps a hardcoded list of the model's features — the
  authoritative feature order comes from ``LoadedModel.feature_order``
  and the request-to-feature mapping is read from the annotations on
  :class:`PredictRequest` itself.

That leaves the Predictor free of model-specific knowledge: swap a
bundle whose ``metadata.feature_list`` differs, and this service still
works as long as :class:`PredictRequest` can supply every named
feature.
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
        contract = self._model.feature_order
        if not contract:
            raise PredictorError(
                "loaded bundle exposes no feature contract; cannot build inference frame"
            )
        available = request.to_model_features()
        missing = [name for name in contract if name not in available]
        if missing:
            raise PredictorError(
                "request cannot supply features the model requires: "
                f"{sorted(missing)} (available from request: {sorted(available)})"
            )
        row = {name: available[name] for name in contract}
        frame = pd.DataFrame([row], columns=list(contract))
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


__all__ = ["PredictionResult", "Predictor", "PredictorError"]
