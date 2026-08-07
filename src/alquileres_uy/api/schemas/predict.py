"""Pydantic schemas for POST /predict.

Each request field that maps to a model feature carries the target
feature name in its ``json_schema_extra['model_feature']`` metadata.
The Predictor uses this metadata (together with ``LoadedModel.feature_order``
from the bundle) to project the payload without ever holding a
hardcoded feature list of its own. Fields without ``model_feature``
metadata are captured for future / diagnostic use but are not consumed
by the current serving model.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Convention: the key inside ``json_schema_extra`` that stores the
# request-field → model-feature name alias. Kept as a module-level
# constant so tests and the Predictor share the same lookup key.
MODEL_FEATURE_KEY: str = "model_feature"


class PredictRequest(BaseModel):
    """Rental listing features submitted by a client.

    All fields are required and unknown fields are rejected so the
    contract is unambiguous. Fields that translate directly to a model
    feature are annotated with ``json_schema_extra={"model_feature": ...}``
    so the Predictor can build the input frame purely from the loaded
    bundle's feature contract.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        frozen=True,
    )

    property_type: Literal["apartment", "house"] = Field(
        ..., json_schema_extra={MODEL_FEATURE_KEY: "property_type"}
    )
    price: float = Field(..., gt=0, description="Listing price the client wants to check")
    bedrooms: int = Field(..., ge=0, json_schema_extra={MODEL_FEATURE_KEY: "bedrooms"})
    bathrooms: int = Field(..., ge=0, json_schema_extra={MODEL_FEATURE_KEY: "bathrooms"})
    covered_area: float = Field(..., gt=0)
    total_area: float = Field(..., gt=0, json_schema_extra={MODEL_FEATURE_KEY: "total_area_m2"})
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    neighborhood: str = Field(
        ..., min_length=1, json_schema_extra={MODEL_FEATURE_KEY: "neighborhood_normalized"}
    )

    def to_model_features(self) -> dict[str, Any]:
        """Return ``{model_feature_name: value}`` for every mapped field.

        Fields without a ``model_feature`` annotation are omitted — they
        exist for the API contract but are not consumed by the model.
        """
        payload: dict[str, Any] = {}
        for name, info in type(self).model_fields.items():
            extra = info.json_schema_extra
            if not isinstance(extra, dict):
                continue
            model_feature = extra.get(MODEL_FEATURE_KEY)
            if isinstance(model_feature, str) and model_feature:
                payload[model_feature] = getattr(self, name)
        return payload


class PredictResponse(BaseModel):
    """Model prediction returned to the client."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    prediction: float
    currency: str
    model_version: str
    prediction_timestamp: datetime


__all__ = ["MODEL_FEATURE_KEY", "PredictRequest", "PredictResponse"]
