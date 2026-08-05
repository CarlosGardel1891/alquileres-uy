import hashlib
import json
from pathlib import Path

import pytest

from alquileres_uy.etl.contracts import RawRunValidationError, load_raw_run


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_summary(root: Path):
    _write_summary_file(root)


def _write_item_batch(root: Path) -> Path:
    (root / "items").mkdir(exist_ok=True)
    batch = root / "items" / "batch_0001.json"
    batch.write_text(json.dumps([{"code": 200, "body": {"id": "MLU_TEST_1"}}]), encoding="utf-8")
    return batch


def _write_summary_file(root: Path, **overrides) -> Path:
    body = {
        "run_id": "r1",
        "status": "completed",
        "items_downloaded": 1,
        "descriptions_downloaded": 0,
    }
    body.update(overrides)
    path = root / "ingestion_summary.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def _write_manifest(
    root: Path,
    *,
    include_batch: bool = True,
    include_summary_entry: bool = True,
    files: list[dict] | None = None,
    **overrides,
):
    """Write a manifest that satisfies the loader contract.

    ``include_batch`` writes ``items/batch_0001.json``; when
    ``include_summary_entry`` is true, also declares
    ``ingestion_summary.json`` as ``kind=report`` with its real hash.
    """
    summary_path = root / "ingestion_summary.json"
    if not summary_path.is_file():
        _write_summary_file(root)
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
    else:
        files = files or []
    if include_summary_entry and summary_path.is_file():
        files = [
            *files,
            {
                "path": "ingestion_summary.json",
                "kind": "report",
                "sha256": _sha256(summary_path),
            },
        ]
    base = {
        "run_id": "r1",
        "source": "mercadolibre",
        "status": "completed",
        "started_at": "2026-08-04T22:00:00Z",
        "finished_at": "2026-08-04T22:15:00Z",
        "files": files,
        "summary_path": "ingestion_summary.json",
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
    _write_item_batch(tmp_path)
    _write_manifest(
        tmp_path,
        include_batch=False,
        include_summary_entry=False,
        files=[
            {
                "path": "items/batch_0001.json",
                "kind": "item_batch",
                "sha256": _sha256(tmp_path / "items" / "batch_0001.json"),
            },
        ],
    )
    (tmp_path / "ingestion_summary.json").unlink()
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
