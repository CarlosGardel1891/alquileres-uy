"""Shared fixtures for model-training tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from alquileres_uy.models.contracts import load_training_input
from alquileres_uy.models.split import temporal_split

FIXTURE_ETL = Path(__file__).resolve().parents[1] / "fixtures" / "models" / "etl_run"


@pytest.fixture(scope="session")
def model_etl_run_dir() -> Path:
    assert (FIXTURE_ETL / "model_ready.parquet").is_file(), (
        "run `python scripts/_generate_model_fixture.py` before pytest — "
        "the deterministic training fixture is missing."
    )
    return FIXTURE_ETL


@pytest.fixture()
def training_input(model_etl_run_dir):
    return load_training_input(model_etl_run_dir)


@pytest.fixture()
def temporal_split_fixture(training_input):
    return temporal_split(
        training_input.model_ready,
        train_fraction=0.7,
        validation_fraction=0.15,
        test_fraction=0.15,
    )


@pytest.fixture()
def isolated_output_dir(tmp_path):
    """Small helper so each test can point --output-dir at a fresh path."""
    out = tmp_path / "training-runs"
    out.mkdir()
    return out


@pytest.fixture()
def copy_etl_fixture(tmp_path, model_etl_run_dir):
    """Return a copy of the fixture ETL run inside tmp_path so tests can mutate it."""
    target = tmp_path / "etl_copy"
    shutil.copytree(model_etl_run_dir, target)
    return target
