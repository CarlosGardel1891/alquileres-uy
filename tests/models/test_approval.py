"""Tests for the ETL production-approval gate."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from alquileres_uy.models.contracts import (
    TrainingInputError,
    load_etl_approval,
    load_training_input,
)


def _promote_to_real(root):
    summary = json.loads((root / "etl_summary.json").read_text(encoding="utf-8"))
    summary["data_mode"] = "real"
    (root / "etl_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    lineage = json.loads((root / "lineage.json").read_text(encoding="utf-8"))
    lineage["data_mode"] = "real"
    (root / "lineage.json").write_text(json.dumps(lineage), encoding="utf-8")
    _refresh_hashes(root)


def _refresh_hashes(root):
    import hashlib

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


def _valid_approval_payload(training_input) -> dict:
    return {
        "status": "ETL_PRODUCTION_VALIDATED",
        "data_mode": "real",
        "etl_run_id": training_input.etl_run_id,
        "etl_summary_sha256": training_input.input_hashes["etl_summary"],
        "lineage_sha256": training_input.input_hashes["lineage"],
        "model_ready_sha256": training_input.input_hashes["model_ready"],
        "approved_at": datetime.now(tz=UTC).isoformat(),
        "approved_by": "tl@example.com",
    }


def test_valid_approval_loads(copy_etl_fixture, tmp_path):
    _promote_to_real(copy_etl_fixture)
    training_input = load_training_input(copy_etl_fixture)
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(json.dumps(_valid_approval_payload(training_input)))
    approval = load_etl_approval(approval_path, training_input)
    assert approval.status == "ETL_PRODUCTION_VALIDATED"
    assert approval.data_mode == "real"


def test_approval_missing_file_rejected(training_input, tmp_path):
    with pytest.raises(TrainingInputError, match="not found"):
        load_etl_approval(tmp_path / "missing.json", training_input)


def test_approval_wrong_decision_rejected(copy_etl_fixture, tmp_path):
    _promote_to_real(copy_etl_fixture)
    training_input = load_training_input(copy_etl_fixture)
    payload = _valid_approval_payload(training_input)
    payload["status"] = "PROBABLY_OK"
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(json.dumps(payload))
    with pytest.raises(TrainingInputError, match="ETL_PRODUCTION_VALIDATED"):
        load_etl_approval(approval_path, training_input)


def test_approval_data_mode_wrong(copy_etl_fixture, tmp_path):
    _promote_to_real(copy_etl_fixture)
    training_input = load_training_input(copy_etl_fixture)
    payload = _valid_approval_payload(training_input)
    payload["data_mode"] = "fixture"
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(json.dumps(payload))
    with pytest.raises(TrainingInputError, match="data_mode"):
        load_etl_approval(approval_path, training_input)


def test_approval_run_id_mismatch(copy_etl_fixture, tmp_path):
    _promote_to_real(copy_etl_fixture)
    training_input = load_training_input(copy_etl_fixture)
    payload = _valid_approval_payload(training_input)
    payload["etl_run_id"] = "someone-else"
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(json.dumps(payload))
    with pytest.raises(TrainingInputError, match="etl_run_id"):
        load_etl_approval(approval_path, training_input)


def test_approval_summary_hash_mismatch(copy_etl_fixture, tmp_path):
    _promote_to_real(copy_etl_fixture)
    training_input = load_training_input(copy_etl_fixture)
    payload = _valid_approval_payload(training_input)
    payload["etl_summary_sha256"] = "0" * 64
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(json.dumps(payload))
    with pytest.raises(TrainingInputError, match="etl_summary_sha256"):
        load_etl_approval(approval_path, training_input)


def test_approval_lineage_hash_mismatch(copy_etl_fixture, tmp_path):
    _promote_to_real(copy_etl_fixture)
    training_input = load_training_input(copy_etl_fixture)
    payload = _valid_approval_payload(training_input)
    payload["lineage_sha256"] = "0" * 64
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(json.dumps(payload))
    with pytest.raises(TrainingInputError, match="lineage_sha256"):
        load_etl_approval(approval_path, training_input)


def test_approval_parquet_hash_mismatch(copy_etl_fixture, tmp_path):
    _promote_to_real(copy_etl_fixture)
    training_input = load_training_input(copy_etl_fixture)
    payload = _valid_approval_payload(training_input)
    payload["model_ready_sha256"] = "0" * 64
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(json.dumps(payload))
    with pytest.raises(TrainingInputError, match="model_ready_sha256"):
        load_etl_approval(approval_path, training_input)


def test_approval_naive_timestamp_rejected(copy_etl_fixture, tmp_path):
    _promote_to_real(copy_etl_fixture)
    training_input = load_training_input(copy_etl_fixture)
    payload = _valid_approval_payload(training_input)
    payload["approved_at"] = "2026-01-01T00:00:00"
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(json.dumps(payload))
    with pytest.raises(TrainingInputError, match="approved_at"):
        load_etl_approval(approval_path, training_input)


def test_approval_against_fixture_run_rejected(training_input, tmp_path):
    """A real approval must not be accepted against a fixture-mode ETL run."""
    payload = {
        "status": "ETL_PRODUCTION_VALIDATED",
        "data_mode": "real",
        "etl_run_id": training_input.etl_run_id,
        "etl_summary_sha256": training_input.input_hashes["etl_summary"],
        "lineage_sha256": training_input.input_hashes["lineage"],
        "model_ready_sha256": training_input.input_hashes["model_ready"],
        "approved_at": datetime.now(tz=UTC).isoformat(),
        "approved_by": "tl",
    }
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(json.dumps(payload))
    with pytest.raises(TrainingInputError, match="mix modes|data_mode"):
        load_etl_approval(approval_path, training_input)


def test_approval_bad_sha_length(copy_etl_fixture, tmp_path):
    _promote_to_real(copy_etl_fixture)
    training_input = load_training_input(copy_etl_fixture)
    payload = _valid_approval_payload(training_input)
    payload["etl_summary_sha256"] = "abc"
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(json.dumps(payload))
    with pytest.raises(TrainingInputError, match="64 hex"):
        load_etl_approval(approval_path, training_input)
