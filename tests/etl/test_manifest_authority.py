"""Tests for the manifest-as-authoritative-inventory contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from alquileres_uy.etl.contracts import RawRunValidationError, load_raw_run


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_batch(root: Path, name: str = "batch_0001.json") -> Path:
    (root / "items").mkdir(exist_ok=True)
    p = root / "items" / name
    p.write_text(json.dumps([{"code": 200, "body": {"id": "MLU_TEST_1"}}]), encoding="utf-8")
    return p


def _write_description(root: Path, name: str = "MLU_TEST_1.json") -> Path:
    (root / "descriptions").mkdir(exist_ok=True)
    p = root / "descriptions" / name
    p.write_text(json.dumps({"plain_text": "x"}), encoding="utf-8")
    return p


def _write_pair(root: Path, *, files: list[dict] | None = None, **overrides):
    (root / "ingestion_summary.json").write_text(json.dumps({"run_id": "r1"}), encoding="utf-8")
    base = {
        "run_id": "r1",
        "source": "mercadolibre",
        "status": "completed",
        "started_at": "2026-08-04T22:00:00Z",
        "finished_at": "2026-08-04T22:15:00Z",
        "files": files if files is not None else [],
    }
    base.update(overrides)
    (root / "manifest.json").write_text(json.dumps(base), encoding="utf-8")


def test_manifest_governs_batches(tmp_path):
    batch = _write_batch(tmp_path)
    _write_pair(
        tmp_path,
        files=[{"path": "items/batch_0001.json", "kind": "item_batch", "sha256": _sha(batch)}],
    )
    run = load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)
    assert len(run.item_batch_paths) == 1


def test_manifest_governs_descriptions(tmp_path):
    batch = _write_batch(tmp_path)
    desc = _write_description(tmp_path)
    _write_pair(
        tmp_path,
        files=[
            {"path": "items/batch_0001.json", "kind": "item_batch", "sha256": _sha(batch)},
            {"path": "descriptions/MLU_TEST_1.json", "kind": "description", "sha256": _sha(desc)},
        ],
    )
    run = load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)
    assert len(run.description_paths) == 1


def test_empty_files_is_rejected(tmp_path):
    _write_batch(tmp_path)
    _write_pair(tmp_path, files=[])
    with pytest.raises(RawRunValidationError, match="files"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_absolute_path_is_rejected(tmp_path):
    batch = _write_batch(tmp_path)
    _write_pair(
        tmp_path,
        files=[{"path": "/etc/passwd", "kind": "item_batch", "sha256": _sha(batch)}],
    )
    # /etc/passwd is only rooted on POSIX; either way, the loader must
    # refuse to open it — either as an escape or as a missing file.
    with pytest.raises(RawRunValidationError):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_dotdot_path_is_rejected(tmp_path):
    batch = _write_batch(tmp_path)
    _write_pair(
        tmp_path,
        files=[{"path": "../secret.json", "kind": "item_batch", "sha256": _sha(batch)}],
    )
    with pytest.raises(RawRunValidationError, match="escape"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_duplicate_path_is_rejected(tmp_path):
    batch = _write_batch(tmp_path)
    _write_pair(
        tmp_path,
        files=[
            {"path": "items/batch_0001.json", "kind": "item_batch", "sha256": _sha(batch)},
            {"path": "items/batch_0001.json", "kind": "item_batch", "sha256": _sha(batch)},
        ],
    )
    with pytest.raises(RawRunValidationError, match="twice"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_missing_file_reference_is_rejected(tmp_path):
    _write_pair(
        tmp_path,
        files=[
            {"path": "items/missing.json", "kind": "item_batch", "sha256": "0" * 64},
        ],
    )
    with pytest.raises(RawRunValidationError, match="missing file"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_wrong_hash_is_rejected(tmp_path):
    _write_batch(tmp_path)
    _write_pair(
        tmp_path,
        files=[{"path": "items/batch_0001.json", "kind": "item_batch", "sha256": "0" * 64}],
    )
    with pytest.raises(RawRunValidationError, match="sha256 mismatch"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_item_batch_outside_items_dir_is_rejected(tmp_path):
    batch = tmp_path / "elsewhere.json"
    batch.write_text(json.dumps([{"code": 200, "body": {"id": "MLU_TEST_1"}}]), encoding="utf-8")
    _write_pair(
        tmp_path,
        files=[{"path": "elsewhere.json", "kind": "item_batch", "sha256": _sha(batch)}],
    )
    with pytest.raises(RawRunValidationError, match="items/"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_undeclared_extra_batch_is_rejected(tmp_path):
    batch = _write_batch(tmp_path)
    # Extra file NOT declared in manifest:
    extra = tmp_path / "items" / "batch_0002.json"
    extra.write_text(json.dumps([]), encoding="utf-8")
    _write_pair(
        tmp_path,
        files=[{"path": "items/batch_0001.json", "kind": "item_batch", "sha256": _sha(batch)}],
    )
    with pytest.raises(RawRunValidationError, match="not declared"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_undeclared_extra_description_is_rejected(tmp_path):
    batch = _write_batch(tmp_path)
    _write_description(tmp_path)  # not declared
    _write_pair(
        tmp_path,
        files=[{"path": "items/batch_0001.json", "kind": "item_batch", "sha256": _sha(batch)}],
    )
    with pytest.raises(RawRunValidationError, match="not declared"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_unknown_kind_is_rejected(tmp_path):
    batch = _write_batch(tmp_path)
    _write_pair(
        tmp_path,
        files=[{"path": "items/batch_0001.json", "kind": "weird_kind", "sha256": _sha(batch)}],
    )
    with pytest.raises(RawRunValidationError, match="unknown kind"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_summary_run_id_mismatch_is_rejected(tmp_path):
    batch = _write_batch(tmp_path)
    (tmp_path / "ingestion_summary.json").write_text(
        json.dumps({"run_id": "OTHER"}), encoding="utf-8"
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "r1",
                "source": "mercadolibre",
                "status": "completed",
                "started_at": "2026-08-04T22:00:00Z",
                "finished_at": "2026-08-04T22:15:00Z",
                "files": [
                    {"path": "items/batch_0001.json", "kind": "item_batch", "sha256": _sha(batch)}
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RawRunValidationError, match="run_id"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_shipped_fixture_passes(etl_fixture_run):
    fixtures_root = etl_fixture_run.parents[2]
    run = load_raw_run(etl_fixture_run, data_mode="fixture", fixtures_root=fixtures_root)
    assert len(run.item_batch_paths) == 2
    assert len(run.description_paths) == 3
