"""Fase 8 — Prometheus observability tests.

Same ASGI harness the production tests use — no httpx, no TestClient.
"""

from __future__ import annotations

import asyncio
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI

from alquileres_uy.api.app import create_app
from alquileres_uy.api.config import ApiSettings
from alquileres_uy.api.metrics import (
    REGISTRY,
    record_request,
    render_latest,
    reset_for_tests,
    set_model_loaded,
)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def clean_metrics():
    reset_for_tests()
    try:
        yield
    finally:
        reset_for_tests()


# ---- minimal ASGI harness (no httpx) --------------------------------


async def _asgi_call(
    app: FastAPI,
    method: str,
    path: str,
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
    body: bytes = b"",
) -> dict:
    result: dict = {"headers": {}, "body": b""}
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers or [],
        "server": ("testserver", 80),
        "client": ("testclient", 12345),
        "app": app,
    }
    sent = [False]

    async def _receive():
        if not sent[0]:
            sent[0] = True
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
            if "status" not in result:
                raise
    return result


def _valid_predict_payload() -> bytes:
    return json.dumps(
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
    ).encode()


# ---- config -------------------------------------------------------


def test_metrics_config_defaults():
    settings = ApiSettings()
    assert settings.ENABLE_METRICS is True
    assert settings.METRICS_PATH == "/metrics"


def test_metrics_config_env_overrides(monkeypatch):
    monkeypatch.setenv("ALQUILERES_API_ENABLE_METRICS", "false")
    monkeypatch.setenv("ALQUILERES_API_METRICS_PATH", "/internal/metrics")
    settings = ApiSettings()
    assert settings.ENABLE_METRICS is False
    assert settings.METRICS_PATH == "/internal/metrics"


# ---- collectors + record helper -----------------------------------


def test_metrics_registry_is_dedicated_not_global():
    """The registry must NOT be prometheus_client's default REGISTRY."""
    from prometheus_client import REGISTRY as GLOBAL_REGISTRY

    assert REGISTRY is not GLOBAL_REGISTRY


def test_record_request_increments_counter(clean_metrics):
    record_request(endpoint="/health", method="GET", status_code=200, duration_seconds=0.01)
    value = REGISTRY.get_sample_value(
        "prediction_requests_total",
        {"endpoint": "/health", "method": "GET", "status_code": "200"},
    )
    assert value == 1.0


def test_record_request_increments_error_counter_on_5xx(clean_metrics):
    record_request(endpoint="/predict", method="POST", status_code=500, duration_seconds=0.02)
    err = REGISTRY.get_sample_value(
        "prediction_errors_total",
        {"endpoint": "/predict", "method": "POST", "status_code": "500"},
    )
    assert err == 1.0


def test_record_request_does_not_increment_error_counter_on_4xx(clean_metrics):
    record_request(endpoint="/predict", method="POST", status_code=422, duration_seconds=0.02)
    err = REGISTRY.get_sample_value(
        "prediction_errors_total",
        {"endpoint": "/predict", "method": "POST", "status_code": "422"},
    )
    assert err is None  # never observed


def test_record_request_updates_latency_histogram(clean_metrics):
    record_request(endpoint="/predict", method="POST", status_code=200, duration_seconds=0.42)
    count = REGISTRY.get_sample_value(
        "prediction_latency_seconds_count",
        {"endpoint": "/predict", "method": "POST"},
    )
    total = REGISTRY.get_sample_value(
        "prediction_latency_seconds_sum",
        {"endpoint": "/predict", "method": "POST"},
    )
    assert count == 1.0
    assert total is not None and abs(total - 0.42) < 1e-9


def test_set_model_loaded_toggles_gauge(clean_metrics):
    assert REGISTRY.get_sample_value("model_loaded") == 0.0
    set_model_loaded(True)
    assert REGISTRY.get_sample_value("model_loaded") == 1.0
    set_model_loaded(False)
    assert REGISTRY.get_sample_value("model_loaded") == 0.0


def test_render_latest_returns_prometheus_exposition(clean_metrics):
    record_request(endpoint="/health", method="GET", status_code=200, duration_seconds=0.01)
    body, content_type = render_latest()
    text = body.decode("utf-8")
    assert content_type.startswith("text/plain")
    assert "# HELP prediction_requests_total" in text
    assert "# TYPE prediction_requests_total counter" in text
    assert 'prediction_requests_total{endpoint="/health"' in text


# ---- middleware + /metrics endpoint --------------------------------


def test_metrics_endpoint_returns_200(api_env, clean_metrics):
    app = create_app()
    response = _run(_asgi_call(app, "GET", "/metrics"))
    assert response["status"] == 200
    text = response["body"].decode()
    assert "# HELP prediction_requests_total" in text
    assert response["headers"]["content-type"].startswith("text/plain")


def test_metrics_endpoint_is_excluded_from_its_own_counters(api_env, clean_metrics):
    app = create_app()
    _run(_asgi_call(app, "GET", "/metrics"))
    value = REGISTRY.get_sample_value(
        "prediction_requests_total",
        {"endpoint": "/metrics", "method": "GET", "status_code": "200"},
    )
    assert value is None


def test_health_hit_increments_requests_counter(api_env, clean_metrics):
    app = create_app()
    for _ in range(3):
        _run(_asgi_call(app, "GET", "/health"))
    value = REGISTRY.get_sample_value(
        "prediction_requests_total",
        {"endpoint": "/health", "method": "GET", "status_code": "200"},
    )
    assert value == 3.0


def test_predict_hit_increments_requests_and_latency(api_env, clean_metrics):
    app = create_app()
    response = _run(
        _asgi_call(
            app,
            "POST",
            "/predict",
            headers=[(b"content-type", b"application/json")],
            body=_valid_predict_payload(),
        )
    )
    assert response["status"] == 200
    hits = REGISTRY.get_sample_value(
        "prediction_requests_total",
        {"endpoint": "/predict", "method": "POST", "status_code": "200"},
    )
    latency_count = REGISTRY.get_sample_value(
        "prediction_latency_seconds_count",
        {"endpoint": "/predict", "method": "POST"},
    )
    assert hits == 1.0
    assert latency_count == 1.0


def test_predict_failure_increments_errors_counter(api_env, monkeypatch, clean_metrics):
    from alquileres_uy.api.services.predictor import Predictor, PredictorError

    def _explode(self, request):
        raise PredictorError("boom")

    monkeypatch.setattr(Predictor, "predict", _explode, raising=True)
    app = create_app()
    response = _run(
        _asgi_call(
            app,
            "POST",
            "/predict",
            headers=[(b"content-type", b"application/json")],
            body=_valid_predict_payload(),
        )
    )
    assert response["status"] == 500
    err = REGISTRY.get_sample_value(
        "prediction_errors_total",
        {"endpoint": "/predict", "method": "POST", "status_code": "500"},
    )
    hits = REGISTRY.get_sample_value(
        "prediction_requests_total",
        {"endpoint": "/predict", "method": "POST", "status_code": "500"},
    )
    assert err == 1.0
    assert hits == 1.0


def test_validation_failure_does_not_hit_error_counter(api_env, clean_metrics):
    app = create_app()
    response = _run(
        _asgi_call(
            app,
            "POST",
            "/predict",
            headers=[(b"content-type", b"application/json")],
            body=b"{}",  # empty payload → 422
        )
    )
    assert response["status"] == 422
    err = REGISTRY.get_sample_value(
        "prediction_errors_total",
        {"endpoint": "/predict", "method": "POST", "status_code": "422"},
    )
    assert err is None


def test_middleware_observes_latency_even_on_error(api_env, clean_metrics):
    app = create_app()

    async def _boom():
        raise RuntimeError("kaboom")

    app.add_api_route("/_boom", _boom, methods=["GET"])
    _run(_asgi_call(app, "GET", "/_boom"))
    count = REGISTRY.get_sample_value(
        "prediction_latency_seconds_count",
        {"endpoint": "/_boom", "method": "GET"},
    )
    err = REGISTRY.get_sample_value(
        "prediction_errors_total",
        {"endpoint": "/_boom", "method": "GET", "status_code": "500"},
    )
    assert count == 1.0
    assert err == 1.0


# ---- gauge behaviour ---------------------------------------------


def test_model_loaded_gauge_is_1_after_startup(api_env, clean_metrics):
    app = create_app()

    async def _cycle():
        async with app.router.lifespan_context(app):
            return REGISTRY.get_sample_value("model_loaded")

    assert _run(_cycle()) == 1.0


def test_model_loaded_gauge_returns_to_0_after_shutdown(api_env, clean_metrics):
    app = create_app()

    async def _cycle():
        async with app.router.lifespan_context(app):
            pass

    _run(_cycle())
    assert REGISTRY.get_sample_value("model_loaded") == 0.0


def test_model_loaded_gauge_is_0_when_model_fails(monkeypatch, tmp_path, clean_metrics):
    monkeypatch.setenv("ALQUILERES_API_MODEL_BUNDLE_PATH", str(tmp_path / "missing"))
    monkeypatch.setenv("ALQUILERES_API_ALLOW_FIXTURE_MODEL", "true")
    from alquileres_uy.api.services.model_loader import ModelUnavailableError

    app = create_app()

    async def _enter():
        async with app.router.lifespan_context(app):
            pass

    with pytest.raises(ModelUnavailableError):
        _run(_enter())
    assert REGISTRY.get_sample_value("model_loaded") == 0.0


# ---- other endpoints keep working --------------------------------


def test_health_endpoint_still_returns_ok_with_metrics(api_env, clean_metrics):
    app = create_app()
    response = _run(_asgi_call(app, "GET", "/health"))
    assert response["status"] == 200
    assert json.loads(response["body"].decode()) == {"status": "ok"}


def test_ready_endpoint_still_returns_ready_with_metrics(api_env, clean_metrics):
    app = create_app()
    response = _run(_asgi_call(app, "GET", "/ready"))
    assert response["status"] == 200
    assert json.loads(response["body"].decode()) == {"status": "ready"}


def test_version_endpoint_still_returns_metadata_with_metrics(api_env, clean_metrics):
    app = create_app()
    response = _run(_asgi_call(app, "GET", "/version"))
    assert response["status"] == 200
    payload = json.loads(response["body"].decode())
    assert set(payload.keys()) == {
        "api_version",
        "model_version",
        "model_type",
        "trained_at",
        "bundle_sha256",
    }


def test_predict_response_shape_unchanged_with_metrics(api_env, clean_metrics):
    app = create_app()
    response = _run(
        _asgi_call(
            app,
            "POST",
            "/predict",
            headers=[(b"content-type", b"application/json")],
            body=_valid_predict_payload(),
        )
    )
    assert response["status"] == 200
    payload = json.loads(response["body"].decode())
    assert set(payload.keys()) == {
        "prediction",
        "currency",
        "model_version",
        "prediction_timestamp",
    }


# ---- disabling metrics -------------------------------------------


def test_disabling_metrics_removes_endpoint(monkeypatch, api_env, clean_metrics):
    monkeypatch.setenv("ALQUILERES_API_ENABLE_METRICS", "false")
    app = create_app()
    paths = {getattr(r, "path", None) for r in app.router.routes}
    assert "/metrics" not in paths


def test_metrics_path_env_variable_is_honored(monkeypatch, api_env, clean_metrics):
    monkeypatch.setenv("ALQUILERES_API_METRICS_PATH", "/internal/metrics")
    app = create_app()
    response = _run(_asgi_call(app, "GET", "/internal/metrics"))
    assert response["status"] == 200
    assert "# HELP prediction_requests_total" in response["body"].decode()


# ---- middleware log line ----------------------------------------


def test_middleware_logs_enriched_line(api_env, clean_metrics):
    import logging

    from alquileres_uy.api.logging_config import get_logger

    logger = get_logger()

    class _Capture(logging.Handler):
        def __init__(self):
            super().__init__()
            self.records: list[logging.LogRecord] = []

        def emit(self, record):
            self.records.append(record)

    handler = _Capture()
    handler.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        app = create_app()
        _run(_asgi_call(app, "GET", "/health"))
    finally:
        logger.removeHandler(handler)

    request_lines = [r for r in handler.records if "http request" in r.message]
    assert request_lines, "http request log line missing"
    line = request_lines[-1].getMessage()
    for token in (
        "method=GET",
        "endpoint=/health",
        "status_code=200",
        "duration_ms=",
        "model_version=",
    ):
        assert token in line, f"missing {token!r} in log line: {line!r}"


def test_middleware_does_not_log_sensitive_predict_fields(api_env, clean_metrics):
    import logging

    from alquileres_uy.api.logging_config import get_logger

    logger = get_logger()
    captured: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record):
            captured.append(record.getMessage())

    handler = _Capture()
    handler.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        app = create_app()
        _run(
            _asgi_call(
                app,
                "POST",
                "/predict",
                headers=[(b"content-type", b"application/json")],
                body=_valid_predict_payload(),
            )
        )
    finally:
        logger.removeHandler(handler)
    joined = " | ".join(captured)
    for forbidden in ("Pocitos", "-34.9", "-56.2", "1500.0", "55.0", "60.0"):
        assert forbidden not in joined, f"log leaked {forbidden!r}"


# ---- Dockerfile / pyproject sanity ------------------------------


_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_dockerfile_installs_prometheus_client():
    """The Dockerfile installs requirements-api.txt which now lists prometheus-client."""
    reqs = (_PROJECT_ROOT / "requirements-api.txt").read_text(encoding="utf-8")
    assert re.search(
        r"^prometheus-client==", reqs, flags=re.MULTILINE
    ), "requirements-api.txt must pin prometheus-client"
