"""Behaviour tests for the six review blockers (Fase 3 corrections).

Structure follows the prompt: one section per blocker, each with tests
that observe pipeline behaviour rather than just filenames.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import joblib as _joblib
import numpy as np
import pandas as pd
import pytest

from alquileres_uy.models.baseline import refit_baseline, tune_baseline
from alquileres_uy.models.config import TrainingConfig
from alquileres_uy.models.contracts import TrainingInputError, load_training_input
from alquileres_uy.models.features import build_torch_vocabularies
from alquileres_uy.models.lightgbm_model import refit_lightgbm, tune_lightgbm
from alquileres_uy.models.linear import refit_linear, tune_linear
from alquileres_uy.models.pipeline import run as pipeline_run
from alquileres_uy.models.selection import SERVING_TIE_TOLERANCE, select_models
from alquileres_uy.models.serving import (
    ServingBundleError,
    load_serving_bundle,
)

# ---- helpers --------------------------------------------------------


def _base_config(etl_run_dir: Path, output_dir: Path, **kwargs) -> TrainingConfig:
    defaults = {
        "etl_run_dir": etl_run_dir,
        "output_dir": output_dir,
        "fixture_mode": True,
        "seed": 42,
    }
    defaults.update(kwargs)
    return TrainingConfig(**defaults)


def _refresh_hashes(root: Path) -> None:
    lineage = json.loads((root / "lineage.json").read_text(encoding="utf-8"))
    for label, filename in (
        ("model_ready", "model_ready.parquet"),
        ("etl_summary", "etl_summary.json"),
        ("schema", "schema.json"),
    ):
        lineage["output_sha256"][label] = hashlib.sha256((root / filename).read_bytes()).hexdigest()
    (root / "lineage.json").write_text(
        json.dumps(lineage, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _mutate_bathrooms(root: Path, action) -> None:
    df = pd.read_parquet(root / "model_ready.parquet")
    df = action(df)
    df.to_parquet(root / "model_ready.parquet", index=False)
    _refresh_hashes(root)


def _full_versions(model_type: str = "baseline", **overrides) -> dict:
    import sklearn as _sklearn

    payload = {
        "python": ".".join(map(str, __import__("sys").version_info[:2])),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit_learn": _sklearn.__version__,
        "joblib": _joblib.__version__,
    }
    if model_type == "lightgbm":
        import lightgbm as _lgbm

        payload["lightgbm"] = _lgbm.__version__
    payload.update(overrides)
    return payload


# ==== B1 — tuning vs final refit protocol ===========================


def test_tuning_ridge_is_fit_on_train_only(temporal_split_fixture):
    tuning = tune_linear(
        temporal_split_fixture.train,
        temporal_split_fixture.validation,
        target_column="price_usd",
        alphas=(0.1, 1.0, 10.0),
    )
    assert tuning.stage == "tuning"
    assert tuning.train_row_count == len(temporal_split_fixture.train)


def test_refit_ridge_uses_train_plus_validation(temporal_split_fixture):
    tuning = tune_linear(
        temporal_split_fixture.train,
        temporal_split_fixture.validation,
        target_column="price_usd",
        alphas=(0.1, 1.0, 10.0),
    )
    combined = pd.concat(
        [temporal_split_fixture.train, temporal_split_fixture.validation], ignore_index=True
    )
    final = refit_linear(combined, target_column="price_usd", tuning_model=tuning)
    assert final.stage == "final"
    assert final.alpha == tuning.alpha
    assert final.train_row_count == len(combined)


def test_tuning_lightgbm_is_fit_on_train_only(temporal_split_fixture):
    tuning = tune_lightgbm(
        temporal_split_fixture.train,
        temporal_split_fixture.validation,
        target_column="price_usd",
        seed=42,
    )
    assert tuning.stage == "tuning"
    assert tuning.train_row_count == len(temporal_split_fixture.train)


def test_refit_lightgbm_freezes_best_iteration(temporal_split_fixture):
    tuning = tune_lightgbm(
        temporal_split_fixture.train,
        temporal_split_fixture.validation,
        target_column="price_usd",
        seed=42,
    )
    combined = pd.concat(
        [temporal_split_fixture.train, temporal_split_fixture.validation], ignore_index=True
    )
    final = refit_lightgbm(combined, target_column="price_usd", seed=42, tuning_model=tuning)
    assert final.stage == "final"
    assert final.hyperparameters == tuning.hyperparameters
    assert final.best_iteration == tuning.best_iteration
    assert final.train_row_count == len(combined)


def test_tuning_baseline_uses_train_medians_only(temporal_split_fixture):
    tuning = tune_baseline(temporal_split_fixture.train, data_mode="fixture", input_hashes={})
    combined = pd.concat(
        [temporal_split_fixture.train, temporal_split_fixture.validation], ignore_index=True
    )
    final = refit_baseline(combined, data_mode="fixture", input_hashes={})
    # Different fit frame → different global median (unless coincidence).
    assert tuning.train_row_count == len(temporal_split_fixture.train)
    assert final.train_row_count == len(combined)


def test_changing_test_targets_does_not_change_validation_metrics(
    model_etl_run_dir, isolated_output_dir, tmp_path
):
    """The whole point of the protocol: perturbing test must not touch tuning."""
    original = pipeline_run(_base_config(model_etl_run_dir, isolated_output_dir))
    orig_metrics = json.loads((original.output_dir / "metrics.json").read_text(encoding="utf-8"))
    orig_selection = json.loads(
        (original.output_dir / "model_selection.json").read_text(encoding="utf-8")
    )
    orig_residual = json.loads(
        (original.output_dir / "serving_bundle" / "residual_interval.json").read_text(
            encoding="utf-8"
        )
    )

    # Copy the fixture and inflate the last ~15% (test region) targets.
    perturbed_dir = tmp_path / "etl_copy"
    shutil.copytree(model_etl_run_dir, perturbed_dir)
    df = pd.read_parquet(perturbed_dir / "model_ready.parquet")
    df = df.sort_values(["date_created", "source_item_id"]).reset_index(drop=True)
    cutoff = int(len(df) * 0.85)
    df.loc[df.index[cutoff:], "price_usd"] = df.loc[df.index[cutoff:], "price_usd"] * 3.0
    df.to_parquet(perturbed_dir / "model_ready.parquet", index=False)
    _refresh_hashes(perturbed_dir)

    other_out = tmp_path / "out2"
    other_out.mkdir()
    perturbed = pipeline_run(_base_config(perturbed_dir, other_out))
    new_metrics = json.loads((perturbed.output_dir / "metrics.json").read_text(encoding="utf-8"))
    new_selection = json.loads(
        (perturbed.output_dir / "model_selection.json").read_text(encoding="utf-8")
    )
    new_residual = json.loads(
        (perturbed.output_dir / "serving_bundle" / "residual_interval.json").read_text(
            encoding="utf-8"
        )
    )
    # Validation is untouched:
    for name in orig_metrics["models"]:
        assert (
            abs(
                orig_metrics["models"][name]["validation"]["mae_usd"]
                - new_metrics["models"][name]["validation"]["mae_usd"]
            )
            < 1e-6
        )
    assert orig_selection["best_overall_model"] == new_selection["best_overall_model"]
    assert orig_selection["serving_candidate"] == new_selection["serving_candidate"]
    assert orig_residual["values"] == new_residual["values"]
    # Test does change (that's the whole point):
    assert (
        orig_metrics["models"]["baseline"]["test"]["mae_usd"]
        != new_metrics["models"]["baseline"]["test"]["mae_usd"]
    )


def test_final_models_row_counts_match_train_plus_validation(
    model_etl_run_dir, isolated_output_dir
):
    result = pipeline_run(_base_config(model_etl_run_dir, isolated_output_dir))
    split = json.loads((result.output_dir / "split_manifest.json").read_text(encoding="utf-8"))
    combined = split["row_counts"]["train"] + split["row_counts"]["validation"]
    linear = _joblib.load(result.output_dir / "models" / "linear.joblib")["metadata"]
    lightgbm = _joblib.load(result.output_dir / "models" / "lightgbm.joblib")["metadata"]
    assert linear["stage"] == "final"
    assert linear["train_row_count"] == combined
    assert lightgbm["stage"] == "final"
    assert lightgbm["train_row_count"] == combined


def test_serving_bundle_carries_final_model(model_etl_run_dir, isolated_output_dir):
    result = pipeline_run(_base_config(model_etl_run_dir, isolated_output_dir))
    bundle_metadata = json.loads(
        (result.output_dir / "serving_bundle" / "metadata.json").read_text(encoding="utf-8")
    )
    model = _joblib.load(result.output_dir / "serving_bundle" / "model.joblib")
    # For the fixture, serving is baseline / linear / lightgbm — check the
    # metadata declares the same name and the model matches.
    assert bundle_metadata["model_type"] == result.serving_candidate
    if result.serving_candidate == "linear" or result.serving_candidate == "lightgbm":
        assert model["metadata"]["stage"] == "final"
    else:
        assert result.serving_candidate == "baseline"


# ==== B2 — selection anchor / no chaining ===========================


def test_best_overall_uses_mae_then_mape_then_name():
    metrics = {
        "baseline": {"mae_usd": 100.0, "mape_fraction": 0.10},
        "linear": {"mae_usd": 100.0, "mape_fraction": 0.09},
        "lightgbm": {"mae_usd": 100.0, "mape_fraction": 0.11},
    }
    result = select_models(metrics, data_mode="fixture")
    # Same MAE, linear has lower MAPE → linear wins.
    assert result.best_overall_model == "linear"


def test_best_overall_uses_name_on_full_tie():
    metrics = {
        "linear": {"mae_usd": 100.0, "mape_fraction": 0.10},
        "lightgbm": {"mae_usd": 100.0, "mape_fraction": 0.10},
    }
    result = select_models(metrics, data_mode="fixture")
    assert result.best_overall_model == "lightgbm"  # alphabetical


def test_simplicity_does_not_affect_best_overall():
    metrics = {
        "baseline": {"mae_usd": 120.0, "mape_fraction": 0.20},
        "linear": {"mae_usd": 90.0, "mape_fraction": 0.10},
        "lightgbm": {"mae_usd": 80.0, "mape_fraction": 0.09},
    }
    result = select_models(metrics, data_mode="fixture")
    assert result.best_overall_model == "lightgbm"


def test_serving_tie_anchored_to_best_eligible_mae():
    metrics = {
        "baseline": {"mae_usd": 108.0, "mape_fraction": 0.11},
        "linear": {"mae_usd": 104.0, "mape_fraction": 0.10},
        "lightgbm": {"mae_usd": 100.0, "mape_fraction": 0.09},
    }
    result = select_models(metrics, data_mode="fixture")
    # tolerance is 5 → threshold = 105 → linear stays in tie, baseline drops out.
    assert result.serving_candidate == "linear"
    assert "baseline" not in result.practical_tie_models


def test_serving_prefers_simpler_within_tolerance():
    metrics = {
        "baseline": {"mae_usd": 103.0, "mape_fraction": 0.11},
        "linear": {"mae_usd": 101.0, "mape_fraction": 0.10},
        "lightgbm": {"mae_usd": 100.0, "mape_fraction": 0.09},
    }
    result = select_models(metrics, data_mode="fixture")
    # threshold 105 → all three in the tie, simpler baseline wins.
    assert result.serving_candidate == "baseline"


def test_serving_never_picks_torch():
    metrics = {
        "baseline": {"mae_usd": 200.0, "mape_fraction": 0.20},
        "linear": {"mae_usd": 150.0, "mape_fraction": 0.15},
        "lightgbm": {"mae_usd": 120.0, "mape_fraction": 0.12},
        "torch": {"mae_usd": 80.0, "mape_fraction": 0.08},
    }
    result = select_models(metrics, data_mode="fixture")
    assert result.best_overall_model == "torch"
    assert result.serving_candidate in {"baseline", "linear", "lightgbm"}


def test_selection_rejects_nan_metrics():
    metrics = {"linear": {"mae_usd": float("nan"), "mape_fraction": 0.10}}
    with pytest.raises(ValueError, match="finite"):
        select_models(metrics, data_mode="fixture")


def test_selection_rejects_infinite_metrics():
    metrics = {"linear": {"mae_usd": float("inf"), "mape_fraction": 0.10}}
    with pytest.raises(ValueError, match="finite"):
        select_models(metrics, data_mode="fixture")


def test_selection_records_practical_tie_metadata():
    metrics = {
        "baseline": {"mae_usd": 102.0, "mape_fraction": 0.11},
        "linear": {"mae_usd": 100.0, "mape_fraction": 0.10},
        "lightgbm": {"mae_usd": 99.0, "mape_fraction": 0.09},
    }
    result = select_models(metrics, data_mode="fixture")
    assert result.best_eligible_mae == 99.0
    assert result.practical_tie_threshold == 99.0 + SERVING_TIE_TOLERANCE
    assert result.simplicity_order == ("baseline", "linear", "lightgbm")


# ==== B3 — training lineage IDs + config hash + approval hash =======


def test_training_run_id_and_etl_run_id_are_distinct(model_etl_run_dir, isolated_output_dir):
    result = pipeline_run(_base_config(model_etl_run_dir, isolated_output_dir))
    lineage = json.loads((result.output_dir / "training_lineage.json").read_text(encoding="utf-8"))
    summary = json.loads((result.output_dir / "training_summary.json").read_text(encoding="utf-8"))
    assert lineage["training_run_id"] == result.training_run_id
    assert lineage["etl_run_id"] != lineage["training_run_id"]
    assert summary["training_run_id"] == lineage["training_run_id"]
    assert summary["etl_run_id"] == lineage["etl_run_id"]


def test_serving_metadata_shares_training_run_id(model_etl_run_dir, isolated_output_dir):
    result = pipeline_run(_base_config(model_etl_run_dir, isolated_output_dir))
    metadata = json.loads(
        (result.output_dir / "serving_bundle" / "metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["training_run_id"] == result.training_run_id


def test_training_config_json_exists_and_is_hashed(model_etl_run_dir, isolated_output_dir):
    result = pipeline_run(_base_config(model_etl_run_dir, isolated_output_dir))
    config_path = result.output_dir / "training_config.json"
    assert config_path.is_file()
    declared = json.loads(
        (result.output_dir / "training_lineage.json").read_text(encoding="utf-8")
    )["inputs_sha256"]["training_config"]
    actual = hashlib.sha256(config_path.read_bytes()).hexdigest()
    assert declared == actual


def test_lineage_outputs_cover_everything_except_itself(model_etl_run_dir, isolated_output_dir):
    result = pipeline_run(_base_config(model_etl_run_dir, isolated_output_dir))
    lineage_path = result.output_dir / "training_lineage.json"
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    outputs = set(lineage["outputs_sha256"].keys())
    assert "training_lineage.json" not in outputs
    for path in result.output_dir.rglob("*"):
        if not path.is_file() or path.name == "training_lineage.json":
            continue
        rel = str(path.relative_to(result.output_dir)).replace("\\", "/")
        assert rel in outputs, f"lineage missing output {rel}"


def test_fixture_mode_does_not_invent_approval(model_etl_run_dir, isolated_output_dir):
    result = pipeline_run(_base_config(model_etl_run_dir, isolated_output_dir))
    lineage = json.loads((result.output_dir / "training_lineage.json").read_text(encoding="utf-8"))
    assert "etl_approval" not in lineage["inputs_sha256"]


def test_lineage_has_no_absolute_paths_or_traversal(model_etl_run_dir, isolated_output_dir):
    result = pipeline_run(_base_config(model_etl_run_dir, isolated_output_dir))
    lineage = json.loads((result.output_dir / "training_lineage.json").read_text(encoding="utf-8"))
    for rel in lineage["outputs_sha256"]:
        assert not rel.startswith("/")
        assert not (len(rel) >= 2 and rel[1] == ":")
        assert ".." not in Path(rel).parts


def test_all_lineage_hashes_are_64_hex(model_etl_run_dir, isolated_output_dir):
    result = pipeline_run(_base_config(model_etl_run_dir, isolated_output_dir))
    lineage = json.loads((result.output_dir / "training_lineage.json").read_text(encoding="utf-8"))
    for value in list(lineage["inputs_sha256"].values()) + list(lineage["outputs_sha256"].values()):
        if value is None:
            continue
        assert len(value) == 64
        int(value, 16)  # raises if non-hex


# ==== B4 — validate runtime before joblib.load ======================


def _make_bundle(model_etl_run_dir, out) -> Path:
    result = pipeline_run(_base_config(model_etl_run_dir, out))
    return result.output_dir / "serving_bundle"


def test_valid_bundle_loads_when_allow_fixture(model_etl_run_dir, isolated_output_dir):
    bundle = _make_bundle(model_etl_run_dir, isolated_output_dir)
    loaded = load_serving_bundle(bundle, allow_fixture=True)
    assert "model" in loaded


def test_load_bundle_rejects_fixture_without_flag(model_etl_run_dir, isolated_output_dir):
    bundle = _make_bundle(model_etl_run_dir, isolated_output_dir)
    # Also monkey-patch joblib.load so we can assert it isn't reached.
    original_load = _joblib.load
    calls = []

    def _tracer(*args, **kwargs):
        calls.append(args)
        return original_load(*args, **kwargs)

    _joblib.load = _tracer
    try:
        with pytest.raises(ServingBundleError, match="fixture"):
            load_serving_bundle(bundle)
    finally:
        _joblib.load = original_load
    assert calls == []


def test_load_bundle_rejects_missing_versions(model_etl_run_dir, isolated_output_dir, monkeypatch):
    bundle = _make_bundle(model_etl_run_dir, isolated_output_dir)
    metadata_path = bundle / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["versions"] = {}
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    # Rewrite checksums for the tampered metadata so the failure is
    # runtime, not integrity.
    _rewrite_checksums(bundle)

    calls = []
    monkeypatch.setattr(_joblib, "load", lambda *a, **kw: calls.append(a))
    with pytest.raises(ServingBundleError, match="required"):
        load_serving_bundle(bundle, allow_fixture=True)
    assert calls == []


def test_load_bundle_rejects_python_mismatch(model_etl_run_dir, isolated_output_dir, monkeypatch):
    bundle = _make_bundle(model_etl_run_dir, isolated_output_dir)
    metadata_path = bundle / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["versions"]["python"] = "99.99"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    _rewrite_checksums(bundle)

    calls = []
    monkeypatch.setattr(_joblib, "load", lambda *a, **kw: calls.append(a))
    with pytest.raises(ServingBundleError, match="python"):
        load_serving_bundle(bundle, allow_fixture=True)
    assert calls == []


def test_load_bundle_rejects_joblib_mismatch(model_etl_run_dir, isolated_output_dir, monkeypatch):
    bundle = _make_bundle(model_etl_run_dir, isolated_output_dir)
    metadata_path = bundle / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["versions"]["joblib"] = "99.0"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    _rewrite_checksums(bundle)

    calls = []
    monkeypatch.setattr(_joblib, "load", lambda *a, **kw: calls.append(a))
    with pytest.raises(ServingBundleError, match="joblib"):
        load_serving_bundle(bundle, allow_fixture=True)
    assert calls == []


def test_load_bundle_rejects_bad_model_artifact_hash(
    model_etl_run_dir, isolated_output_dir, monkeypatch
):
    bundle = _make_bundle(model_etl_run_dir, isolated_output_dir)
    metadata_path = bundle / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["model_artifact_sha256"] = "0" * 64
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    _rewrite_checksums(bundle)

    calls = []
    monkeypatch.setattr(_joblib, "load", lambda *a, **kw: calls.append(a))
    with pytest.raises(ServingBundleError, match="model_artifact_sha256"):
        load_serving_bundle(bundle, allow_fixture=True)
    assert calls == []


def test_checksums_rejects_traversal_and_bad_hash(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "model.joblib").write_bytes(b"x")
    (bundle / "metadata.json").write_text("{}", encoding="utf-8")
    (bundle / "feature_schema.json").write_text("{}", encoding="utf-8")
    (bundle / "residual_interval.json").write_text("{}", encoding="utf-8")
    (bundle / "checksums.json").write_text(json.dumps({"../evil.txt": "0" * 64}), encoding="utf-8")
    with pytest.raises(ServingBundleError, match="safe filename"):
        load_serving_bundle(bundle, allow_fixture=True)


def test_checksums_rejects_non_hex(model_etl_run_dir, isolated_output_dir, monkeypatch):
    bundle = _make_bundle(model_etl_run_dir, isolated_output_dir)
    checks = json.loads((bundle / "checksums.json").read_text(encoding="utf-8"))
    key = next(iter(checks))
    checks[key] = "zz" * 32
    (bundle / "checksums.json").write_text(json.dumps(checks), encoding="utf-8")
    calls = []
    monkeypatch.setattr(_joblib, "load", lambda *a, **kw: calls.append(a))
    with pytest.raises(ServingBundleError, match="sha256"):
        load_serving_bundle(bundle, allow_fixture=True)
    assert calls == []


def test_missing_checksums_file(model_etl_run_dir, isolated_output_dir):
    bundle = _make_bundle(model_etl_run_dir, isolated_output_dir)
    (bundle / "checksums.json").unlink()
    with pytest.raises(ServingBundleError, match="checksums"):
        load_serving_bundle(bundle, allow_fixture=True)


@pytest.mark.torch
def test_pytorch_never_becomes_serving_model(model_etl_run_dir, isolated_output_dir):
    result = pipeline_run(_base_config(model_etl_run_dir, isolated_output_dir, include_torch=True))
    metadata = json.loads(
        (result.output_dir / "serving_bundle" / "metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["model_type"] != "torch"


# ==== B5 — hardened input contract + median bathrooms ==============


def test_source_item_id_int_rejected(copy_etl_fixture):
    df = pd.read_parquet(copy_etl_fixture / "model_ready.parquet")
    df["source_item_id"] = list(range(len(df)))
    df.to_parquet(copy_etl_fixture / "model_ready.parquet", index=False)
    _refresh_hashes(copy_etl_fixture)
    with pytest.raises(TrainingInputError, match="source_item_id"):
        load_training_input(copy_etl_fixture)


def test_source_item_id_whitespace_only_rejected(copy_etl_fixture):
    df = pd.read_parquet(copy_etl_fixture / "model_ready.parquet")
    df.loc[df.index[0], "source_item_id"] = "   "
    df.to_parquet(copy_etl_fixture / "model_ready.parquet", index=False)
    _refresh_hashes(copy_etl_fixture)
    with pytest.raises(TrainingInputError, match="source_item_id"):
        load_training_input(copy_etl_fixture)


def test_neighborhood_empty_rejected(copy_etl_fixture):
    df = pd.read_parquet(copy_etl_fixture / "model_ready.parquet")
    df.loc[df.index[0], "neighborhood_normalized"] = ""
    df.to_parquet(copy_etl_fixture / "model_ready.parquet", index=False)
    _refresh_hashes(copy_etl_fixture)
    with pytest.raises(TrainingInputError, match="neighborhood_normalized"):
        load_training_input(copy_etl_fixture)


def test_neighborhood_numeric_rejected(copy_etl_fixture):
    df = pd.read_parquet(copy_etl_fixture / "model_ready.parquet").copy()
    df["neighborhood_normalized"] = [42] * len(df)
    df.to_parquet(copy_etl_fixture / "model_ready.parquet", index=False)
    _refresh_hashes(copy_etl_fixture)
    with pytest.raises(TrainingInputError, match="neighborhood_normalized"):
        load_training_input(copy_etl_fixture)


def test_bedrooms_infinite_rejected(copy_etl_fixture):
    df = pd.read_parquet(copy_etl_fixture / "model_ready.parquet")
    df["bedrooms"] = df["bedrooms"].astype(float)
    df.loc[df.index[0], "bedrooms"] = float("inf")
    df.to_parquet(copy_etl_fixture / "model_ready.parquet", index=False)
    _refresh_hashes(copy_etl_fixture)
    with pytest.raises(TrainingInputError, match="finite"):
        load_training_input(copy_etl_fixture)


def test_bathrooms_infinite_rejected(copy_etl_fixture):
    df = pd.read_parquet(copy_etl_fixture / "model_ready.parquet")
    df["bathrooms"] = df["bathrooms"].astype(float)
    df.loc[df.index[0], "bathrooms"] = float("inf")
    df.to_parquet(copy_etl_fixture / "model_ready.parquet", index=False)
    _refresh_hashes(copy_etl_fixture)
    with pytest.raises(TrainingInputError, match="finite"):
        load_training_input(copy_etl_fixture)


def test_bathrooms_negative_rejected(copy_etl_fixture):
    df = pd.read_parquet(copy_etl_fixture / "model_ready.parquet")
    df["bathrooms"] = df["bathrooms"].astype(float)
    df.loc[df.index[0], "bathrooms"] = -1.0
    df.to_parquet(copy_etl_fixture / "model_ready.parquet", index=False)
    _refresh_hashes(copy_etl_fixture)
    with pytest.raises(TrainingInputError, match="non-negative"):
        load_training_input(copy_etl_fixture)


def test_bathrooms_null_is_accepted(model_etl_run_dir):
    inp = load_training_input(model_etl_run_dir)
    # The fixture already has null bathrooms; loader must accept them.
    assert inp.model_ready["bathrooms"].isnull().any()


def test_missing_bathrooms_column_is_accepted(copy_etl_fixture, isolated_output_dir):
    def _drop(df):
        return df.drop(columns=["bathrooms"])

    _mutate_bathrooms(copy_etl_fixture, _drop)
    inp = load_training_input(copy_etl_fixture)
    assert "bathrooms" in inp.model_ready.columns  # injected internally
    # And training runs end-to-end:
    result = pipeline_run(_base_config(copy_etl_fixture, isolated_output_dir))
    assert result.status == "completed"


def test_pytorch_uses_median_for_bathrooms_impute(temporal_split_fixture):
    vocabs = build_torch_vocabularies(temporal_split_fixture.train)
    train_bathrooms = pd.to_numeric(
        temporal_split_fixture.train["bathrooms"], errors="coerce"
    ).astype(float)
    expected_median = float(train_bathrooms.dropna().median())
    assert abs(vocabs.numeric_impute_values["bathrooms"] - expected_median) < 1e-9
    # And it must not equal the mean unless the data is uniform.
    assert vocabs.numeric_impute_values["bathrooms"] != pytest.approx(
        float(train_bathrooms.mean()), abs=1e-9
    ) or expected_median == pytest.approx(float(train_bathrooms.mean()))


def test_input_contract_does_not_mutate_source_frame(copy_etl_fixture):
    original = pd.read_parquet(copy_etl_fixture / "model_ready.parquet")
    load_training_input(copy_etl_fixture)
    reread = pd.read_parquet(copy_etl_fixture / "model_ready.parquet")
    pd.testing.assert_frame_equal(original, reread)


# ==== B6 — predictions include train + residual sign ===============


def test_predictions_has_all_three_splits_for_every_model(model_etl_run_dir, isolated_output_dir):
    result = pipeline_run(_base_config(model_etl_run_dir, isolated_output_dir))
    df = pd.read_parquet(result.output_dir / "predictions.parquet")
    for model_name in ("baseline", "linear", "lightgbm"):
        for split_name in ("train", "validation", "test"):
            subset = df[(df["model_name"] == model_name) & (df["split"] == split_name)]
            assert not subset.empty, f"missing rows for {model_name}/{split_name}"


def test_predictions_row_count_matches_split(model_etl_run_dir, isolated_output_dir):
    result = pipeline_run(_base_config(model_etl_run_dir, isolated_output_dir))
    manifest = json.loads((result.output_dir / "split_manifest.json").read_text(encoding="utf-8"))
    df = pd.read_parquet(result.output_dir / "predictions.parquet")
    rows = manifest["row_counts"]
    model_count = df["model_name"].nunique()
    expected = (rows["train"] + rows["validation"] + rows["test"]) * model_count
    assert len(df) == expected


def test_train_and_validation_use_tuning_model(model_etl_run_dir, isolated_output_dir):
    result = pipeline_run(_base_config(model_etl_run_dir, isolated_output_dir))
    df = pd.read_parquet(result.output_dir / "predictions.parquet")
    train_val = df[df["split"].isin(["train", "validation"])]
    assert set(train_val["model_stage"].unique()) == {"tuning_model"}


def test_test_split_uses_final_refit(model_etl_run_dir, isolated_output_dir):
    result = pipeline_run(_base_config(model_etl_run_dir, isolated_output_dir))
    df = pd.read_parquet(result.output_dir / "predictions.parquet")
    test = df[df["split"] == "test"]
    assert set(test["model_stage"].unique()) == {"final_refit"}


def test_residual_is_actual_minus_predicted(model_etl_run_dir, isolated_output_dir):
    result = pipeline_run(_base_config(model_etl_run_dir, isolated_output_dir))
    df = pd.read_parquet(result.output_dir / "predictions.parquet")
    formula = df["actual_price_usd"] - df["predicted_price_usd"]
    assert np.allclose(df["residual"].astype(float), formula.astype(float), atol=1e-9)


def test_absolute_error_is_abs_residual(model_etl_run_dir, isolated_output_dir):
    result = pipeline_run(_base_config(model_etl_run_dir, isolated_output_dir))
    df = pd.read_parquet(result.output_dir / "predictions.parquet")
    assert np.allclose(df["absolute_error_usd"], df["residual"].abs(), atol=1e-9)


def test_percentage_error_is_non_negative(model_etl_run_dir, isolated_output_dir):
    result = pipeline_run(_base_config(model_etl_run_dir, isolated_output_dir))
    df = pd.read_parquet(result.output_dir / "predictions.parquet")
    assert (df["percentage_error"].dropna() >= 0).all()


def test_predictions_have_no_nan_or_inf(model_etl_run_dir, isolated_output_dir):
    result = pipeline_run(_base_config(model_etl_run_dir, isolated_output_dir))
    df = pd.read_parquet(result.output_dir / "predictions.parquet")
    for column in ("actual_price_usd", "predicted_price_usd", "residual", "absolute_error_usd"):
        assert not df[column].isnull().any()
        assert np.isfinite(df[column].astype(float)).all()


def test_worst_errors_uses_test_final_refit_only(model_etl_run_dir, isolated_output_dir):
    result = pipeline_run(_base_config(model_etl_run_dir, isolated_output_dir))
    top = pd.read_csv(result.output_dir / "worst_errors.csv")
    assert (top["split"] == "test").all()
    assert (top["model_stage"] == "final_refit").all()
    assert (top["model_name"] == result.serving_candidate).all()
    diffs = top["absolute_error_usd"].diff().dropna()
    assert (diffs <= 0).all()  # descending


def test_residual_interval_uses_validation_tuning_model(model_etl_run_dir, isolated_output_dir):
    result = pipeline_run(_base_config(model_etl_run_dir, isolated_output_dir))
    interval = json.loads(
        (result.output_dir / "serving_bundle" / "residual_interval.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = json.loads((result.output_dir / "split_manifest.json").read_text(encoding="utf-8"))
    assert interval["validation_rows"] == manifest["row_counts"]["validation"]


# ---- helpers --------------------------------------------------------


def _rewrite_checksums(bundle: Path) -> None:
    """Recompute checksums.json so a metadata mutation stays integrity-clean."""
    checks = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in bundle.iterdir()
        if p.is_file() and p.name != "checksums.json"
    }
    (bundle / "checksums.json").write_text(
        json.dumps(checks, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
