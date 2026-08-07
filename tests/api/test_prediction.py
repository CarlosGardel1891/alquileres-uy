"""Tests for the POST /predict endpoint and its supporting services.

The prompt forbids ``httpx`` and ``TestClient``, so route behaviour is
exercised by direct async calls + router / OpenAPI inspection (same
approach as the bootstrap tests).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from alquileres_uy.api.app import create_app
from alquileres_uy.api.dependencies import get_predictor
from alquileres_uy.api.lifespan import lifespan
from alquileres_uy.api.routes import predict as predict_route
from alquileres_uy.api.schemas.predict import PredictRequest, PredictResponse
from alquileres_uy.api.services.model_loader import (
    LoadedModel,
    ModelLoader,
    ModelUnavailableError,
)
from alquileres_uy.api.services.predictor import (
    PredictionResult,
    Predictor,
    PredictorError,
)


def _run(coro):
    return asyncio.run(coro)


def _valid_payload(**overrides) -> dict:
    payload = {
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
    payload.update(overrides)
    return payload


# ---- ModelLoader ---------------------------------------------------


def test_model_loader_loads_valid_bundle(prediction_bundle):
    loader = ModelLoader(bundle_path=prediction_bundle, allow_fixture=True)
    loaded = loader.load()
    assert isinstance(loaded, LoadedModel)
    assert loaded.model_type in {"baseline", "linear", "lightgbm"}
    assert loaded.version
    assert loaded.bundle_path == prediction_bundle


def test_model_loader_raises_when_directory_missing(tmp_path):
    loader = ModelLoader(bundle_path=tmp_path / "nope", allow_fixture=True)
    with pytest.raises(ModelUnavailableError, match="not found"):
        loader.load()


def test_model_loader_raises_when_path_is_file(tmp_path):
    file_path = tmp_path / "bundle.txt"
    file_path.write_text("not a directory", encoding="utf-8")
    loader = ModelLoader(bundle_path=file_path, allow_fixture=True)
    with pytest.raises(ModelUnavailableError, match="directory"):
        loader.load()


def test_model_loader_raises_on_invalid_bundle(prediction_bundle, tmp_path):
    """A bundle whose checksums no longer match is rejected as unavailable."""
    import shutil

    copy = tmp_path / "broken_bundle"
    shutil.copytree(prediction_bundle, copy)
    # Corrupt one payload without updating checksums.
    (copy / "metadata.json").write_text('{"broken": true}', encoding="utf-8")
    loader = ModelLoader(bundle_path=copy, allow_fixture=True)
    with pytest.raises(ModelUnavailableError, match="invalid"):
        loader.load()


def test_model_loader_refuses_fixture_bundle_by_default(prediction_bundle):
    """Without allow_fixture the loader must refuse a fixture-mode bundle."""
    loader = ModelLoader(bundle_path=prediction_bundle)  # allow_fixture=False
    with pytest.raises(ModelUnavailableError, match="invalid"):
        loader.load()


# ---- Predictor -----------------------------------------------------


def test_predictor_returns_prediction_result(prediction_bundle):
    loaded = ModelLoader(bundle_path=prediction_bundle, allow_fixture=True).load()
    predictor = Predictor(model=loaded)
    result = predictor.predict(PredictRequest(**_valid_payload()))
    assert isinstance(result, PredictionResult)
    assert result.prediction > 0
    assert result.currency == "USD"
    assert result.model_version == loaded.version
    assert isinstance(result.prediction_timestamp, datetime)


def test_predictor_prediction_is_finite(prediction_bundle):
    loaded = ModelLoader(bundle_path=prediction_bundle, allow_fixture=True).load()
    predictor = Predictor(model=loaded)
    result = predictor.predict(PredictRequest(**_valid_payload()))
    assert result.prediction == result.prediction  # not NaN
    assert result.prediction != float("inf")
    assert result.prediction != float("-inf")


def test_predictor_wraps_model_failures():
    class _Explodes:
        def predict(self, frame):
            raise RuntimeError("model boom")

    loaded = LoadedModel(
        model=_Explodes(),
        metadata={"bundle_version": "1.0.0", "model_type": "baseline"},
        bundle_path=Path("/tmp/fake"),
    )
    predictor = Predictor(model=loaded)
    with pytest.raises(PredictorError, match="model boom"):
        predictor.predict(PredictRequest(**_valid_payload()))


def test_predictor_rejects_non_numeric_output():
    class _WeirdOutput:
        def predict(self, frame):
            return ["not-a-number"]

    loaded = LoadedModel(
        model=_WeirdOutput(),
        metadata={"bundle_version": "1.0.0", "model_type": "baseline"},
        bundle_path=Path("/tmp/fake"),
    )
    predictor = Predictor(model=loaded)
    with pytest.raises(PredictorError):
        predictor.predict(PredictRequest(**_valid_payload()))


def test_predictor_uses_loaded_model_version():
    class _Constant:
        def predict(self, frame):
            return [1234.5]

    loaded = LoadedModel(
        model=_Constant(),
        metadata={"bundle_version": "9.9.9", "model_type": "baseline"},
        bundle_path=Path("/tmp/fake"),
    )
    result = Predictor(model=loaded).predict(PredictRequest(**_valid_payload()))
    assert result.model_version == "9.9.9"
    assert result.prediction == 1234.5


# ---- Request / Response schemas ------------------------------------


def test_predict_request_accepts_valid_payload():
    request = PredictRequest(**_valid_payload())
    assert request.property_type == "apartment"
    assert request.neighborhood == "Pocitos"


def test_predict_request_rejects_extra_fields():
    with pytest.raises(ValidationError):
        PredictRequest(**_valid_payload(), unexpected_field="oops")


@pytest.mark.parametrize(
    "missing_field",
    [
        "property_type",
        "price",
        "bedrooms",
        "bathrooms",
        "covered_area",
        "total_area",
        "latitude",
        "longitude",
        "neighborhood",
    ],
)
def test_predict_request_rejects_missing_field(missing_field):
    payload = _valid_payload()
    payload.pop(missing_field)
    with pytest.raises(ValidationError):
        PredictRequest(**payload)


def test_predict_request_rejects_invalid_property_type():
    with pytest.raises(ValidationError):
        PredictRequest(**_valid_payload(property_type="warehouse"))


def test_predict_request_rejects_non_positive_price():
    with pytest.raises(ValidationError):
        PredictRequest(**_valid_payload(price=0))


def test_predict_request_rejects_negative_bedrooms():
    with pytest.raises(ValidationError):
        PredictRequest(**_valid_payload(bedrooms=-1))


def test_predict_request_rejects_out_of_range_latitude():
    with pytest.raises(ValidationError):
        PredictRequest(**_valid_payload(latitude=-91))


def test_predict_request_rejects_empty_neighborhood():
    with pytest.raises(ValidationError):
        PredictRequest(**_valid_payload(neighborhood=""))


def test_predict_response_declares_exact_field_set():
    fields = set(PredictResponse.model_fields.keys())
    assert fields == {"prediction", "currency", "model_version", "prediction_timestamp"}


def test_predict_response_rejects_extra_fields():
    with pytest.raises(ValidationError):
        PredictResponse(
            prediction=1000.0,
            currency="USD",
            model_version="1.0.0",
            prediction_timestamp=datetime.now(),
            debug="nope",
        )


def test_predict_response_serializes_from_prediction_result():
    result = PredictionResult(
        prediction=1500.5,
        currency="USD",
        model_version="1.0.0",
        prediction_timestamp=datetime(2026, 8, 6, 12, 0, 0),
    )
    payload = PredictResponse(
        prediction=result.prediction,
        currency=result.currency,
        model_version=result.model_version,
        prediction_timestamp=result.prediction_timestamp,
    )
    assert payload.prediction == 1500.5
    assert payload.currency == "USD"
    assert payload.model_version == "1.0.0"


# ---- Route handler + router / OpenAPI ------------------------------


def test_predict_route_returns_response_for_valid_payload(prediction_bundle):
    loaded = ModelLoader(bundle_path=prediction_bundle, allow_fixture=True).load()
    predictor = Predictor(model=loaded)

    async def _call():
        return await predict_route.predict(
            payload=PredictRequest(**_valid_payload()),
            predictor=predictor,
        )

    response = _run(_call())
    assert isinstance(response, PredictResponse)
    assert response.prediction > 0
    assert response.currency == "USD"
    assert response.model_version == loaded.version


def test_predict_route_raises_500_when_predictor_fails():
    class _Explodes:
        def predict(self, frame):
            raise RuntimeError("boom")

    loaded = LoadedModel(
        model=_Explodes(),
        metadata={"bundle_version": "1.0.0", "model_type": "baseline"},
        bundle_path=Path("/tmp/fake"),
    )
    predictor = Predictor(model=loaded)

    async def _call():
        return await predict_route.predict(
            payload=PredictRequest(**_valid_payload()),
            predictor=predictor,
        )

    with pytest.raises(HTTPException) as info:
        _run(_call())
    assert info.value.status_code == 500


def test_predict_router_registers_one_post_route():
    routes = [r for r in predict_route.router.routes if getattr(r, "path", None) == "/predict"]
    assert len(routes) == 1
    assert "POST" in routes[0].methods


def test_created_app_registers_predict_route(api_env):
    app = create_app()
    matches = [r for r in app.router.routes if getattr(r, "path", None) == "/predict"]
    assert len(matches) == 1
    assert "POST" in matches[0].methods


def test_created_app_openapi_includes_predict(api_env):
    app = create_app()
    schema = app.openapi()
    assert "/predict" in schema["paths"]
    assert "post" in schema["paths"]["/predict"]


def test_created_app_openapi_predict_advertises_request_and_response(api_env):
    app = create_app()
    schema = app.openapi()
    post_op = schema["paths"]["/predict"]["post"]
    assert "requestBody" in post_op
    assert "PredictRequest" in json.dumps(post_op["requestBody"])
    responses = post_op["responses"]
    assert "200" in responses
    assert "PredictResponse" in json.dumps(responses["200"])


# ---- Lifespan model-loading behaviour ------------------------------


def test_lifespan_loads_model_and_publishes_predictor(api_env):
    app = FastAPI()

    async def _cycle():
        async with lifespan(app):
            return {
                "loaded_model": type(app.state.loaded_model).__name__,
                "predictor": type(app.state.predictor).__name__,
            }

    payload = _run(_cycle())
    assert payload["loaded_model"] == "LoadedModel"
    assert payload["predictor"] == "Predictor"


def test_lifespan_raises_when_model_bundle_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("ALQUILERES_API_MODEL_BUNDLE_PATH", str(tmp_path / "missing"))
    monkeypatch.setenv("ALQUILERES_API_ALLOW_FIXTURE_MODEL", "true")
    app = FastAPI()

    async def _enter():
        async with lifespan(app):
            return "should-not-reach"

    with pytest.raises(ModelUnavailableError):
        _run(_enter())


def test_lifespan_clears_state_on_shutdown(api_env):
    app = FastAPI()

    async def _cycle():
        async with lifespan(app):
            pass
        return app.state.predictor, app.state.loaded_model

    predictor, loaded = _run(_cycle())
    assert predictor is None
    assert loaded is None


def test_get_predictor_raises_when_missing(monkeypatch):
    from starlette.requests import Request as StarletteRequest

    app = FastAPI()
    scope = {
        "type": "http",
        "app": app,
        "headers": [],
        "method": "POST",
        "path": "/predict",
    }
    request = StarletteRequest(scope)
    with pytest.raises(HTTPException) as info:
        get_predictor(request)
    assert info.value.status_code == 503


# ---- End-to-end: startup + predict via app.state -------------------


def test_created_app_predict_end_to_end(api_env):
    """After lifespan, the app.state predictor answers a real request."""
    app = create_app()

    @asynccontextmanager
    async def _lifespan_ctx():
        async with app.router.lifespan_context(app):
            yield

    async def _cycle():
        async with _lifespan_ctx():
            predictor = app.state.predictor
            return predictor.predict(PredictRequest(**_valid_payload()))

    result = _run(_cycle())
    assert result.prediction > 0
    assert result.currency == "USD"


# ---- Bundle SHA reference (evidence in the entrega) ----------------


def test_prediction_bundle_has_valid_checksums(prediction_bundle):
    """The session bundle passes the checksum manifest — sanity check for entrega evidence."""
    declared = json.loads((prediction_bundle / "checksums.json").read_text(encoding="utf-8"))
    for name, expected in declared.items():
        actual = hashlib.sha256((prediction_bundle / name).read_bytes()).hexdigest()
        assert actual == expected, f"stale hash for {name}"
