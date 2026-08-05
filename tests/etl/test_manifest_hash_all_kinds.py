"""Every kind in manifest.files must validate its SHA-256, not just batches."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from alquileres_uy.etl.contracts import RawRunValidationError, load_raw_run


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _base_run(tmp_path: Path, extra_files: list[dict]) -> Path:
    (tmp_path / "items").mkdir(exist_ok=True)
    batch = tmp_path / "items" / "batch_0001.json"
    batch.write_text(json.dumps([{"code": 200, "body": {"id": "MLU_TEST_1"}}]), encoding="utf-8")
    summary = tmp_path / "ingestion_summary.json"
    summary.write_text(
        json.dumps(
            {
                "run_id": "r1",
                "status": "completed",
                "items_downloaded": 1,
                "descriptions_downloaded": 0,
            }
        ),
        encoding="utf-8",
    )
    files = [
        {"path": "items/batch_0001.json", "kind": "item_batch", "sha256": _sha(batch)},
        {"path": "ingestion_summary.json", "kind": "report", "sha256": _sha(summary)},
        *extra_files,
    ]
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "r1",
                "source": "mercadolibre",
                "status": "completed",
                "started_at": "2026-08-04T22:00:00Z",
                "finished_at": "2026-08-04T22:15:00Z",
                "files": files,
                "summary_path": "ingestion_summary.json",
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_correct_search_page_hash_passes(tmp_path):
    search_page = tmp_path / "search_page_0001.json"
    search_page.write_text(json.dumps({"results": []}), encoding="utf-8")
    _base_run(
        tmp_path,
        [{"path": "search_page_0001.json", "kind": "search_page", "sha256": _sha(search_page)}],
    )
    run = load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)
    assert run.declared_files
    assert any(entry.kind == "search_page" for entry in run.declared_files)


def test_wrong_search_page_hash_is_rejected(tmp_path):
    search_page = tmp_path / "search_page_0001.json"
    search_page.write_text(json.dumps({"results": []}), encoding="utf-8")
    _base_run(
        tmp_path,
        [{"path": "search_page_0001.json", "kind": "search_page", "sha256": "0" * 64}],
    )
    with pytest.raises(RawRunValidationError, match="sha256 mismatch"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_correct_error_log_hash_passes(tmp_path):
    log = tmp_path / "errors.jsonl"
    log.write_text('{"error":"x"}\n{"error":"y"}\n', encoding="utf-8")
    _base_run(
        tmp_path,
        [{"path": "errors.jsonl", "kind": "error_log", "sha256": _sha(log)}],
    )
    run = load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)
    assert any(entry.kind == "error_log" for entry in run.declared_files)


def test_wrong_error_log_hash_is_rejected(tmp_path):
    log = tmp_path / "errors.jsonl"
    log.write_text('{"error":"x"}\n', encoding="utf-8")
    _base_run(
        tmp_path,
        [{"path": "errors.jsonl", "kind": "error_log", "sha256": "0" * 64}],
    )
    with pytest.raises(RawRunValidationError, match="sha256 mismatch"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_report_hash_is_validated_for_arbitrary_report(tmp_path):
    extra_report = tmp_path / "extra_report.json"
    extra_report.write_text(json.dumps({"count": 5}), encoding="utf-8")
    _base_run(
        tmp_path,
        [{"path": "extra_report.json", "kind": "report", "sha256": _sha(extra_report)}],
    )
    run = load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)
    reports = [entry for entry in run.declared_files if entry.kind == "report"]
    assert len(reports) == 2  # summary + extra_report


def test_wrong_report_hash_is_rejected(tmp_path):
    extra_report = tmp_path / "extra_report.json"
    extra_report.write_text(json.dumps({"count": 5}), encoding="utf-8")
    _base_run(
        tmp_path,
        [{"path": "extra_report.json", "kind": "report", "sha256": "0" * 64}],
    )
    with pytest.raises(RawRunValidationError, match="sha256 mismatch"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_sha_with_wrong_length_is_rejected(tmp_path):
    log = tmp_path / "errors.jsonl"
    log.write_text('{"error":"x"}\n', encoding="utf-8")
    _base_run(
        tmp_path,
        [{"path": "errors.jsonl", "kind": "error_log", "sha256": "abc"}],
    )
    with pytest.raises(RawRunValidationError, match="64 hex"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_sha_with_non_hex_is_rejected(tmp_path):
    log = tmp_path / "errors.jsonl"
    log.write_text('{"error":"x"}\n', encoding="utf-8")
    _base_run(
        tmp_path,
        [
            {
                "path": "errors.jsonl",
                "kind": "error_log",
                "sha256": "z" * 64,
            }
        ],
    )
    with pytest.raises(RawRunValidationError, match="non-hex"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_sha_in_uppercase_still_matches(tmp_path):
    log = tmp_path / "errors.jsonl"
    log.write_text('{"error":"x"}\n', encoding="utf-8")
    _base_run(
        tmp_path,
        [
            {
                "path": "errors.jsonl",
                "kind": "error_log",
                "sha256": _sha(log).upper(),
            }
        ],
    )
    run = load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)
    assert any(entry.kind == "error_log" for entry in run.declared_files)
