"""Readiness probe.

Returns 200 when the predictor + model + bundle are all loaded and the
underlying model has a callable ``predict`` method. Returns 503 with
``{"status": "not_ready"}`` otherwise. Never leaks the missing piece
by name; readiness is a boolean signal.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    predictor = getattr(request.app.state, "predictor", None)
    loaded_model = getattr(request.app.state, "loaded_model", None)
    if predictor is None or loaded_model is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready"},
        )
    inner = getattr(loaded_model, "model", None)
    if inner is None or not callable(getattr(inner, "predict", None)):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready"},
        )
    return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "ready"})


__all__ = ["router"]
