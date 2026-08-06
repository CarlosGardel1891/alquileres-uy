"""Artifact / serving-bundle tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import numpy as np
import pytest

from alquileres_uy.models.artifacts import (
    ArtifactError,
    atomic_run_directory,
    sha256_file,
    write_json,
)
from alquileres_uy.models.baseline import fit_baseline
from alquileres_uy.models.serving import (
    ServingBundleError,
    build_feature_schema,
    build_serving_bundle,
    compute_residual_interval,
    load_serving_bundle,
    validate_runtime_compatibility,
)


def _baseline(temporal_split_fixture):
    return fit_baseline(
        temporal_split_fixture.train, data_mode="fixture", input_hashes={"model_ready": "0" * 64}
    )


def test_atomic_publish_success(tmp_path):
    target = tmp_path / "runs" / "run1"
    with atomic_run_directory(target) as tmp:
        (tmp / "x.txt").write_text("hi", encoding="utf-8")
    assert target.is_dir()
    tmp_dir = target.with_name(target.name + ".tmp")
    assert not tmp_dir.exists()


def test_atomic_publish_cleans_tmp_on_failure(tmp_path):
    target = tmp_path / "runs" / "run1"
    with pytest.raises(RuntimeError), atomic_run_directory(target) as tmp:
        (tmp / "x.txt").write_text("hi", encoding="utf-8")
        raise RuntimeError("boom")
    assert not target.exists()
    tmp_dir = target.with_name(target.name + ".tmp")
    assert not tmp_dir.exists()


def test_atomic_publish_refuses_to_overwrite(tmp_path):
    target = tmp_path / "existing"
    target.mkdir()
    with pytest.raises(ArtifactError, match="already exists"), atomic_run_directory(target):
        pass


def test_write_json_is_deterministic_and_lf(tmp_path):
    payload = {"b": 2, "a": 1}
    write_json(tmp_path / "x.json", payload)
    text = (tmp_path / "x.json").read_bytes()
    assert b"\r\n" not in text
    # sort_keys keys → determinism regardless of insertion order.
    payload2 = {"a": 1, "b": 2}
    write_json(tmp_path / "y.json", payload2)
    assert (tmp_path / "x.json").read_bytes() == (tmp_path / "y.json").read_bytes()


def test_sha256_file(tmp_path):
    path = tmp_path / "a.txt"
    path.write_bytes(b"hello")
    import hashlib as _h

    assert sha256_file(path) == _h.sha256(b"hello").hexdigest()


def test_residual_interval_and_coverage():
    y_true = np.array([100.0, 200.0, 300.0, 400.0])
    y_pred = np.array([90.0, 210.0, 320.0, 380.0])
    interval = compute_residual_interval(y_true, y_pred, data_mode="fixture")
    assert interval.method.startswith("empirical")
    assert 0.0 <= interval.coverage <= 1.0
    assert interval.validation_rows == 4


def test_residual_interval_requires_matching_shapes():
    with pytest.raises(ServingBundleError, match="matching"):
        compute_residual_interval(np.array([1.0]), np.array([1.0, 2.0]), data_mode="fixture")


def test_feature_schema_excludes_target():
    schema = build_feature_schema()
    assert schema["target"] == "price_usd"
    assert "price_usd" not in schema["required_fields"]
    assert schema["target_excluded_from_input"] is True


def test_build_serving_bundle_writes_expected_files(tmp_path, temporal_split_fixture):
    baseline = _baseline(temporal_split_fixture)
    y_val = temporal_split_fixture.validation["price_usd"].astype(float).to_numpy()
    y_pred = baseline.predict(temporal_split_fixture.validation)
    interval = compute_residual_interval(y_val, y_pred, data_mode="fixture")
    bundle_dir = tmp_path / "bundle"
    build_serving_bundle(
        bundle_dir,
        model_name="baseline",
        model_object=baseline,
        validation_metrics={"mae_usd": 100.0},
        test_metrics={"mae_usd": 110.0},
        residual_interval=interval,
        training_run_id="run-abc",
        etl_run_id="etl-xyz",
        data_mode="fixture",
        input_hashes={"model_ready": "0" * 64},
        git_commit="abc123",
        trained_at=datetime.now(tz=UTC).isoformat(),
    )
    for name in (
        "model.joblib",
        "metadata.json",
        "feature_schema.json",
        "residual_interval.json",
        "checksums.json",
    ):
        assert (bundle_dir / name).is_file(), f"missing {name}"


def test_build_serving_bundle_rejects_torch(tmp_path, temporal_split_fixture):
    baseline = _baseline(temporal_split_fixture)
    y_val = temporal_split_fixture.validation["price_usd"].astype(float).to_numpy()
    interval = compute_residual_interval(
        y_val, baseline.predict(temporal_split_fixture.validation), data_mode="fixture"
    )
    with pytest.raises(ServingBundleError, match="serving bundle"):
        build_serving_bundle(
            tmp_path / "bundle",
            model_name="torch",
            model_object=baseline,
            validation_metrics={"mae_usd": 100.0},
            test_metrics={"mae_usd": 110.0},
            residual_interval=interval,
            training_run_id="run",
            etl_run_id="etl",
            data_mode="fixture",
            input_hashes={},
            git_commit=None,
            trained_at="2026-01-01T00:00:00+00:00",
        )


def test_load_serving_bundle_rejects_fixture_by_default(tmp_path, temporal_split_fixture):
    baseline = _baseline(temporal_split_fixture)
    y_val = temporal_split_fixture.validation["price_usd"].astype(float).to_numpy()
    interval = compute_residual_interval(
        y_val, baseline.predict(temporal_split_fixture.validation), data_mode="fixture"
    )
    bundle_dir = tmp_path / "bundle"
    build_serving_bundle(
        bundle_dir,
        model_name="baseline",
        model_object=baseline,
        validation_metrics={"mae_usd": 100.0},
        test_metrics={"mae_usd": 110.0},
        residual_interval=interval,
        training_run_id="r",
        etl_run_id="e",
        data_mode="fixture",
        input_hashes={},
        git_commit=None,
        trained_at="2026-01-01T00:00:00+00:00",
    )
    with pytest.raises(ServingBundleError, match="fixture"):
        load_serving_bundle(bundle_dir)


def test_load_serving_bundle_allow_fixture(tmp_path, temporal_split_fixture):
    baseline = _baseline(temporal_split_fixture)
    y_val = temporal_split_fixture.validation["price_usd"].astype(float).to_numpy()
    interval = compute_residual_interval(
        y_val, baseline.predict(temporal_split_fixture.validation), data_mode="fixture"
    )
    bundle_dir = tmp_path / "bundle"
    build_serving_bundle(
        bundle_dir,
        model_name="baseline",
        model_object=baseline,
        validation_metrics={"mae_usd": 100.0},
        test_metrics={"mae_usd": 110.0},
        residual_interval=interval,
        training_run_id="r",
        etl_run_id="e",
        data_mode="fixture",
        input_hashes={},
        git_commit=None,
        trained_at="2026-01-01T00:00:00+00:00",
    )
    loaded = load_serving_bundle(bundle_dir, allow_fixture=True)
    assert loaded["metadata"]["model_type"] == "baseline"


def test_load_serving_bundle_detects_checksum_tampering(tmp_path, temporal_split_fixture):
    baseline = _baseline(temporal_split_fixture)
    y_val = temporal_split_fixture.validation["price_usd"].astype(float).to_numpy()
    interval = compute_residual_interval(
        y_val, baseline.predict(temporal_split_fixture.validation), data_mode="fixture"
    )
    bundle_dir = tmp_path / "bundle"
    build_serving_bundle(
        bundle_dir,
        model_name="baseline",
        model_object=baseline,
        validation_metrics={"mae_usd": 100.0},
        test_metrics={"mae_usd": 110.0},
        residual_interval=interval,
        training_run_id="r",
        etl_run_id="e",
        data_mode="fixture",
        input_hashes={},
        git_commit=None,
        trained_at="2026-01-01T00:00:00+00:00",
    )
    # Tamper with metadata.json without touching checksums.
    metadata_path = bundle_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["model_type"] = "compromised"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ServingBundleError, match="checksum"):
        load_serving_bundle(bundle_dir, allow_fixture=True)


def _full_versions(**overrides) -> dict:
    import joblib as _joblib
    import numpy as _np
    import pandas as _pd
    import sklearn as _sklearn

    payload = {
        "python": ".".join(map(str, __import__("sys").version_info[:2])),
        "numpy": _np.__version__,
        "pandas": _pd.__version__,
        "scikit_learn": _sklearn.__version__,
        "joblib": _joblib.__version__,
    }
    payload.update(overrides)
    return payload


def test_runtime_compatibility_flags_python_mismatch():
    metadata = {"versions": _full_versions(python="99.0"), "model_type": "baseline"}
    with pytest.raises(ServingBundleError, match="python"):
        validate_runtime_compatibility(metadata)


def test_runtime_compatibility_rejects_missing_versions():
    metadata = {"versions": {}, "model_type": "baseline"}
    with pytest.raises(ServingBundleError, match="required"):
        validate_runtime_compatibility(metadata)
