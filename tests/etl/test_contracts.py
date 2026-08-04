import json
from pathlib import Path

import pytest

from alquileres_uy.etl.contracts import RawRunValidationError, load_raw_run


def _write_manifest(root: Path, **overrides):
    base = {"run_id": "r1", "source": "mercadolibre", "status": "completed"}
    base.update(overrides)
    (root / "manifest.json").write_text(json.dumps(base), encoding="utf-8")


def _write_summary(root: Path):
    (root / "ingestion_summary.json").write_text(json.dumps({"run_id": "r1"}), encoding="utf-8")


def _write_item_batch(root: Path):
    (root / "items").mkdir(exist_ok=True)
    (root / "items" / "batch_0001.json").write_text(
        json.dumps([{"code": 200, "body": {"id": "MLU_TEST_1"}}]), encoding="utf-8"
    )


def test_load_valid_run(tmp_path):
    _write_manifest(tmp_path)
    _write_summary(tmp_path)
    _write_item_batch(tmp_path)
    run = load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)
    assert run.source == "mercadolibre"
    assert run.status == "completed"
    assert len(run.item_batch_paths) == 1


def test_missing_manifest_raises(tmp_path):
    _write_summary(tmp_path)
    _write_item_batch(tmp_path)
    with pytest.raises(RawRunValidationError, match="manifest"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_missing_summary_raises(tmp_path):
    _write_manifest(tmp_path)
    _write_item_batch(tmp_path)
    with pytest.raises(RawRunValidationError, match="summary"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_invalid_json_raises(tmp_path):
    (tmp_path / "manifest.json").write_text("not json", encoding="utf-8")
    _write_summary(tmp_path)
    _write_item_batch(tmp_path)
    with pytest.raises(RawRunValidationError, match="valid JSON"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_wrong_source_raises(tmp_path):
    _write_manifest(tmp_path, source="other")
    _write_summary(tmp_path)
    _write_item_batch(tmp_path)
    with pytest.raises(RawRunValidationError, match="source"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_status_not_completed_raises(tmp_path):
    _write_manifest(tmp_path, status="failed")
    _write_summary(tmp_path)
    _write_item_batch(tmp_path)
    with pytest.raises(RawRunValidationError, match="status"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_no_items_dir_raises(tmp_path):
    _write_manifest(tmp_path)
    _write_summary(tmp_path)
    with pytest.raises(RawRunValidationError, match="items"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_real_mode_rejects_fixture_dir(tmp_path):
    _write_manifest(tmp_path)
    _write_summary(tmp_path)
    _write_item_batch(tmp_path)
    with pytest.raises(RawRunValidationError, match="fixture"):
        load_raw_run(tmp_path, data_mode="real", fixtures_root=tmp_path)


def test_fixture_mode_rejects_non_fixture_dir(tmp_path):
    _write_manifest(tmp_path)
    _write_summary(tmp_path)
    _write_item_batch(tmp_path)
    other = tmp_path / "outside"
    with pytest.raises(RawRunValidationError, match="fixture"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=other)
