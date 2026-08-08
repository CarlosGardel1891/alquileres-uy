"""Fase 9 runtime-reliability tests.

Same 'no httpx' constraint as the previous phases: a minimal ASGI
harness drives the app end-to-end. Where possible each concern is
also exercised in isolation (compatibility check, warmup, prediction
service, benchmark stats).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI

from alquileres_uy.api.app import create_app
from alquileres_uy.api.compatibility import (
    IncompatibleBundleError,
    verify_bundle_compatibility,
)
from alquileres_uy.api.config import ApiSettings
from alquileres_uy.api.logging_config import LOGGER_NAME, get_logger
from alquileres_uy.api.metrics import REGISTRY, reset_for_tests
from alquileres_uy.api.prediction_service import (
    PredictionService,
    PredictionTimeoutError,
    ServiceShuttingDownError,
)
from alquileres_uy.api.schemas.predict import PredictRequest
from alquileres_uy.api.services.model_loader import LoadedModel, ModelLoader
from alquileres_uy.api.services.predictor import PredictionResult, Predictor
from alquileres_uy.api.warmup import WarmupError, run_warmup


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def clean_metrics():
    reset_for_tests()
    try:
        yield
    finally:
        reset_for_tests()


@pytest.fixture()
def project_caplog(caplog):
    logger = get_logger()
    logger.addHandler(caplog.handler)
    original_level = logger.level
    logger.setLevel(logging.DEBUG)
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)
        logger.setLevel(original_level)


# ---- minimal ASGI harness -----------------------------------------


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


def _valid_payload_bytes() -> bytes:
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


# ---- warmup ------------------------------------------------------


def test_warmup_success_runs_once(prediction_bundle):
    loaded = ModelLoader(bundle_path=prediction_bundle, allow_fixture=True).load()
    predictor = Predictor(model=loaded)
    calls: list = []
    original = predictor.predict

    def _counter(request):
        calls.append(request)
        return original(request)

    predictor.predict = _counter  # type: ignore[assignment]
    run_warmup(predictor)
    assert len(calls) == 1


def test_warmup_failure_raises_warmup_error():
    class _BrokenPredictor:
        def predict(self, request):
            raise RuntimeError("bad predictor")

    with pytest.raises(WarmupError, match="warmup prediction failed"):
        run_warmup(_BrokenPredictor())  # type: ignore[arg-type]


def test_warmup_does_not_touch_prometheus_counters(prediction_bundle, clean_metrics):
    loaded = ModelLoader(bundle_path=prediction_bundle, allow_fixture=True).load()
    predictor = Predictor(model=loaded)
    run_warmup(predictor)
    # No HTTP request was involved → no counter should have moved.
    for status_code in ("200", "500"):
        for endpoint in ("/predict", "/warmup", "/"):
            value = REGISTRY.get_sample_value(
                "prediction_requests_total",
                {"endpoint": endpoint, "method": "POST", "status_code": status_code},
            )
            assert value is None, f"warmup leaked to prediction_requests_total ({endpoint})"
        value = REGISTRY.get_sample_value(
            "prediction_errors_total",
            {"endpoint": "/predict", "method": "POST", "status_code": status_code},
        )
        assert value is None


def test_warmup_completed_log_line(prediction_bundle, project_caplog):
    loaded = ModelLoader(bundle_path=prediction_bundle, allow_fixture=True).load()
    predictor = Predictor(model=loaded)
    run_warmup(predictor)
    messages = [r.message for r in project_caplog.records if r.name == LOGGER_NAME]
    assert any("warmup completed" in m for m in messages)


def test_warmup_failed_log_line(project_caplog):
    class _BrokenPredictor:
        def predict(self, request):
            raise RuntimeError("kaboom")

    with pytest.raises(WarmupError):
        run_warmup(_BrokenPredictor())  # type: ignore[arg-type]
    messages = [r.message for r in project_caplog.records if r.name == LOGGER_NAME]
    assert any("warmup failed" in m for m in messages)


# ---- prediction service: semaphore + timeout ---------------------


def _make_service(*, max_concurrent: int = 2, timeout: float = 1.0) -> PredictionService:
    def _fast(request):
        return PredictionResult(
            prediction=100.0,
            currency="USD",
            model_version="test",
            prediction_timestamp=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
        )

    class _Model:
        pass

    loaded = LoadedModel(
        model=_Model(),
        metadata={"bundle_version": "1.0.0", "model_type": "baseline"},
        bundle_path=Path("/tmp/fake"),
        feature_order=("bedrooms",),
    )
    predictor = Predictor(model=loaded)
    predictor.predict = _fast  # type: ignore[assignment]
    return PredictionService(
        predictor=predictor,
        max_concurrent=max_concurrent,
        timeout_seconds=timeout,
    )


def _slow_service(
    *, delay: float, max_concurrent: int = 2, timeout: float = 5.0
) -> PredictionService:
    def _slow(request):
        time.sleep(delay)
        return PredictionResult(
            prediction=100.0,
            currency="USD",
            model_version="test",
            prediction_timestamp=__import__("datetime").datetime.now(tz=__import__("datetime").UTC),
        )

    class _Model:
        pass

    loaded = LoadedModel(
        model=_Model(),
        metadata={"bundle_version": "1.0.0", "model_type": "baseline"},
        bundle_path=Path("/tmp/fake"),
        feature_order=("bedrooms",),
    )
    predictor = Predictor(model=loaded)
    predictor.predict = _slow  # type: ignore[assignment]
    return PredictionService(
        predictor=predictor,
        max_concurrent=max_concurrent,
        timeout_seconds=timeout,
    )


def _sample_request() -> PredictRequest:
    return PredictRequest(
        property_type="apartment",
        price=1000.0,
        bedrooms=2,
        bathrooms=1,
        covered_area=50.0,
        total_area=55.0,
        latitude=-34.9,
        longitude=-56.2,
        neighborhood="Pocitos",
    )


def test_service_predict_returns_result():
    service = _make_service()
    result = _run(service.predict(_sample_request()))
    assert isinstance(result, PredictionResult)
    assert result.prediction == 100.0


def test_service_timeout_raises_prediction_timeout_error():
    service = _slow_service(delay=0.5, timeout=0.05)
    with pytest.raises(PredictionTimeoutError):
        _run(service.predict(_sample_request()))


def test_service_timeout_logs_line(project_caplog):
    service = _slow_service(delay=0.5, timeout=0.05)
    with pytest.raises(PredictionTimeoutError):
        _run(service.predict(_sample_request()))
    messages = [r.message for r in project_caplog.records if r.name == LOGGER_NAME]
    assert any("prediction timeout" in m for m in messages)


def test_service_semaphore_limits_concurrent_predictions():
    service = _slow_service(delay=0.1, max_concurrent=2, timeout=5.0)

    async def _run_concurrent():
        return await asyncio.gather(
            service.predict(_sample_request()),
            service.predict(_sample_request()),
            service.predict(_sample_request()),
            service.predict(_sample_request()),
        )

    started = time.perf_counter()
    results = _run(_run_concurrent())
    elapsed = time.perf_counter() - started
    # 4 requests times 0.1s work, 2-way concurrent → wall time ≥ 0.2s.
    assert len(results) == 4
    assert elapsed >= 0.18, f"semaphore did not serialise correctly (elapsed={elapsed:.3f})"


def test_service_semaphore_releases_on_exception():
    class _Raises:
        def predict(self, request):
            raise RuntimeError("nope")

    class _Model:
        pass

    loaded = LoadedModel(
        model=_Model(),
        metadata={"bundle_version": "1.0.0", "model_type": "baseline"},
        bundle_path=Path("/tmp/fake"),
        feature_order=("bedrooms",),
    )
    predictor = Predictor(model=loaded)
    predictor.predict = _Raises().predict  # type: ignore[assignment]
    service = PredictionService(predictor=predictor, max_concurrent=1, timeout_seconds=5.0)

    async def _hits():
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await service.predict(_sample_request())
        return service.in_flight

    assert _run(_hits()) == 0


def test_service_shutdown_rejects_new_predictions():
    service = _make_service()
    service.begin_shutdown()
    with pytest.raises(ServiceShuttingDownError):
        _run(service.predict(_sample_request()))


def test_service_shutdown_waits_for_in_flight():
    service = _slow_service(delay=0.2, max_concurrent=2, timeout=5.0)
    finished: list[bool] = []

    async def _one():
        await service.predict(_sample_request())
        finished.append(True)

    async def _scenario():
        task_one = asyncio.create_task(_one())
        task_two = asyncio.create_task(_one())
        # Let both requests enter the service.
        await asyncio.sleep(0.02)
        assert service.in_flight == 2
        service.begin_shutdown()
        # A new caller must be refused immediately.
        with pytest.raises(ServiceShuttingDownError):
            await service.predict(_sample_request())
        # But the two in-flight predictions must finish successfully.
        await service.wait_for_drain(timeout=5.0)
        await asyncio.gather(task_one, task_two)

    _run(_scenario())
    assert len(finished) == 2


def test_shutdown_log_lines(project_caplog):
    service = _slow_service(delay=0.05, max_concurrent=2, timeout=5.0)

    async def _scenario():
        task = asyncio.create_task(service.predict(_sample_request()))
        await asyncio.sleep(0.01)
        service.begin_shutdown()
        await service.wait_for_drain(timeout=5.0)
        await task

    _run(_scenario())
    messages = [r.message for r in project_caplog.records if r.name == LOGGER_NAME]
    assert any("shutdown waiting" in m for m in messages)
    assert any("shutdown completed" in m for m in messages)


# ---- bundle compatibility ----------------------------------------


def test_compatible_bundle_passes():
    loaded = LoadedModel(
        model=object(),
        metadata={
            "bundle_version": "1.0.0",
            "model_type": "baseline",
            "minimum_api_version": "0.1.0",
        },
        bundle_path=Path("/tmp/fake"),
        feature_order=("bedrooms",),
    )
    verify_bundle_compatibility(loaded, api_version="0.1.0")


def test_bundle_without_minimum_api_version_is_accepted():
    loaded = LoadedModel(
        model=object(),
        metadata={"bundle_version": "1.0.0", "model_type": "baseline"},
        bundle_path=Path("/tmp/fake"),
        feature_order=("bedrooms",),
    )
    verify_bundle_compatibility(loaded, api_version="0.1.0")


def test_incompatible_bundle_is_rejected():
    loaded = LoadedModel(
        model=object(),
        metadata={
            "bundle_version": "1.0.0",
            "model_type": "baseline",
            "minimum_api_version": "9.9.9",
        },
        bundle_path=Path("/tmp/fake"),
        feature_order=("bedrooms",),
    )
    with pytest.raises(IncompatibleBundleError, match="9.9.9"):
        verify_bundle_compatibility(loaded, api_version="0.1.0")


def test_lifespan_rejects_bundle_with_higher_minimum_api_version(
    prediction_bundle, tmp_path, monkeypatch
):
    import shutil

    copy = tmp_path / "incompatible_bundle"
    shutil.copytree(prediction_bundle, copy)
    metadata = json.loads((copy / "metadata.json").read_text(encoding="utf-8"))
    metadata["minimum_api_version"] = "99.99.99"
    (copy / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    # Rewrite checksums so the loader gets past the integrity check.
    checks = {
        name: hashlib.sha256((copy / name).read_bytes()).hexdigest()
        for name in (
            "model.joblib",
            "metadata.json",
            "feature_schema.json",
            "residual_interval.json",
        )
    }
    (copy / "checksums.json").write_text(
        json.dumps(checks, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    monkeypatch.setenv("ALQUILERES_API_MODEL_BUNDLE_PATH", str(copy))
    monkeypatch.setenv("ALQUILERES_API_ALLOW_FIXTURE_MODEL", "true")

    app = create_app()

    async def _enter():
        async with app.router.lifespan_context(app):
            pass

    with pytest.raises(IncompatibleBundleError):
        _run(_enter())


# ---- config -------------------------------------------------------


def test_new_settings_defaults():
    settings = ApiSettings()
    assert settings.MAX_CONCURRENT_PREDICTIONS >= 1
    assert settings.PREDICT_TIMEOUT > 0


def test_new_settings_env_overrides(monkeypatch):
    monkeypatch.setenv("ALQUILERES_API_MAX_CONCURRENT_PREDICTIONS", "12")
    monkeypatch.setenv("ALQUILERES_API_PREDICT_TIMEOUT", "0.75")
    settings = ApiSettings()
    assert settings.MAX_CONCURRENT_PREDICTIONS == 12
    assert settings.PREDICT_TIMEOUT == 0.75


# ---- HTTP: timeout returns 503 + prediction_timeout code ---------


def test_http_predict_timeout_returns_503_envelope(api_env, monkeypatch, clean_metrics):
    """A synthetic PredictionService that always times out returns the correct envelope."""
    from alquileres_uy.api.prediction_service import PredictionService as _Svc

    async def _timeout(self, request):
        raise PredictionTimeoutError("timed out")

    monkeypatch.setattr(_Svc, "predict", _timeout, raising=True)
    app = create_app()
    response = _run(
        _asgi_call(
            app,
            "POST",
            "/predict",
            headers=[(b"content-type", b"application/json")],
            body=_valid_payload_bytes(),
        )
    )
    assert response["status"] == 503
    body = json.loads(response["body"].decode())
    assert body == {"error": {"code": "prediction_timeout", "message": "Prediction timed out."}}


def test_http_predict_timeout_increments_errors_counter(api_env, monkeypatch, clean_metrics):
    from alquileres_uy.api.prediction_service import PredictionService as _Svc

    async def _timeout(self, request):
        raise PredictionTimeoutError("timed out")

    monkeypatch.setattr(_Svc, "predict", _timeout, raising=True)
    app = create_app()
    _run(
        _asgi_call(
            app,
            "POST",
            "/predict",
            headers=[(b"content-type", b"application/json")],
            body=_valid_payload_bytes(),
        )
    )
    err = REGISTRY.get_sample_value(
        "prediction_errors_total",
        {"endpoint": "/predict", "method": "POST", "status_code": "503"},
    )
    assert err is not None and err >= 1


def test_http_predict_shutdown_returns_503(api_env, monkeypatch, clean_metrics):
    from alquileres_uy.api.prediction_service import PredictionService as _Svc

    async def _shutdown(self, request):
        raise ServiceShuttingDownError("draining")

    monkeypatch.setattr(_Svc, "predict", _shutdown, raising=True)
    app = create_app()
    response = _run(
        _asgi_call(
            app,
            "POST",
            "/predict",
            headers=[(b"content-type", b"application/json")],
            body=_valid_payload_bytes(),
        )
    )
    assert response["status"] == 503


# ---- benchmark script --------------------------------------------


def test_benchmark_quantile_helper():
    from scripts.benchmark import _quantile

    assert _quantile([], 0.5) == 0.0
    assert _quantile([10.0], 0.5) == 10.0
    # 10, 20, 30, 40, 50 → p50 = 30, p95 ~= 48
    assert _quantile([10.0, 20.0, 30.0, 40.0, 50.0], 0.5) == 30.0
    assert _quantile([10.0, 20.0, 30.0, 40.0, 50.0], 0.95) == pytest.approx(48.0)


def test_benchmark_run_captures_stats(monkeypatch):
    from scripts import benchmark

    latencies_iter = iter([0.01, 0.02, 0.03, 0.04, 0.05])

    def _fake_fire(url, payload, timeout):
        return (next(latencies_iter), 200)

    monkeypatch.setattr(benchmark, "_fire_one", _fake_fire)
    stats = benchmark.run_benchmark(url="http://example.com", total_requests=5, concurrency=1)
    assert stats["total_requests"] == 5
    assert stats["errors"] == 0
    assert stats["status_counts"] == {"200": 5}
    for key in ("throughput_rps", "avg_ms", "p50_ms", "p95_ms", "p99_ms", "min_ms", "max_ms"):
        assert stats[key] is not None
    assert stats["min_ms"] == pytest.approx(10.0)
    assert stats["max_ms"] == pytest.approx(50.0)


def test_benchmark_reports_errors(monkeypatch):
    from scripts import benchmark

    responses = iter([(0.01, 200), (0.02, 500), (0.03, None)])

    def _fake_fire(url, payload, timeout):
        return next(responses)

    monkeypatch.setattr(benchmark, "_fire_one", _fake_fire)
    stats = benchmark.run_benchmark(url="http://example.com", total_requests=3, concurrency=1)
    assert stats["errors"] == 2  # one 500 + one network error
    assert stats["status_counts"]["500"] == 1
    assert stats["status_counts"]["network_error"] == 1


def test_benchmark_format_report_is_multiline():
    from scripts.benchmark import format_report

    stats = {
        "total_requests": 10,
        "concurrency": 2,
        "total_seconds": 1.0,
        "throughput_rps": 10.0,
        "avg_ms": 100.0,
        "min_ms": 90.0,
        "max_ms": 120.0,
        "p50_ms": 100.0,
        "p95_ms": 115.0,
        "p99_ms": 119.0,
        "status_counts": {"200": 10},
        "errors": 0,
    }
    report = format_report(stats)
    assert "total requests" in report
    assert "p95 latency" in report
    assert "errors" in report


def test_benchmark_main_exits_nonzero_on_errors(monkeypatch, capsys):
    from scripts import benchmark

    responses = iter([(0.01, 500)])

    def _fake_fire(url, payload, timeout):
        return next(responses)

    monkeypatch.setattr(benchmark, "_fire_one", _fake_fire)
    exit_code = benchmark.main(
        ["--url", "http://example.com", "--requests", "1", "--concurrency", "1"]
    )
    assert exit_code == 1


# ---- smoke script ------------------------------------------------


def test_smoke_all_pass(monkeypatch):
    from scripts import smoke_api

    def _fake_http(url, method="GET", body=None, timeout=10.0):
        if url.endswith("/health"):
            return (200, b'{"status":"ok"}', {})
        if url.endswith("/ready"):
            return (200, b'{"status":"ready"}', {})
        if url.endswith("/version"):
            payload = json.dumps(
                {
                    "api_version": "0.1.0",
                    "model_version": "1.0.0",
                    "model_type": "baseline",
                    "trained_at": "2026-01-01T00:00:00+00:00",
                    "bundle_sha256": "0" * 64,
                }
            ).encode()
            return (200, payload, {})
        if url.endswith("/metrics"):
            return (
                200,
                b"# HELP prediction_requests_total ...\n# TYPE prediction_requests_total counter\n",
                {"Content-Type": "text/plain; version=0.0.4; charset=utf-8"},
            )
        if url.endswith("/predict"):
            payload = json.dumps(
                {
                    "prediction": 1234.5,
                    "currency": "USD",
                    "model_version": "1.0.0",
                    "prediction_timestamp": "2026-01-01T00:00:00+00:00",
                }
            ).encode()
            return (200, payload, {})
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(smoke_api, "_http", _fake_http)
    exit_code = smoke_api.main(["--url", "http://example.com"])
    assert exit_code == 0


def test_smoke_reports_failure_when_any_check_breaks(monkeypatch):
    from scripts import smoke_api

    def _fake_http(url, method="GET", body=None, timeout=10.0):
        if url.endswith("/health"):
            return (503, b'{"status":"not_ready"}', {})
        return (200, b"{}", {})

    monkeypatch.setattr(smoke_api, "_http", _fake_http)
    exit_code = smoke_api.main(["--url", "http://example.com"])
    assert exit_code == 1


# ---- HTTP end-to-end: metrics + endpoints intact ---------------


def test_predict_end_to_end_via_http(api_env, clean_metrics):
    app = create_app()
    response = _run(
        _asgi_call(
            app,
            "POST",
            "/predict",
            headers=[(b"content-type", b"application/json")],
            body=_valid_payload_bytes(),
        )
    )
    assert response["status"] == 200
    body = json.loads(response["body"].decode())
    assert set(body.keys()) == {"prediction", "currency", "model_version", "prediction_timestamp"}


def test_ready_still_returns_ready_after_reliability_wiring(api_env, clean_metrics):
    app = create_app()
    response = _run(_asgi_call(app, "GET", "/ready"))
    assert response["status"] == 200
    assert json.loads(response["body"].decode()) == {"status": "ready"}


def test_lifespan_publishes_prediction_service(api_env, clean_metrics):
    app = create_app()

    async def _cycle():
        async with app.router.lifespan_context(app):
            return type(app.state.prediction_service).__name__

    assert _run(_cycle()) == "PredictionService"


def test_lifespan_lifespan_shutdown_still_logs(api_env, project_caplog, clean_metrics):
    app = create_app()

    async def _cycle():
        async with app.router.lifespan_context(app):
            pass

    _run(_cycle())
    messages = [r.message for r in project_caplog.records if r.name == LOGGER_NAME]
    assert any("api shutdown" in m for m in messages)
    assert any("shutdown completed" in m for m in messages)
