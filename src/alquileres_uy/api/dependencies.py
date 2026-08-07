"""FastAPI dependency providers."""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from .config import ApiSettings
from .services.model_loader import LoadedModel
from .services.predictor import Predictor


def get_settings() -> ApiSettings:
    return ApiSettings()


def get_loaded_model(request: Request) -> LoadedModel:
    loaded = getattr(request.app.state, "loaded_model", None)
    if loaded is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model is not available",
        )
    return loaded


def get_predictor(request: Request) -> Predictor:
    predictor = getattr(request.app.state, "predictor", None)
    if predictor is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Predictor is not available",
        )
    return predictor


__all__ = ["get_loaded_model", "get_predictor", "get_settings"]
