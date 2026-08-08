"""Fase 7 production-hardening tests.

Same 'no httpx' constraint: routes are exercised via ASGI directly
(``httpx.ASGITransport`` is not available; we drive the app with a
minimal ASGI harness that captures the response). The Dockerfile is
verified by static inspection.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException, status

from alquileres_uy.api import errors as errors_module
from alquileres_uy.api.app import create_app
from alquileres_uy.api.config import ApiSettings
from alquileres_uy.api.errors import register_exception_handlers
from alquileres_uy.api.logging_config import (
    LOGGER_NAME,
    NO_REQUEST_ID,
    REQUEST_ID_HEADER,
    RequestIdFilter,
    configure_logging,
    get_logger,
    get_request_id,
    reset_request_id,
    set_request_id,
)
from alquileres_uy.api.middleware import RequestIdMiddleware
from alquileres_uy.api.routes import ready as ready_route
from alquileres_uy.api.routes import version as version_route
from alquileres_uy.api.services.model_loader import LoadedModel


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def project_caplog(caplog):
    """Attach caplog directly to the project logger.

    The project logger runs with ``propagate=False`` so its records
    never reach the root logger where caplog installs its handler by
    default. Attaching the caplog handler here (and restoring afterward)
    lets tests observe project-emitted log lines.
    """
    logger = get_logger()
    logger.addHandler(caplog.handler)
    original_level = logger.level
    logger.setLevel(logging.DEBUG)
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)
        logger.setLevel(original_level)


# ---- minimal ASGI harness (no httpx) --------------------------------


async def _asgi_call(
    app: FastAPI,
    method: str,
    path: str,
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
    body: bytes = b"",
    query_string: bytes = b"",
) -> dict:
    """Drive an ASGI app through one HTTP request and return the response.

    Returns ``{"status": int, "headers": {name: value}, "body": bytes}``.
    Enters the app's lifespan first so startup runs and app.state is
    populated.
    """
    result: dict = {"headers": {}, "body": b""}
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query_string,
        "headers": headers or [],
        "server": ("testserver", 80),
        "client": ("testclient", 12345),
        "app": app,
    }
    sent_body = False

    async def _receive():
        nonlocal sent_body
        if not sent_body:
            sent_body = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def _send(message):
        if message["type"] == "http.response.start":
            result["status"] = message["status"]
            result["headers"] = {k.decode(): v.decode() for k, v in message.get("headers", [])}
        elif message["type"] == "http.response.body":
            result["body"] += message.get("body", b"")

    @asynccontextmanager
    async def _lifespan_ctx():
        async with app.router.lifespan_context(app):
            yield

    async with _lifespan_ctx():
        try:
            await app(scope, _receive, _send)
        except Exception:
            # Starlette's ServerErrorMiddleware sends the error response
            # and then re-raises so the outer server can log. Real ASGI
            # servers swallow the re-raise; this harness mirrors that.
            if "status" not in result:
                raise
    return result


def _json_body(response: dict) -> dict:
    return json.loads(response["body"].decode("utf-8"))


def _header(response: dict, name: str) -> str | None:
    """Case-insensitive header lookup — ASGI normalizes to lowercase."""
    return response["headers"].get(name.lower())


# ---- config -------------------------------------------------------


def test_api_settings_include_production_knobs():
    settings = ApiSettings()
    assert isinstance(settings.HOST, str)
    assert isinstance(settings.PORT, int)
    assert isinstance(settings.LOG_LEVEL, str)
    assert isinstance(settings.REQUEST_TIMEOUT, int) and settings.REQUEST_TIMEOUT > 0
    assert isinstance(settings.MAX_WORKERS, int) and settings.MAX_WORKERS >= 1


def test_api_settings_read_production_knobs_from_env(monkeypatch):
    monkeypatch.setenv("ALQUILERES_API_HOST", "0.0.0.0")
    monkeypatch.setenv("ALQUILERES_API_PORT", "9090")
    monkeypatch.setenv("ALQUILERES_API_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("ALQUILERES_API_REQUEST_TIMEOUT", "45")
    monkeypatch.setenv("ALQUILERES_API_MAX_WORKERS", "4")
    settings = ApiSettings()
    assert settings.HOST == "0.0.0.0"
    assert settings.PORT == 9090
    assert settings.LOG_LEVEL == "DEBUG"
    assert settings.REQUEST_TIMEOUT == 45
    assert settings.MAX_WORKERS == 4


# ---- logging ------------------------------------------------------


def test_configure_logging_installs_project_logger():
    configure_logging("INFO")
    logger = get_logger()
    assert logger.name == LOGGER_NAME
    assert logger.handlers


def test_request_id_filter_injects_the_context_var():
    filt = RequestIdFilter()
    record = logging.LogRecord(LOGGER_NAME, logging.INFO, __file__, 1, "test", None, None)
    token = set_request_id("abc123")
    try:
        assert filt.filter(record) is True
        assert record.request_id == "abc123"
    finally:
        reset_request_id(token)


def test_get_request_id_defaults_when_no_active_request():
    assert get_request_id() == NO_REQUEST_ID


def test_project_logger_line_carries_request_id(project_caplog):
    logger = get_logger()
    token = set_request_id("req-1234")
    try:
        logger.info("hello world")
    finally:
        reset_request_id(token)
    matching = [
        r for r in project_caplog.records if r.name == LOGGER_NAME and "hello world" in r.message
    ]
    assert matching, "no matching log record captured"
    assert getattr(matching[-1], "request_id", None) == "req-1234"


# ---- middleware ---------------------------------------------------


def test_request_id_middleware_generates_uuid_when_missing(api_env):
    app = create_app()
    response = _run(_asgi_call(app, "GET", "/health"))
    assert response["status"] == 200
    generated = _header(response, REQUEST_ID_HEADER)
    assert generated is not None
    # uuid4().hex → 32 hex chars.
    assert re.fullmatch(r"[0-9a-f]{32}", generated), f"unexpected shape: {generated!r}"


def test_request_id_middleware_echoes_client_supplied_header(api_env):
    app = create_app()
    response = _run(
        _asgi_call(
            app,
            "GET",
            "/health",
            headers=[(REQUEST_ID_HEADER.lower().encode(), b"client-req-42")],
        )
    )
    assert response["status"] == 200
    assert _header(response, REQUEST_ID_HEADER) == "client-req-42"


def test_request_id_middleware_propagates_to_context_var(api_env):
    """Route handlers observe the id via the shared ContextVar."""
    app = create_app()

    seen_ids: list[str] = []

    async def _probe():
        seen_ids.append(get_request_id())
        return {"ok": True}

    app.add_api_route("/_probe_request_id", _probe, methods=["GET"])
    response = _run(
        _asgi_call(
            app,
            "GET",
            "/_probe_request_id",
            headers=[(REQUEST_ID_HEADER.lower().encode(), b"probe-99")],
        )
    )
    assert response["status"] == 200, f"probe route failed: {response}"
    assert seen_ids == ["probe-99"]


def test_request_id_middleware_still_sets_header_on_error(api_env, monkeypatch):
    """An error response must still carry the request id header."""
    app = create_app()

    async def _boom():
        raise RuntimeError("kaboom")

    app.add_api_route("/_boom", _boom, methods=["GET"])
    response = _run(_asgi_call(app, "GET", "/_boom", headers=[(b"x-request-id", b"err-77")]))
    assert response["status"] == 500
    assert _header(response, REQUEST_ID_HEADER) == "err-77"


# ---- error handlers ----------------------------------------------


def test_error_handler_returns_uniform_envelope_for_http_exception():
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)

    async def _forbidden():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Nope")

    app.add_api_route("/_forbidden", _forbidden, methods=["GET"])
    response = _run(_asgi_call(app, "GET", "/_forbidden"))
    assert response["status"] == 403
    body = _json_body(response)
    assert body == {"error": {"code": "forbidden", "message": "Nope"}}


def test_error_handler_returns_uniform_envelope_for_generic_exception():
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)

    async def _explode():
        raise ValueError("secret leak")

    app.add_api_route("/_explode", _explode, methods=["GET"])
    response = _run(_asgi_call(app, "GET", "/_explode"))
    assert response["status"] == 500
    body = _json_body(response)
    assert body == {"error": {"code": "internal_error", "message": "An internal error occurred"}}
    # Never leak the original message.
    assert "secret leak" not in response["body"].decode()


def test_error_handler_returns_uniform_envelope_for_request_validation(api_env):
    """POST /predict without a body triggers RequestValidationError."""
    app = create_app()
    response = _run(_asgi_call(app, "POST", "/predict"))
    assert response["status"] == 422
    body = _json_body(response)
    assert body["error"]["code"] == "validation_error"
    assert "invalid" in body["error"]["message"].lower()


def test_error_handler_never_leaks_traceback(api_env):
    """Verify the response body carries no traceback markers."""
    app = create_app()

    async def _explode():
        raise RuntimeError("boom-trace")

    app.add_api_route("/_explode_here", _explode, methods=["GET"])
    response = _run(_asgi_call(app, "GET", "/_explode_here"))
    text = response["body"].decode()
    for marker in ("Traceback", 'File "', "line ", "boom-trace"):
        assert marker not in text, f"leaked {marker!r}"


# ---- /health / /ready / /version routes --------------------------


def test_health_endpoint_returns_status_ok(api_env):
    app = create_app()
    response = _run(_asgi_call(app, "GET", "/health"))
    assert response["status"] == 200
    assert _json_body(response) == {"status": "ok"}


def test_ready_endpoint_returns_ready_when_model_loaded(api_env):
    app = create_app()
    response = _run(_asgi_call(app, "GET", "/ready"))
    assert response["status"] == 200
    assert _json_body(response) == {"status": "ready"}


def test_ready_endpoint_returns_not_ready_when_state_missing():
    """Directly probe the ready handler without going through lifespan."""
    from fastapi import Request

    app = FastAPI()
    request = Request(
        {"type": "http", "app": app, "headers": [], "method": "GET", "path": "/ready"}
    )
    response = _run(ready_route.ready(request))
    assert response.status_code == 503
    assert json.loads(response.body.decode()) == {"status": "not_ready"}


def test_ready_endpoint_flags_broken_predict_method():
    from fastapi import Request

    app = FastAPI()

    # Simulate a partially-initialized app: loaded_model exists but its
    # inner object has no predict callable.
    class _NotAModel:
        pass

    app.state.loaded_model = LoadedModel(
        model=_NotAModel(),
        metadata={"bundle_version": "1.0.0", "model_type": "baseline"},
        bundle_path=Path("/tmp/fake"),
        feature_order=("bedrooms",),
    )
    app.state.predictor = object()
    request = Request(
        {"type": "http", "app": app, "headers": [], "method": "GET", "path": "/ready"}
    )
    response = _run(ready_route.ready(request))
    assert response.status_code == 503


def test_version_endpoint_reads_metadata_from_bundle(api_env):
    app = create_app()
    response = _run(_asgi_call(app, "GET", "/version"))
    assert response["status"] == 200
    body = _json_body(response)
    for key in ("api_version", "model_version", "model_type", "trained_at", "bundle_sha256"):
        assert key in body
    # Cross-check with the actual bundle metadata on disk.
    bundle = api_env
    metadata = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
    assert body["model_version"] == str(metadata.get("bundle_version", ""))
    assert body["model_type"] == metadata["model_type"]
    assert body["bundle_sha256"] == metadata["model_artifact_sha256"]


def test_version_endpoint_returns_503_when_model_missing():
    from fastapi import Request

    app = FastAPI()
    request = Request(
        {"type": "http", "app": app, "headers": [], "method": "GET", "path": "/version"}
    )
    with pytest.raises(HTTPException) as info:
        _run(version_route.version(request))
    assert info.value.status_code == 503


# ---- predict instrumentation + logging ---------------------------


def test_predict_logs_safe_fields_only(api_env, project_caplog):
    app = create_app()

    async def _cycle():
        return await _asgi_call(
            app,
            "POST",
            "/predict",
            headers=[(b"content-type", b"application/json")],
            body=json.dumps(
                {
                    "property_type": "apartment",
                    "price": 1500.0,
                    "bedrooms": 2,
                    "bathrooms": 1,
                    "covered_area": 55.0,
                    "total_area": 60.0,
                    "latitude": -34.9,
                    "longitude": -56.2,
                    "neighborhood": "Pocitos",
                }
            ).encode(),
        )

    response = _run(_cycle())

    assert response["status"] == 200
    predict_records = [
        r for r in project_caplog.records if r.name == LOGGER_NAME and "predict" in r.message
    ]
    assert predict_records, "no predict log line captured"
    joined = " | ".join(r.message for r in predict_records)
    # Sensitive fields must NEVER appear in the logs.
    for forbidden in ("Pocitos", "-34.9", "-56.2", "1500.0", "55.0", "60.0"):
        assert forbidden not in joined, f"log leaked {forbidden!r}"
    # Required fields must appear.
    assert "duration_ms" in joined
    assert "model=" in joined
    assert "result=" in joined


def test_predict_failure_logs_error_line(api_env, monkeypatch, project_caplog):
    from alquileres_uy.api.prediction_service import PredictionService
    from alquileres_uy.api.services.predictor import PredictorError

    async def _raise(self, request):
        raise PredictorError("boom")

    # Patch the SERVICE so startup warmup still succeeds through the raw Predictor.
    monkeypatch.setattr(PredictionService, "predict", _raise, raising=True)
    app = create_app()
    response = _run(
        _asgi_call(
            app,
            "POST",
            "/predict",
            headers=[(b"content-type", b"application/json")],
            body=json.dumps(
                {
                    "property_type": "apartment",
                    "price": 1500.0,
                    "bedrooms": 2,
                    "bathrooms": 1,
                    "covered_area": 55.0,
                    "total_area": 60.0,
                    "latitude": -34.9,
                    "longitude": -56.2,
                    "neighborhood": "Pocitos",
                }
            ).encode(),
        )
    )
    assert response["status"] == 500
    body = _json_body(response)
    assert body["error"]["code"] == "internal_error"
    error_lines = [r for r in project_caplog.records if "predict failure" in r.message]
    assert error_lines, "expected a predict failure log line"


# ---- lifespan / startup / shutdown --------------------------------


def test_lifespan_logs_startup_and_shutdown(api_env, project_caplog):
    app = create_app()

    async def _cycle():
        async with app.router.lifespan_context(app):
            return True

    assert _run(_cycle()) is True
    messages = [r.message for r in project_caplog.records if r.name == LOGGER_NAME]
    assert any("startup begin" in m for m in messages)
    assert any("model loaded" in m for m in messages)
    assert any("shutdown" in m for m in messages)


def test_lifespan_logs_rejected_model(monkeypatch, tmp_path, project_caplog):
    from alquileres_uy.api.services.model_loader import ModelUnavailableError

    monkeypatch.setenv("ALQUILERES_API_MODEL_BUNDLE_PATH", str(tmp_path / "missing"))
    monkeypatch.setenv("ALQUILERES_API_ALLOW_FIXTURE_MODEL", "true")
    app = create_app()
    with pytest.raises(ModelUnavailableError):
        _run(_lifespan_enter(app))
    rejected = [r for r in project_caplog.records if "model rejected" in r.message]
    assert rejected, "expected a 'model rejected' log line"


async def _lifespan_enter(app: FastAPI) -> None:
    async with app.router.lifespan_context(app):
        return None


# ---- Docker inspection -------------------------------------------


_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_dockerfile_exists_and_has_expected_contract():
    dockerfile = (_PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    for marker in (
        "FROM python:3.12",
        "COPY requirements-api.txt",
        "pip install",
        "EXPOSE 8000",
        "scripts/run_api.py",
    ):
        assert marker in dockerfile, f"Dockerfile missing {marker!r}"


def test_dockerignore_excludes_heavy_directories():
    dockerignore = (_PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")
    for marker in (".git", ".venv", "data/", "tests/fixtures/ingest_integration_"):
        assert marker in dockerignore, f".dockerignore missing {marker!r}"


def test_ci_workflow_has_docker_build_job():
    ci = (_PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "docker-build:" in ci
    assert "docker/build-push-action@v6" in ci
    assert "push: false" in ci


# ---- OpenAPI includes the new endpoints --------------------------


def test_openapi_advertises_health_ready_version_predict(api_env):
    app = create_app()
    schema = app.openapi()
    for path in ("/health", "/ready", "/version", "/predict", "/model-info"):
        assert path in schema["paths"], f"OpenAPI missing {path}"


# ---- module hygiene ----------------------------------------------


def test_no_prints_in_api_package():
    """Structured logging is the only channel; print() must not sneak in."""
    api_root = Path(errors_module.__file__).parent
    for pyfile in api_root.rglob("*.py"):
        text = pyfile.read_text(encoding="utf-8")
        # Look for the pattern 'print(' not inside a triple-quoted docstring.
        # We simplify: a bare 'print(' anywhere is a smell; docstrings can
        # legitimately mention 'print' only inside quotes, which this
        # substring check catches too. We accept 'imprint' / 'sprint' but
        # not the standalone token.
        for line in text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            assert not re.match(
                r"\bprint\s*\(", stripped
            ), f"print() found in {pyfile.relative_to(api_root)}: {line!r}"


def test_scripts_run_api_does_not_use_print():
    text = (_PROJECT_ROOT / "scripts" / "run_api.py").read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        assert not re.match(r"\bprint\s*\(", stripped)
