"""Server-side rendered Web UI (Fase 11).

Serves the single-page interface that consumes the existing prediction
API from the browser. Everything below the transport is unchanged:
the router does not touch the Predictor, PredictionService, ModelLoader
or the JSON contract of ``POST /predict`` — it only renders HTML
templates and hands them to the client. The browser then calls the
existing JSON endpoints via ``fetch()``.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..dependencies import get_settings

router = APIRouter(include_in_schema=False)

_MODULE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = _MODULE_DIR / "templates"
STATIC_DIR = _MODULE_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

REPOSITORY_URL = "https://github.com/CarlosGardel1891/alquileres-uy"


@router.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "app_name": settings.APP_NAME,
            "app_version": settings.APP_VERSION,
            "repository_url": REPOSITORY_URL,
        },
    )


__all__ = ["STATIC_DIR", "TEMPLATES_DIR", "router"]
