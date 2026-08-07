"""Pydantic schemas for POST /predict."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PredictRequest(BaseModel):
    """Rental listing features submitted by a client.

    All fields are required and unknown fields are rejected so the
    contract is unambiguous. Some fields (``price``, ``covered_area``,
    ``latitude``, ``longitude``) are captured for future features /
    diagnostics but are not consumed by the current serving model —
    the model's input contract is enforced by the Predictor when it
    projects this payload onto the feature frame.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        frozen=True,
    )

    property_type: Literal["apartment", "house"]
    price: float = Field(..., gt=0, description="Listing price the client wants to check")
    bedrooms: int = Field(..., ge=0)
    bathrooms: int = Field(..., ge=0)
    covered_area: float = Field(..., gt=0)
    total_area: float = Field(..., gt=0)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    neighborhood: str = Field(..., min_length=1)


class PredictResponse(BaseModel):
    """Model prediction returned to the client."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    prediction: float
    currency: str
    model_version: str
    prediction_timestamp: datetime


__all__ = ["PredictRequest", "PredictResponse"]
