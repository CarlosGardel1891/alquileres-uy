"""Semantic validation of ingestion_summary.json against the manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from alquileres_uy.etl.contracts import RawRunValidationError, load_raw_run


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_run(
    root: Path,
    *,
    envelopes: list[dict] | None = None,
    descriptions: list[str] | None = None,
    summary_overrides: dict | None = None,
    manifest_overrides: dict | None = None,
    include_summary_entry: bool = True,
) -> Path:
    envelopes = (
        envelopes if envelopes is not None else [{"code": 200, "body": {"id": "MLU_TEST_1"}}]
    )
    descriptions = descriptions or []
    (root / "items").mkdir(exist_ok=True)
    batch = root / "items" / "batch_0001.json"
    batch.write_text(json.dumps(envelopes), encoding="utf-8")
    description_files: list[Path] = []
    if descriptions:
        (root / "descriptions").mkdir(exist_ok=True)
        for item_id in descriptions:
            path = root / "descriptions" / f"{item_id}.json"
            path.write_text(json.dumps({"plain_text": item_id}), encoding="utf-8")
            description_files.append(path)

    summary_body = {
        "run_id": "r1",
        "status": "completed",
        "started_at": "2026-08-04T22:00:00Z",
        "finished_at": "2026-08-04T22:15:00Z",
        "items_downloaded": sum(
            1 for e in envelopes if e.get("code") == 200 and isinstance(e.get("body"), dict)
        ),
        "descriptions_downloaded": len(descriptions),
    }
    if summary_overrides:
        summary_body.update(summary_overrides)
    summary_path = root / "ingestion_summary.json"
    summary_path.write_text(json.dumps(summary_body), encoding="utf-8")

    files = [
        {"path": "items/batch_0001.json", "kind": "item_batch", "sha256": _sha(batch)},
    ]
    for path in description_files:
        files.append(
            {"path": f"descriptions/{path.name}", "kind": "description", "sha256": _sha(path)}
        )
    if include_summary_entry:
        files.append(
            {"path": "ingestion_summary.json", "kind": "report", "sha256": _sha(summary_path)}
        )

    manifest = {
        "run_id": "r1",
        "source": "mercadolibre",
        "status": "completed",
        "started_at": "2026-08-04T22:00:00Z",
        "finished_at": "2026-08-04T22:15:00Z",
        "files": files,
        "summary_path": "ingestion_summary.json",
    }
    if manifest_overrides:
        manifest.update(manifest_overrides)
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def test_valid_summary_passes(tmp_path):
    _write_run(tmp_path)
    load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_missing_run_id_is_rejected(tmp_path):
    _write_run(tmp_path, summary_overrides={"run_id": None})
    with pytest.raises(RawRunValidationError, match="summary.run_id"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_run_id_mismatch_is_rejected(tmp_path):
    _write_run(tmp_path, summary_overrides={"run_id": "OTHER"})
    with pytest.raises(RawRunValidationError, match="run_id"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_missing_status_is_rejected(tmp_path):
    _write_run(tmp_path, summary_overrides={"status": None})
    with pytest.raises(RawRunValidationError, match="summary.status"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_status_mismatch_is_rejected(tmp_path):
    _write_run(tmp_path, summary_overrides={"status": "failed"})
    with pytest.raises(RawRunValidationError, match="status"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_items_downloaded_missing_is_rejected(tmp_path):
    _write_run(tmp_path, summary_overrides={"items_downloaded": None})
    with pytest.raises(RawRunValidationError, match="items_downloaded"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_items_downloaded_non_int_is_rejected(tmp_path):
    _write_run(tmp_path, summary_overrides={"items_downloaded": "seven"})
    with pytest.raises(RawRunValidationError, match="items_downloaded"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_items_downloaded_mismatch_envelopes_is_rejected(tmp_path):
    envelopes = [
        {"code": 200, "body": {"id": "MLU_TEST_1"}},
        {"code": 200, "body": {"id": "MLU_TEST_2"}},
    ]
    _write_run(tmp_path, envelopes=envelopes, summary_overrides={"items_downloaded": 5})
    with pytest.raises(RawRunValidationError, match="items_downloaded"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_envelopes_404_and_500_do_not_count(tmp_path):
    envelopes = [
        {"code": 200, "body": {"id": "MLU_TEST_1"}},
        {"code": 404, "body": {"error": "not found"}},
        {"code": 500, "body": None},
    ]
    _write_run(
        tmp_path,
        envelopes=envelopes,
        summary_overrides={"items_downloaded": 1},
    )
    run = load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)
    assert run.run_id == "r1"


def test_descriptions_downloaded_missing_is_rejected(tmp_path):
    _write_run(tmp_path, summary_overrides={"descriptions_downloaded": None})
    with pytest.raises(RawRunValidationError, match="descriptions_downloaded"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_descriptions_downloaded_mismatch_is_rejected(tmp_path):
    _write_run(
        tmp_path,
        descriptions=["MLU_TEST_1", "MLU_TEST_2"],
        summary_overrides={"descriptions_downloaded": 5},
    )
    with pytest.raises(RawRunValidationError, match="descriptions_downloaded"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_summary_timestamp_mismatch_is_rejected(tmp_path):
    _write_run(
        tmp_path,
        summary_overrides={"started_at": "2026-09-01T00:00:00Z"},
    )
    with pytest.raises(RawRunValidationError, match="started_at"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_shipped_fixture_passes_all_checks(etl_fixture_run):
    fixtures_root = etl_fixture_run.parents[2]
    run = load_raw_run(etl_fixture_run, data_mode="fixture", fixtures_root=fixtures_root)
    assert run.declared_files
    assert any(entry.kind == "report" for entry in run.declared_files)


def test_error_message_names_the_inconsistent_field(tmp_path):
    envelopes = [
        {"code": 200, "body": {"id": "MLU_TEST_1"}},
        {"code": 200, "body": {"id": "MLU_TEST_2"}},
    ]
    _write_run(tmp_path, envelopes=envelopes, summary_overrides={"items_downloaded": 99})
    with pytest.raises(RawRunValidationError) as info:
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)
    message = str(info.value)
    assert "items_downloaded" in message
    assert "99" in message
    assert "2" in message


def test_missing_summary_path_declaration_is_rejected(tmp_path):
    _write_run(tmp_path, manifest_overrides={"summary_path": None})
    with pytest.raises(RawRunValidationError, match="summary_path"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_wrong_summary_path_target_is_rejected(tmp_path):
    _write_run(tmp_path, manifest_overrides={"summary_path": "other.json"})
    with pytest.raises(RawRunValidationError, match="ingestion_summary.json"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_summary_missing_from_files_is_rejected(tmp_path):
    _write_run(tmp_path, include_summary_entry=False)
    with pytest.raises(RawRunValidationError, match="ingestion_summary.json"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_summary_declared_with_wrong_kind_is_rejected(tmp_path):
    _write_run(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        if entry["path"] == "ingestion_summary.json":
            entry["kind"] = "item_batch"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RawRunValidationError):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)
