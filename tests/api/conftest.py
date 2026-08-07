"""Shared fixtures for API tests.

Builds a real fixture serving bundle once per session so both the
prediction tests and the lifespan bootstrap tests exercise the exact
same load path the production API will run through.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from alquileres_uy.models.config import TrainingConfig
from alquileres_uy.models.pipeline import run as pipeline_run

_ETL_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "models" / "etl_run"


@pytest.fixture(scope="session")
def etl_run_dir_for_api() -> Path:
    assert (
        _ETL_FIXTURE / "model_ready.parquet"
    ).is_file(), "run `python scripts/_generate_model_fixture.py` before pytest"
    return _ETL_FIXTURE


@pytest.fixture(scope="session")
def prediction_bundle(tmp_path_factory, etl_run_dir_for_api) -> Path:
    """Build a real serving_bundle from the Fase 3 fixture ETL run.

    Session-scoped so the training pipeline runs only once. Returns
    the ``serving_bundle`` directory — the exact shape the API loader
    consumes at startup.
    """
    output_dir = tmp_path_factory.mktemp("api-serving-bundle")
    result = pipeline_run(
        TrainingConfig(
            etl_run_dir=etl_run_dir_for_api,
            output_dir=output_dir,
            fixture_mode=True,
            seed=42,
        )
    )
    bundle = result.output_dir / "serving_bundle"
    assert bundle.is_dir(), f"serving bundle missing: {bundle}"
    return bundle


@pytest.fixture()
def api_env(monkeypatch, prediction_bundle):
    """Point the API at the session bundle and allow the fixture flag."""
    monkeypatch.setenv("ALQUILERES_API_MODEL_BUNDLE_PATH", str(prediction_bundle))
    monkeypatch.setenv("ALQUILERES_API_ALLOW_FIXTURE_MODEL", "true")
    return prediction_bundle
