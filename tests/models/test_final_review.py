"""Final review corrections.

Covers exact bundle set, bathrooms fallback, real-mode approval and
runtime mismatches. Grouped by section of the review prompt so each
blocker/evidence maps directly to a set of tests.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import joblib as _joblib
import numpy as np
import pandas as pd
import pytest

from alquileres_uy.models.baseline import refit_baseline, tune_baseline
from alquileres_uy.models.config import TrainingConfig
from alquileres_uy.models.contracts import load_training_input
from alquileres_uy.models.features import (
    build_preprocessor,
    build_torch_vocabularies,
    encode_torch_frame,
    feature_frame,
)
from alquileres_uy.models.imputation import (
    CONSTANT_FALLBACK,
    resolve_numeric_imputation_values,
)
from alquileres_uy.models.lightgbm_model import refit_lightgbm, tune_lightgbm
from alquileres_uy.models.linear import refit_linear, tune_linear
from alquileres_uy.models.pipeline import run as pipeline_run
from alquileres_uy.models.serving import (
    REQUIRED_BUNDLE_FILES,
    REQUIRED_BUNDLE_PAYLOAD_FILES,
    ServingBundleError,
    load_serving_bundle,
    validate_runtime_compatibility,
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


def _rewrite_checksums(bundle: Path) -> None:
    checks = {
        name: hashlib.sha256((bundle / name).read_bytes()).hexdigest()
        for name in sorted(REQUIRED_BUNDLE_PAYLOAD_FILES)
    }
    (bundle / "checksums.json").write_text(
        json.dumps(checks, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _make_fixture_bundle(model_etl_run_dir: Path, output_dir: Path) -> Path:
    result = pipeline_run(_base_config(model_etl_run_dir, output_dir))
    return result.output_dir / "serving_bundle"


def _promote_fixture_to_real(root: Path) -> None:
    summary = json.loads((root / "etl_summary.json").read_text(encoding="utf-8"))
    summary["data_mode"] = "real"
    (root / "etl_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    lineage = json.loads((root / "lineage.json").read_text(encoding="utf-8"))
    lineage["data_mode"] = "real"
    (root / "lineage.json").write_text(
        json.dumps(lineage, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _refresh_hashes(root)


def _drop_bathrooms(root: Path) -> None:
    df = pd.read_parquet(root / "model_ready.parquet").drop(columns=["bathrooms"])
    df.to_parquet(root / "model_ready.parquet", index=False)
    _refresh_hashes(root)


# ==== B1 — exact bundle set + deployability consistency =============


def test_bundle_contains_exactly_five_files(model_etl_run_dir, isolated_output_dir):
    bundle = _make_fixture_bundle(model_etl_run_dir, isolated_output_dir)
    names = {p.name for p in bundle.iterdir()}
    assert names == set(REQUIRED_BUNDLE_FILES)


def test_checksums_declares_exactly_four_payloads(model_etl_run_dir, isolated_output_dir):
    bundle = _make_fixture_bundle(model_etl_run_dir, isolated_output_dir)
    declared = json.loads((bundle / "checksums.json").read_text(encoding="utf-8"))
    assert set(declared.keys()) == set(REQUIRED_BUNDLE_PAYLOAD_FILES)


@pytest.mark.parametrize("payload", sorted(REQUIRED_BUNDLE_PAYLOAD_FILES))
def test_missing_checksum_entry_is_rejected(
    payload, model_etl_run_dir, isolated_output_dir, monkeypatch
):
    bundle = _make_fixture_bundle(model_etl_run_dir, isolated_output_dir)
    declared = json.loads((bundle / "checksums.json").read_text(encoding="utf-8"))
    declared.pop(payload)
    (bundle / "checksums.json").write_text(json.dumps(declared), encoding="utf-8")

    calls: list = []
    monkeypatch.setattr(_joblib, "load", lambda *a, **kw: calls.append(a))
    with pytest.raises(ServingBundleError, match="missing required entries"):
        load_serving_bundle(bundle, allow_fixture=True)
    assert calls == []


def test_extra_checksum_entry_is_rejected(model_etl_run_dir, isolated_output_dir, monkeypatch):
    bundle = _make_fixture_bundle(model_etl_run_dir, isolated_output_dir)
    declared = json.loads((bundle / "checksums.json").read_text(encoding="utf-8"))
    declared["debug.json"] = "0" * 64
    (bundle / "checksums.json").write_text(json.dumps(declared), encoding="utf-8")

    calls: list = []
    monkeypatch.setattr(_joblib, "load", lambda *a, **kw: calls.append(a))
    with pytest.raises(ServingBundleError, match="unexpected entries"):
        load_serving_bundle(bundle, allow_fixture=True)
    assert calls == []


def test_extra_physical_file_is_rejected(model_etl_run_dir, isolated_output_dir, monkeypatch):
    bundle = _make_fixture_bundle(model_etl_run_dir, isolated_output_dir)
    (bundle / "debug.json").write_text("{}", encoding="utf-8")
    calls: list = []
    monkeypatch.setattr(_joblib, "load", lambda *a, **kw: calls.append(a))
    with pytest.raises(ServingBundleError, match="undeclared files"):
        load_serving_bundle(bundle, allow_fixture=True)
    assert calls == []


def test_subdirectory_is_rejected(model_etl_run_dir, isolated_output_dir, monkeypatch):
    bundle = _make_fixture_bundle(model_etl_run_dir, isolated_output_dir)
    (bundle / "torch").mkdir()
    calls: list = []
    monkeypatch.setattr(_joblib, "load", lambda *a, **kw: calls.append(a))
    with pytest.raises(ServingBundleError, match="unexpected directory"):
        load_serving_bundle(bundle, allow_fixture=True)
    assert calls == []


def test_symlink_is_rejected(model_etl_run_dir, isolated_output_dir, monkeypatch, tmp_path):
    bundle = _make_fixture_bundle(model_etl_run_dir, isolated_output_dir)
    target = tmp_path / "external.txt"
    target.write_text("x", encoding="utf-8")
    try:
        (bundle / "shortcut").symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("filesystem does not support symlinks in this environment")
    calls: list = []
    monkeypatch.setattr(_joblib, "load", lambda *a, **kw: calls.append(a))
    with pytest.raises(ServingBundleError):
        load_serving_bundle(bundle, allow_fixture=True)
    assert calls == []


def test_checksums_declaring_itself_is_rejected(
    model_etl_run_dir, isolated_output_dir, monkeypatch
):
    bundle = _make_fixture_bundle(model_etl_run_dir, isolated_output_dir)
    declared = json.loads((bundle / "checksums.json").read_text(encoding="utf-8"))
    declared["checksums.json"] = "0" * 64
    (bundle / "checksums.json").write_text(json.dumps(declared), encoding="utf-8")
    calls: list = []
    monkeypatch.setattr(_joblib, "load", lambda *a, **kw: calls.append(a))
    with pytest.raises(ServingBundleError, match="itself|unexpected"):
        load_serving_bundle(bundle, allow_fixture=True)
    assert calls == []


def test_fixture_with_deployable_true_is_rejected(
    model_etl_run_dir, isolated_output_dir, monkeypatch
):
    bundle = _make_fixture_bundle(model_etl_run_dir, isolated_output_dir)
    metadata_path = bundle / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["deployable"] = True  # inconsistent with data_mode=fixture
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    _rewrite_checksums(bundle)
    calls: list = []
    monkeypatch.setattr(_joblib, "load", lambda *a, **kw: calls.append(a))
    with pytest.raises(ServingBundleError, match="inconsistent"):
        load_serving_bundle(bundle, allow_fixture=True)
    assert calls == []


def test_real_with_deployable_false_is_rejected(
    model_etl_run_dir, isolated_output_dir, monkeypatch
):
    bundle = _make_fixture_bundle(model_etl_run_dir, isolated_output_dir)
    metadata_path = bundle / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["data_mode"] = "real"
    metadata["deployable"] = False
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    _rewrite_checksums(bundle)
    calls: list = []
    monkeypatch.setattr(_joblib, "load", lambda *a, **kw: calls.append(a))
    with pytest.raises(ServingBundleError, match="inconsistent"):
        load_serving_bundle(bundle, allow_fixture=True)
    assert calls == []


@pytest.mark.parametrize("bad_value", ["false", 0, 1, None])
def test_deployable_must_be_bool(bad_value, model_etl_run_dir, isolated_output_dir, monkeypatch):
    bundle = _make_fixture_bundle(model_etl_run_dir, isolated_output_dir)
    metadata_path = bundle / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["deployable"] = bad_value
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    _rewrite_checksums(bundle)
    calls: list = []
    monkeypatch.setattr(_joblib, "load", lambda *a, **kw: calls.append(a))
    with pytest.raises(ServingBundleError, match="boolean"):
        load_serving_bundle(bundle, allow_fixture=True)
    assert calls == []


def test_unknown_data_mode_is_rejected(model_etl_run_dir, isolated_output_dir, monkeypatch):
    bundle = _make_fixture_bundle(model_etl_run_dir, isolated_output_dir)
    metadata_path = bundle / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["data_mode"] = "staging"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    _rewrite_checksums(bundle)
    calls: list = []
    monkeypatch.setattr(_joblib, "load", lambda *a, **kw: calls.append(a))
    with pytest.raises(ServingBundleError, match="data_mode"):
        load_serving_bundle(bundle, allow_fixture=True)
    assert calls == []


def test_valid_fixture_bundle_loads_with_allow_fixture(model_etl_run_dir, isolated_output_dir):
    bundle = _make_fixture_bundle(model_etl_run_dir, isolated_output_dir)
    loaded = load_serving_bundle(bundle, allow_fixture=True)
    assert loaded["metadata"]["deployable"] is False
    assert loaded["metadata"]["data_mode"] == "fixture"


# ==== B2 — bathrooms all-missing / absent ==========================


def test_resolve_impute_values_returns_median_when_observed():
    frame = pd.DataFrame(
        {"bedrooms": [1, 2, 3], "bathrooms": [1.0, 2.0, np.nan], "total_area_m2": [40, 50, 60]}
    )
    values, sources = resolve_numeric_imputation_values(frame)
    assert values["bathrooms"] == 1.5  # median of [1.0, 2.0]
    assert sources["bathrooms"] == "fit_frame_median"


def test_resolve_impute_values_falls_back_to_zero_when_all_null():
    frame = pd.DataFrame(
        {
            "bedrooms": [1, 2, 3],
            "bathrooms": [np.nan, np.nan, np.nan],
            "total_area_m2": [40, 50, 60],
        }
    )
    values, sources = resolve_numeric_imputation_values(frame)
    assert values["bathrooms"] == CONSTANT_FALLBACK
    assert sources["bathrooms"] == "constant_fallback_no_observed_values"


def test_resolve_impute_values_falls_back_when_column_missing():
    frame = pd.DataFrame({"bedrooms": [1, 2], "total_area_m2": [40, 50]})
    values, sources = resolve_numeric_imputation_values(frame)
    assert values["bathrooms"] == CONSTANT_FALLBACK
    assert sources["bathrooms"] == "constant_fallback_no_observed_values"


def test_classical_preprocessor_keeps_bathrooms_when_all_null(temporal_split_fixture):
    train = temporal_split_fixture.train.copy()
    train["bathrooms"] = pd.array([pd.NA] * len(train), dtype="Float64")
    features = feature_frame(train)
    preprocessor = build_preprocessor()
    preprocessor.fit(features)
    transformed = preprocessor.transform(features)
    # bathrooms occupies index 0 of the numeric branch after
    # StandardScaler with keep_empty_features=True: mean=0, std handled
    # by sklearn; every value must remain finite.
    assert np.isfinite(transformed).all()


def test_torch_vocabularies_use_fallback_when_all_bathrooms_null(temporal_split_fixture):
    train = temporal_split_fixture.train.copy()
    train["bathrooms"] = pd.array([pd.NA] * len(train), dtype="Float64")
    vocabs = build_torch_vocabularies(train)
    assert vocabs.numeric_impute_values["bathrooms"] == CONSTANT_FALLBACK
    assert vocabs.imputation_sources["bathrooms"] == "constant_fallback_no_observed_values"
    assert vocabs.numeric_mean["bathrooms"] == 0.0
    assert vocabs.numeric_std["bathrooms"] == 1.0


def test_torch_encoder_uses_fallback_when_column_missing(temporal_split_fixture):
    train = temporal_split_fixture.train.copy()
    train["bathrooms"] = pd.array([pd.NA] * len(train), dtype="Float64")
    vocabs = build_torch_vocabularies(train)
    frame = temporal_split_fixture.test.drop(columns=["bathrooms"], errors="ignore")
    neigh, prop, num = encode_torch_frame(frame, vocabs)
    assert np.isfinite(num).all()
    assert neigh.shape[0] == len(frame)
    assert prop.shape[0] == len(frame)


def test_tune_and_refit_baseline_without_bathrooms(temporal_split_fixture):
    train = temporal_split_fixture.train.drop(columns=["bathrooms"], errors="ignore")
    combined = pd.concat(
        [train, temporal_split_fixture.validation.drop(columns=["bathrooms"], errors="ignore")],
        ignore_index=True,
    )
    tune_baseline(train, data_mode="fixture", input_hashes={})
    refit_baseline(combined, data_mode="fixture", input_hashes={})


def test_tune_and_refit_ridge_without_bathrooms(temporal_split_fixture):
    train = temporal_split_fixture.train.copy()
    validation = temporal_split_fixture.validation.copy()
    train["bathrooms"] = pd.array([pd.NA] * len(train), dtype="Float64")
    validation["bathrooms"] = pd.array([pd.NA] * len(validation), dtype="Float64")
    tuning = tune_linear(train, validation, target_column="price_usd", alphas=(0.1, 1.0, 10.0))
    combined = pd.concat([train, validation], ignore_index=True)
    final = refit_linear(combined, target_column="price_usd", tuning_model=tuning)
    assert np.isfinite(final.predict(validation)).all()


def test_tune_and_refit_lightgbm_without_bathrooms(temporal_split_fixture):
    train = temporal_split_fixture.train.copy()
    validation = temporal_split_fixture.validation.copy()
    train["bathrooms"] = pd.array([pd.NA] * len(train), dtype="Float64")
    validation["bathrooms"] = pd.array([pd.NA] * len(validation), dtype="Float64")
    tuning = tune_lightgbm(train, validation, target_column="price_usd", seed=42)
    combined = pd.concat([train, validation], ignore_index=True)
    final = refit_lightgbm(combined, target_column="price_usd", seed=42, tuning_model=tuning)
    assert np.isfinite(final.predict(validation)).all()


def test_classical_pipeline_completes_without_bathrooms(copy_etl_fixture, isolated_output_dir):
    _drop_bathrooms(copy_etl_fixture)
    result = pipeline_run(_base_config(copy_etl_fixture, isolated_output_dir))
    assert result.status == "completed"
    predictions = pd.read_parquet(result.output_dir / "predictions.parquet")
    for column in ("predicted_price_usd", "residual", "absolute_error_usd"):
        assert not predictions[column].isnull().any()


@pytest.mark.torch
def test_full_pipeline_with_torch_completes_without_bathrooms(
    copy_etl_fixture, isolated_output_dir
):
    _drop_bathrooms(copy_etl_fixture)
    result = pipeline_run(_base_config(copy_etl_fixture, isolated_output_dir, include_torch=True))
    assert result.status == "completed"
    scaler = json.loads(
        (result.output_dir / "models" / "torch" / "numeric_scaler.json").read_text(encoding="utf-8")
    )
    assert scaler["impute_values"]["bathrooms"] == 0.0
    assert scaler["imputation_sources"]["bathrooms"] == "constant_fallback_no_observed_values"
    predictions = pd.read_parquet(result.output_dir / "predictions.parquet")
    for column in ("predicted_price_usd", "residual", "absolute_error_usd"):
        assert not predictions[column].isnull().any()


def test_loader_does_not_mutate_original_parquet(copy_etl_fixture):
    original = pd.read_parquet(copy_etl_fixture / "model_ready.parquet")
    load_training_input(copy_etl_fixture)
    reread = pd.read_parquet(copy_etl_fixture / "model_ready.parquet")
    pd.testing.assert_frame_equal(original, reread)


# ==== E3 — test perturbation with torch ============================


@pytest.mark.torch
def test_changing_test_targets_does_not_affect_any_tuning_result_with_torch(
    model_etl_run_dir, isolated_output_dir, tmp_path
):
    original = pipeline_run(
        _base_config(model_etl_run_dir, isolated_output_dir, include_torch=True)
    )
    orig_metrics = json.loads((original.output_dir / "metrics.json").read_text(encoding="utf-8"))
    orig_selection = json.loads(
        (original.output_dir / "model_selection.json").read_text(encoding="utf-8")
    )
    orig_residual = json.loads(
        (original.output_dir / "serving_bundle" / "residual_interval.json").read_text(
            encoding="utf-8"
        )
    )
    orig_split = json.loads(
        (original.output_dir / "split_manifest.json").read_text(encoding="utf-8")
    )
    orig_torch_history = json.loads(
        (original.output_dir / "models" / "torch" / "training_history.json").read_text(
            encoding="utf-8"
        )
    )
    orig_lgbm = _joblib.load(original.output_dir / "models" / "lightgbm.joblib")["metadata"]
    orig_linear = _joblib.load(original.output_dir / "models" / "linear.joblib")["metadata"]

    # Identify real test source_item_ids via the split hashes are not
    # enough — read the predictions file which carries them explicitly.
    predictions = pd.read_parquet(original.output_dir / "predictions.parquet")
    test_ids = set(predictions.loc[predictions["split"] == "test", "source_item_id"].astype(str))
    assert test_ids, "test split must not be empty"

    perturbed_dir = tmp_path / "etl_perturbed_torch"
    shutil.copytree(model_etl_run_dir, perturbed_dir)
    df = pd.read_parquet(perturbed_dir / "model_ready.parquet")
    mask = df["source_item_id"].astype(str).isin(test_ids)
    df.loc[mask, "price_usd"] = df.loc[mask, "price_usd"] * 3.0
    df.to_parquet(perturbed_dir / "model_ready.parquet", index=False)
    _refresh_hashes(perturbed_dir)

    other_out = tmp_path / "out2"
    other_out.mkdir()
    perturbed = pipeline_run(_base_config(perturbed_dir, other_out, include_torch=True))
    new_metrics = json.loads((perturbed.output_dir / "metrics.json").read_text(encoding="utf-8"))
    new_selection = json.loads(
        (perturbed.output_dir / "model_selection.json").read_text(encoding="utf-8")
    )
    new_residual = json.loads(
        (perturbed.output_dir / "serving_bundle" / "residual_interval.json").read_text(
            encoding="utf-8"
        )
    )
    new_split = json.loads(
        (perturbed.output_dir / "split_manifest.json").read_text(encoding="utf-8")
    )
    new_torch_history = json.loads(
        (perturbed.output_dir / "models" / "torch" / "training_history.json").read_text(
            encoding="utf-8"
        )
    )
    new_lgbm = _joblib.load(perturbed.output_dir / "models" / "lightgbm.joblib")["metadata"]
    new_linear = _joblib.load(perturbed.output_dir / "models" / "linear.joblib")["metadata"]

    # Split boundaries are unchanged (dates were not touched).
    assert orig_split["id_hashes"] == new_split["id_hashes"]
    # Validation metrics for every model — identical.
    for name in ("baseline", "linear", "lightgbm", "torch"):
        assert (
            abs(
                orig_metrics["models"][name]["validation"]["mae_usd"]
                - new_metrics["models"][name]["validation"]["mae_usd"]
            )
            < 1e-6
        )
    assert orig_selection["best_overall_model"] == new_selection["best_overall_model"]
    assert orig_selection["serving_candidate"] == new_selection["serving_candidate"]
    assert orig_selection["practical_tie_models"] == new_selection["practical_tie_models"]
    assert orig_residual["values"] == new_residual["values"]
    # Torch best_epoch driven by validation — unchanged.
    assert orig_torch_history["best_epoch"] == new_torch_history["best_epoch"]
    # LightGBM tuning artefacts unchanged.
    assert orig_lgbm["hyperparameters"] == new_lgbm["hyperparameters"]
    assert orig_lgbm["best_iteration"] == new_lgbm["best_iteration"]
    assert orig_linear["alpha"] == new_linear["alpha"]
    # Test metrics must change for at least one model.
    changed = [
        name
        for name in ("baseline", "linear", "lightgbm", "torch")
        if abs(
            orig_metrics["models"][name]["test"]["mae_usd"]
            - new_metrics["models"][name]["test"]["mae_usd"]
        )
        > 1e-6
    ]
    assert len(changed) >= 2, f"only these test metrics changed: {changed}"


# ==== E4 — real-mode ephemeral approval hash =======================


def test_real_mode_lineage_contains_exact_approval_hash(
    model_etl_run_dir, isolated_output_dir, tmp_path
):
    """TEST-ONLY SYNTHETIC REAL-MODE CONTRACT RUN — NOT PRODUCTION VALIDATION."""
    etl_copy = tmp_path / "etl_real"
    shutil.copytree(model_etl_run_dir, etl_copy)
    _promote_fixture_to_real(etl_copy)
    training_input = load_training_input(etl_copy)

    approval_payload = {
        "status": "ETL_PRODUCTION_VALIDATED",
        "data_mode": "real",
        "etl_run_id": training_input.etl_run_id,
        "etl_summary_sha256": training_input.input_hashes["etl_summary"],
        "lineage_sha256": training_input.input_hashes["lineage"],
        "model_ready_sha256": training_input.input_hashes["model_ready"],
        "approved_at": datetime.now(tz=UTC).isoformat(),
        "approved_by": "test-suite",
    }
    approval_path = tmp_path / "etl_production_approval.json"
    approval_path.write_text(json.dumps(approval_payload), encoding="utf-8")
    approval_hash = hashlib.sha256(approval_path.read_bytes()).hexdigest()

    result = pipeline_run(
        _base_config(
            etl_copy,
            isolated_output_dir,
            fixture_mode=False,
            etl_approval_path=approval_path,
        )
    )
    lineage = json.loads((result.output_dir / "training_lineage.json").read_text(encoding="utf-8"))
    assert lineage["data_mode"] == "real"
    assert lineage["inputs_sha256"]["etl_approval"] == approval_hash
    assert len(lineage["inputs_sha256"]["etl_approval"]) == 64
    int(lineage["inputs_sha256"]["etl_approval"], 16)  # hex

    # serving metadata must carry deployable=true and the same
    # training_run_id / etl_run_id.
    metadata = json.loads(
        (result.output_dir / "serving_bundle" / "metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["deployable"] is True
    assert metadata["data_mode"] == "real"
    assert metadata["training_run_id"] == result.training_run_id
    assert metadata["etl_run_id"] == training_input.etl_run_id

    # Approval content itself must not leak into the lineage.
    lineage_text = (result.output_dir / "training_lineage.json").read_text(encoding="utf-8")
    assert "test-suite" not in lineage_text
    assert str(approval_path) not in lineage_text


def test_real_mode_lineage_breaks_when_approval_mutates_after_run(
    model_etl_run_dir, isolated_output_dir, tmp_path
):
    etl_copy = tmp_path / "etl_real_mutate"
    shutil.copytree(model_etl_run_dir, etl_copy)
    _promote_fixture_to_real(etl_copy)
    training_input = load_training_input(etl_copy)
    approval_payload = {
        "status": "ETL_PRODUCTION_VALIDATED",
        "data_mode": "real",
        "etl_run_id": training_input.etl_run_id,
        "etl_summary_sha256": training_input.input_hashes["etl_summary"],
        "lineage_sha256": training_input.input_hashes["lineage"],
        "model_ready_sha256": training_input.input_hashes["model_ready"],
        "approved_at": datetime.now(tz=UTC).isoformat(),
        "approved_by": "test-suite",
    }
    approval_path = tmp_path / "etl_production_approval.json"
    approval_path.write_text(json.dumps(approval_payload), encoding="utf-8")

    result = pipeline_run(
        _base_config(
            etl_copy,
            isolated_output_dir,
            fixture_mode=False,
            etl_approval_path=approval_path,
        )
    )
    lineage = json.loads((result.output_dir / "training_lineage.json").read_text(encoding="utf-8"))
    original_hash = lineage["inputs_sha256"]["etl_approval"]

    # Mutate after the run — recomputing sha256 must disagree with lineage.
    approval_payload["approved_by"] = "someone-else"
    approval_path.write_text(json.dumps(approval_payload), encoding="utf-8")
    new_hash = hashlib.sha256(approval_path.read_bytes()).hexdigest()
    assert new_hash != original_hash


# ==== E5 — runtime version mismatches ==============================


def _full_versions(model_type: str = "baseline", **overrides) -> dict:
    import sklearn as _sklearn

    payload = {
        "python": ".".join(map(str, sys.version_info[:2])),
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


@pytest.mark.parametrize(
    "version_key, error_hint",
    [
        ("numpy", "numpy"),
        ("pandas", "pandas"),
        ("scikit_learn", "scikit_learn"),
        ("joblib", "joblib"),
    ],
)
def test_load_bundle_rejects_runtime_mismatch(
    version_key,
    error_hint,
    model_etl_run_dir,
    isolated_output_dir,
    monkeypatch,
):
    bundle = _make_fixture_bundle(model_etl_run_dir, isolated_output_dir)
    metadata_path = bundle / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["versions"][version_key] = "99.0"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    _rewrite_checksums(bundle)
    calls: list = []
    monkeypatch.setattr(_joblib, "load", lambda *a, **kw: calls.append(a))
    with pytest.raises(ServingBundleError, match=error_hint):
        load_serving_bundle(bundle, allow_fixture=True)
    assert calls == []


def test_lightgbm_bundle_missing_lightgbm_version_is_rejected_before_load():
    metadata = {
        "bundle_version": "1.0.0",
        "model_type": "lightgbm",
        "data_mode": "fixture",
        "deployable": False,
        "versions": _full_versions(model_type="baseline"),  # lacks lightgbm
    }
    with pytest.raises(ServingBundleError, match="lightgbm"):
        validate_runtime_compatibility(metadata)


def test_lightgbm_bundle_version_mismatch_is_rejected_before_load(tmp_path, monkeypatch):
    # Build a minimal bundle-like tree so load_serving_bundle exercises
    # the LightGBM branch of validate_runtime_compatibility. Metadata
    # + checksums live in tmp; joblib.load is monkey-patched.
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "model.joblib").write_bytes(b"stub")
    (bundle / "feature_schema.json").write_text("{}", encoding="utf-8")
    (bundle / "residual_interval.json").write_text("{}", encoding="utf-8")
    metadata = {
        "bundle_version": "1.0.0",
        "model_type": "lightgbm",
        "data_mode": "fixture",
        "deployable": False,
        "model_artifact_sha256": hashlib.sha256(b"stub").hexdigest(),
        "versions": _full_versions(model_type="lightgbm", lightgbm="99.0"),
    }
    (bundle / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    _rewrite_checksums(bundle)

    calls: list = []
    monkeypatch.setattr(_joblib, "load", lambda *a, **kw: calls.append(a))
    with pytest.raises(ServingBundleError, match="lightgbm"):
        load_serving_bundle(bundle, allow_fixture=True)
    assert calls == []


def test_lightgbm_bundle_without_runtime_dependency_is_rejected_before_load(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "model.joblib").write_bytes(b"stub")
    (bundle / "feature_schema.json").write_text("{}", encoding="utf-8")
    (bundle / "residual_interval.json").write_text("{}", encoding="utf-8")
    metadata = {
        "bundle_version": "1.0.0",
        "model_type": "lightgbm",
        "data_mode": "fixture",
        "deployable": False,
        "model_artifact_sha256": hashlib.sha256(b"stub").hexdigest(),
        "versions": _full_versions(model_type="lightgbm"),
    }
    (bundle / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    _rewrite_checksums(bundle)

    # Force the lightgbm import inside validate_runtime_compatibility to fail.
    real_import = (
        __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__
    )

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "lightgbm":
            raise ImportError("simulated: lightgbm missing")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", _fake_import)
    calls: list = []
    monkeypatch.setattr(_joblib, "load", lambda *a, **kw: calls.append(a))
    with pytest.raises(ServingBundleError, match="lightgbm"):
        load_serving_bundle(bundle, allow_fixture=True)
    assert calls == []
