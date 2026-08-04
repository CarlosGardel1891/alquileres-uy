import hashlib
import json
from pathlib import Path

import pytest

from alquileres_uy.etl.contracts import RawRunValidationError, load_raw_run


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_summary(root: Path):
    (root / "ingestion_summary.json").write_text(json.dumps({"run_id": "r1"}), encoding="utf-8")


def _write_item_batch(root: Path) -> Path:
    (root / "items").mkdir(exist_ok=True)
    batch = root / "items" / "batch_0001.json"
    batch.write_text(json.dumps([{"code": 200, "body": {"id": "MLU_TEST_1"}}]), encoding="utf-8")
    return batch


def _write_manifest(
    root: Path,
    *,
    include_batch: bool = True,
    files: list[dict] | None = None,
    **overrides,
):
    """Write a manifest with valid timestamps + files entries.

    ``include_batch`` also writes ``items/batch_0001.json`` and populates
    ``files`` accordingly. Overrides win over defaults.
    """
    if include_batch:
        batch = _write_item_batch(root)
        if files is None:
            files = [
                {
                    "path": "items/batch_0001.json",
                    "kind": "item_batch",
                    "sha256": _sha256(batch),
                }
            ]
    base = {
        "run_id": "r1",
        "source": "mercadolibre",
        "status": "completed",
        "started_at": "2026-08-04T22:00:00Z",
        "finished_at": "2026-08-04T22:15:00Z",
        "files": files or [],
    }
    base.update(overrides)
    (root / "manifest.json").write_text(json.dumps(base), encoding="utf-8")


def test_load_valid_run(tmp_path):
    _write_manifest(tmp_path)
    _write_summary(tmp_path)
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
    with pytest.raises(RawRunValidationError, match="summary"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_invalid_json_raises(tmp_path):
    _write_item_batch(tmp_path)
    (tmp_path / "manifest.json").write_text("not json", encoding="utf-8")
    _write_summary(tmp_path)
    with pytest.raises(RawRunValidationError, match="valid JSON"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_wrong_source_raises(tmp_path):
    _write_manifest(tmp_path, source="other")
    _write_summary(tmp_path)
    with pytest.raises(RawRunValidationError, match="source"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_status_not_completed_raises(tmp_path):
    _write_manifest(tmp_path, status="failed")
    _write_summary(tmp_path)
    with pytest.raises(RawRunValidationError, match="status"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_no_items_dir_raises(tmp_path):
    _write_manifest(tmp_path, include_batch=False)
    _write_summary(tmp_path)
    with pytest.raises(RawRunValidationError, match="files"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_real_mode_rejects_fixture_dir(tmp_path):
    _write_manifest(tmp_path)
    _write_summary(tmp_path)
    with pytest.raises(RawRunValidationError, match="fixture"):
        load_raw_run(tmp_path, data_mode="real", fixtures_root=tmp_path)


def test_fixture_mode_rejects_non_fixture_dir(tmp_path):
    _write_manifest(tmp_path)
    _write_summary(tmp_path)
    other = tmp_path / "outside"
    with pytest.raises(RawRunValidationError, match="fixture"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=other)
