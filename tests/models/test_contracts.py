"""Tests for the ETL input contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from alquileres_uy.models.contracts import (
    TrainingInputError,
    check_training_leakage,
    load_training_input,
)


def _rehash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _refresh_hashes(root: Path) -> None:
    lineage = json.loads((root / "lineage.json").read_text(encoding="utf-8"))
    lineage["output_sha256"]["model_ready"] = _rehash(root / "model_ready.parquet")
    lineage["output_sha256"]["etl_summary"] = _rehash(root / "etl_summary.json")
    lineage["output_sha256"]["schema"] = _rehash(root / "schema.json")
    (root / "lineage.json").write_text(
        json.dumps(lineage, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def test_valid_fixture_loads(model_etl_run_dir):
    inp = load_training_input(model_etl_run_dir)
    assert inp.data_mode == "fixture"
    assert inp.schema_version == "1.0.0"
    assert not inp.model_ready.empty


def test_missing_etl_dir_is_rejected(tmp_path):
    with pytest.raises(TrainingInputError, match="etl run directory"):
        load_training_input(tmp_path / "nope")


def test_missing_file_is_rejected(copy_etl_fixture):
    (copy_etl_fixture / "model_ready.parquet").unlink()
    with pytest.raises(TrainingInputError, match="model_ready"):
        load_training_input(copy_etl_fixture)


def test_summary_status_not_completed(copy_etl_fixture):
    summary = json.loads((copy_etl_fixture / "etl_summary.json").read_text(encoding="utf-8"))
    summary["status"] = "in-progress"
    (copy_etl_fixture / "etl_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    _refresh_hashes(copy_etl_fixture)
    with pytest.raises(TrainingInputError, match="completed"):
        load_training_input(copy_etl_fixture)


def test_summary_data_mode_invalid(copy_etl_fixture):
    summary = json.loads((copy_etl_fixture / "etl_summary.json").read_text(encoding="utf-8"))
    summary["data_mode"] = "staging"
    (copy_etl_fixture / "etl_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    _refresh_hashes(copy_etl_fixture)
    with pytest.raises(TrainingInputError, match="data_mode"):
        load_training_input(copy_etl_fixture)


def test_summary_schema_version_unsupported(copy_etl_fixture):
    summary = json.loads((copy_etl_fixture / "etl_summary.json").read_text(encoding="utf-8"))
    summary["schema_version"] = "9.9.9"
    (copy_etl_fixture / "etl_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    _refresh_hashes(copy_etl_fixture)
    with pytest.raises(TrainingInputError, match="schema_version"):
        load_training_input(copy_etl_fixture)


def test_summary_naive_timestamp_rejected(copy_etl_fixture):
    summary = json.loads((copy_etl_fixture / "etl_summary.json").read_text(encoding="utf-8"))
    summary["started_at"] = "2026-01-01T00:00:00"
    (copy_etl_fixture / "etl_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    _refresh_hashes(copy_etl_fixture)
    with pytest.raises(TrainingInputError, match="timezone"):
        load_training_input(copy_etl_fixture)


def test_summary_negative_counts_rejected(copy_etl_fixture):
    summary = json.loads((copy_etl_fixture / "etl_summary.json").read_text(encoding="utf-8"))
    summary["input_items"] = -5
    (copy_etl_fixture / "etl_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    _refresh_hashes(copy_etl_fixture)
    with pytest.raises(TrainingInputError, match="input_items"):
        load_training_input(copy_etl_fixture)


def test_lineage_hash_mismatch(copy_etl_fixture):
    lineage = json.loads((copy_etl_fixture / "lineage.json").read_text(encoding="utf-8"))
    lineage["output_sha256"]["model_ready"] = "0" * 64
    (copy_etl_fixture / "lineage.json").write_text(json.dumps(lineage), encoding="utf-8")
    with pytest.raises(TrainingInputError, match="model_ready"):
        load_training_input(copy_etl_fixture)


def test_lineage_etl_run_id_mismatch(copy_etl_fixture):
    lineage = json.loads((copy_etl_fixture / "lineage.json").read_text(encoding="utf-8"))
    lineage["etl_run_id"] = "different"
    (copy_etl_fixture / "lineage.json").write_text(json.dumps(lineage), encoding="utf-8")
    with pytest.raises(TrainingInputError, match="etl_run_id"):
        load_training_input(copy_etl_fixture)


def test_lineage_data_mode_mismatch(copy_etl_fixture):
    lineage = json.loads((copy_etl_fixture / "lineage.json").read_text(encoding="utf-8"))
    lineage["data_mode"] = "real"
    (copy_etl_fixture / "lineage.json").write_text(json.dumps(lineage), encoding="utf-8")
    with pytest.raises(TrainingInputError, match="data_mode"):
        load_training_input(copy_etl_fixture)


def test_lineage_output_path_traversal(copy_etl_fixture):
    lineage = json.loads((copy_etl_fixture / "lineage.json").read_text(encoding="utf-8"))
    lineage["output_files"]["extra"] = "../secret.json"
    (copy_etl_fixture / "lineage.json").write_text(json.dumps(lineage), encoding="utf-8")
    with pytest.raises(TrainingInputError, match="escape"):
        load_training_input(copy_etl_fixture)


def test_schema_missing_required_column(copy_etl_fixture):
    schema = json.loads((copy_etl_fixture / "schema.json").read_text(encoding="utf-8"))
    schema["model_ready_required"] = [c for c in schema["model_ready_required"] if c != "bedrooms"]
    (copy_etl_fixture / "schema.json").write_text(json.dumps(schema), encoding="utf-8")
    _refresh_hashes(copy_etl_fixture)
    with pytest.raises(TrainingInputError, match="bedrooms"):
        load_training_input(copy_etl_fixture)


def test_model_ready_missing_column(copy_etl_fixture):
    df = pd.read_parquet(copy_etl_fixture / "model_ready.parquet").drop(columns=["bedrooms"])
    df.to_parquet(copy_etl_fixture / "model_ready.parquet", index=False)
    _refresh_hashes(copy_etl_fixture)
    with pytest.raises(TrainingInputError, match="bedrooms"):
        load_training_input(copy_etl_fixture)


def test_model_ready_forbidden_column(copy_etl_fixture):
    df = pd.read_parquet(copy_etl_fixture / "model_ready.parquet")
    df["price_per_m2"] = df["price_usd"] / df["total_area_m2"]
    df.to_parquet(copy_etl_fixture / "model_ready.parquet", index=False)
    _refresh_hashes(copy_etl_fixture)
    with pytest.raises(TrainingInputError, match="forbidden"):
        load_training_input(copy_etl_fixture)


def test_model_ready_null_target(copy_etl_fixture):
    df = pd.read_parquet(copy_etl_fixture / "model_ready.parquet")
    df.loc[df.index[0], "price_usd"] = None
    df.to_parquet(copy_etl_fixture / "model_ready.parquet", index=False)
    _refresh_hashes(copy_etl_fixture)
    with pytest.raises(TrainingInputError, match="price_usd"):
        load_training_input(copy_etl_fixture)


def test_model_ready_non_positive_target(copy_etl_fixture):
    df = pd.read_parquet(copy_etl_fixture / "model_ready.parquet")
    df.loc[df.index[0], "price_usd"] = 0.0
    df.to_parquet(copy_etl_fixture / "model_ready.parquet", index=False)
    _refresh_hashes(copy_etl_fixture)
    with pytest.raises(TrainingInputError, match="greater than zero"):
        load_training_input(copy_etl_fixture)


def test_model_ready_non_positive_area(copy_etl_fixture):
    df = pd.read_parquet(copy_etl_fixture / "model_ready.parquet")
    df.loc[df.index[0], "total_area_m2"] = -1.0
    df.to_parquet(copy_etl_fixture / "model_ready.parquet", index=False)
    _refresh_hashes(copy_etl_fixture)
    with pytest.raises(TrainingInputError, match="total_area_m2"):
        load_training_input(copy_etl_fixture)


def test_model_ready_duplicate_source_id(copy_etl_fixture):
    df = pd.read_parquet(copy_etl_fixture / "model_ready.parquet")
    df.loc[df.index[-1], "source_item_id"] = df.loc[df.index[0], "source_item_id"]
    df.to_parquet(copy_etl_fixture / "model_ready.parquet", index=False)
    _refresh_hashes(copy_etl_fixture)
    with pytest.raises(TrainingInputError, match="source_item_id"):
        load_training_input(copy_etl_fixture)


def test_model_ready_invalid_property_type(copy_etl_fixture):
    df = pd.read_parquet(copy_etl_fixture / "model_ready.parquet")
    df.loc[df.index[0], "property_type"] = "warehouse"
    df.to_parquet(copy_etl_fixture / "model_ready.parquet", index=False)
    _refresh_hashes(copy_etl_fixture)
    with pytest.raises(TrainingInputError, match="property_type"):
        load_training_input(copy_etl_fixture)


def test_check_training_leakage_rejects_target():
    from alquileres_uy.models.config import FEATURE_COLUMNS

    with pytest.raises(TrainingInputError, match="forbidden"):
        check_training_leakage([*FEATURE_COLUMNS, "price_usd"])


def test_check_training_leakage_rejects_ppm2():
    with pytest.raises(TrainingInputError, match="forbidden"):
        check_training_leakage(["bedrooms", "price_per_m2"])


def test_check_training_leakage_rejects_source_id():
    with pytest.raises(TrainingInputError, match="forbidden"):
        check_training_leakage(["bedrooms", "source_item_id"])


def test_check_training_leakage_accepts_declared_features():
    from alquileres_uy.models.config import FEATURE_COLUMNS

    check_training_leakage(FEATURE_COLUMNS)  # must not raise
