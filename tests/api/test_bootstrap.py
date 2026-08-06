"""Tests for the Fase 4 API bootstrap.

The prompt forbids adding ``httpx``, so we cannot use FastAPI's
``TestClient``. The routes are exercised via direct calls to the
async handlers and via router-registration inspection — enough to
verify the bootstrap contract without pulling extra dependencies.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI, HTTPException

from alquileres_uy.api.app import create_app
from alquileres_uy.api.config import ApiSettings
from alquileres_uy.api.dependencies import get_settings
from alquileres_uy.api.lifespan import lifespan
from alquileres_uy.api.routes import health as health_route
from alquileres_uy.api.routes import model_info as model_info_route


def _run(coro):
    return asyncio.run(coro)


# ---- create_app ----------------------------------------------------


def test_create_app_returns_fastapi_instance():
    app = create_app()
    assert isinstance(app, FastAPI)


def test_create_app_uses_settings_title_and_version():
    app = create_app()
    settings = ApiSettings()
    assert app.title == settings.APP_NAME
    assert app.version == settings.APP_VERSION


def test_create_app_registers_health_and_model_info_routes():
    app = create_app()
    paths = {route.path for route in app.router.routes}
    assert "/health" in paths
    assert "/model-info" in paths


def test_create_app_wires_the_bootstrap_lifespan():
    app = create_app()
    # FastAPI stores the lifespan on the router — ensure it's wired.
    assert app.router.lifespan_context is not None


def test_create_app_returns_a_fresh_app_each_call():
    a = create_app()
    b = create_app()
    assert a is not b


# ---- config / dependencies -----------------------------------------


def test_api_settings_defaults():
    settings = ApiSettings()
    assert settings.APP_NAME
    assert settings.APP_VERSION
    assert settings.HOST
    assert isinstance(settings.PORT, int)
    assert isinstance(settings.DEBUG, bool)
    assert settings.LOG_LEVEL


def test_api_settings_env_prefix(monkeypatch):
    monkeypatch.setenv("ALQUILERES_API_APP_NAME", "custom-name")
    monkeypatch.setenv("ALQUILERES_API_PORT", "9001")
    settings = ApiSettings()
    assert settings.APP_NAME == "custom-name"
    assert settings.PORT == 9001


def test_get_settings_returns_fresh_instance_each_call():
    first = get_settings()
    second = get_settings()
    assert first is not second


def test_get_settings_returns_api_settings_instance():
    settings = get_settings()
    assert isinstance(settings, ApiSettings)


# ---- lifespan ------------------------------------------------------


def test_lifespan_startup_and_shutdown_do_not_raise():
    app = FastAPI()

    async def _enter_exit() -> str:
        async with lifespan(app):
            return "yielded"

    assert _run(_enter_exit()) == "yielded"


def test_lifespan_is_an_async_context_manager():
    # asynccontextmanager returns a helper whose __call__ produces an
    # async context manager. Calling it must not perform IO.
    cm = lifespan(FastAPI())
    assert hasattr(cm, "__aenter__")
    assert hasattr(cm, "__aexit__")


def test_lifespan_yields_none():
    app = FastAPI()

    async def _peek():
        async with lifespan(app) as value:
            return value

    assert _run(_peek()) is None


# ---- health route --------------------------------------------------


def test_health_route_returns_status_ok():
    assert _run(health_route.health()) == {"status": "ok"}


def test_health_router_registers_one_get_route():
    routes = [r for r in health_route.router.routes if r.path == "/health"]
    assert len(routes) == 1
    assert "GET" in routes[0].methods


# ---- model_info route ----------------------------------------------


def test_model_info_route_raises_501_not_implemented():
    with pytest.raises(HTTPException) as exc_info:
        _run(model_info_route.model_info())
    assert exc_info.value.status_code == 501
    assert exc_info.value.detail == "Not Implemented"


def test_model_info_router_registers_one_get_route():
    routes = [r for r in model_info_route.router.routes if r.path == "/model-info"]
    assert len(routes) == 1
    assert "GET" in routes[0].methods


# ---- end-to-end registration -------------------------------------


def test_created_app_health_route_is_reachable_via_router():
    app = create_app()
    matches = [r for r in app.router.routes if getattr(r, "path", None) == "/health"]
    assert len(matches) == 1


def test_created_app_model_info_route_is_reachable_via_router():
    app = create_app()
    matches = [r for r in app.router.routes if getattr(r, "path", None) == "/model-info"]
    assert len(matches) == 1


def test_created_app_lifespan_executes_end_to_end():
    """The lifespan runs cleanly when the app is entered — no side effects."""
    app = create_app()

    @asynccontextmanager
    async def _enter():
        async with app.router.lifespan_context(app):
            yield

    async def _cycle():
        async with _enter():
            return True

    assert _run(_cycle()) is True
