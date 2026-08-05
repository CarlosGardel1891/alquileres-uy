"""Final ETL summary invariants: exact path and mandatory timestamps.

These tests pin down two contract rules that were previously permissive:

* ``manifest.summary_path`` is compared against ``manifest.files`` by
  full logical POSIX path, not by basename. Anything that differs
  (``./``, subdir, another folder with the same basename, absolute
  paths) is rejected.
* ``summary.started_at`` and ``summary.finished_at`` are required and
  must match the manifest's timestamps once both sides are converted
  to UTC.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from alquileres_uy.etl.contracts import RawRunValidationError, load_raw_run


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_summary(root: Path, name: str = "ingestion_summary.json", **overrides) -> Path:
    body = {
        "run_id": "r1",
        "status": "completed",
        "started_at": "2026-08-04T22:00:00Z",
        "finished_at": "2026-08-04T22:15:00Z",
        "items_downloaded": 1,
        "descriptions_downloaded": 0,
    }
    body.update(overrides)
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def _write_batch(root: Path) -> Path:
    (root / "items").mkdir(exist_ok=True)
    batch = root / "items" / "batch_0001.json"
    batch.write_text(json.dumps([{"code": 200, "body": {"id": "MLU_TEST_1"}}]), encoding="utf-8")
    return batch


def _write_manifest(
    root: Path,
    *,
    summary_path: str = "ingestion_summary.json",
    extra_files: list[dict] | None = None,
    started_at: str = "2026-08-04T22:00:00Z",
    finished_at: str = "2026-08-04T22:15:00Z",
) -> None:
    batch = root / "items" / "batch_0001.json"
    summary_root = root / "ingestion_summary.json"
    files = [{"path": "items/batch_0001.json", "kind": "item_batch", "sha256": _sha(batch)}]
    if summary_root.is_file():
        files.append(
            {"path": "ingestion_summary.json", "kind": "report", "sha256": _sha(summary_root)}
        )
    if extra_files:
        files.extend(extra_files)
    manifest = {
        "run_id": "r1",
        "source": "mercadolibre",
        "status": "completed",
        "started_at": started_at,
        "finished_at": finished_at,
        "files": files,
        "summary_path": summary_path,
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


# ---- Correction 1: exact summary_path comparison -----------------------


def test_root_summary_path_matches_root_entry(tmp_path):
    _write_batch(tmp_path)
    _write_summary(tmp_path)
    _write_manifest(tmp_path, summary_path="ingestion_summary.json")
    run = load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)
    assert run.summary_path.name == "ingestion_summary.json"


def test_subdir_summary_path_does_not_match_root_entry(tmp_path):
    _write_batch(tmp_path)
    _write_summary(tmp_path)
    _write_manifest(tmp_path, summary_path="subdir/ingestion_summary.json")
    with pytest.raises(RawRunValidationError, match="subdir/ingestion_summary.json"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_root_summary_path_does_not_match_subdir_entry(tmp_path):
    _write_batch(tmp_path)
    _write_summary(tmp_path)
    # Move summary declaration to a subdirectory (same basename) — the
    # manifest still points to root, so the exact-path lookup fails.
    other_report = tmp_path / "reports" / "ingestion_summary.json"
    other_report.parent.mkdir(exist_ok=True)
    other_report.write_text(json.dumps({"note": "extra"}), encoding="utf-8")
    _write_manifest(
        tmp_path,
        summary_path="ingestion_summary.json",
        extra_files=[
            {
                "path": "reports/ingestion_summary.json",
                "kind": "report",
                "sha256": _sha(other_report),
            },
        ],
    )
    # The root summary IS declared and DOES match, so this actually passes.
    # Then flip: remove the root declaration and keep only the subdir one.
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"] = [
        entry for entry in manifest["files"] if entry["path"] != "ingestion_summary.json"
    ]
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RawRunValidationError, match="ingestion_summary.json"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_leading_dot_slash_is_rejected(tmp_path):
    _write_batch(tmp_path)
    _write_summary(tmp_path)
    _write_manifest(tmp_path, summary_path="./ingestion_summary.json")
    with pytest.raises(RawRunValidationError, match="manifest.summary_path"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_dotdot_summary_path_is_rejected(tmp_path):
    _write_batch(tmp_path)
    _write_summary(tmp_path)
    _write_manifest(tmp_path, summary_path="../ingestion_summary.json")
    with pytest.raises(RawRunValidationError, match="escape"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_posix_absolute_summary_path_is_rejected(tmp_path):
    _write_batch(tmp_path)
    _write_summary(tmp_path)
    _write_manifest(tmp_path, summary_path="/var/data/ingestion_summary.json")
    with pytest.raises(RawRunValidationError, match="relative POSIX"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_windows_absolute_summary_path_is_rejected(tmp_path):
    _write_batch(tmp_path)
    _write_summary(tmp_path)
    _write_manifest(tmp_path, summary_path="C:\\temp\\ingestion_summary.json")
    with pytest.raises(RawRunValidationError, match="relative POSIX"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_another_report_with_same_basename_does_not_produce_spurious_match(tmp_path):
    """Root summary is picked by exact path; a same-basename subdir doesn't shadow it."""
    _write_batch(tmp_path)
    _write_summary(tmp_path)
    other = tmp_path / "reports" / "ingestion_summary.json"
    other.parent.mkdir(exist_ok=True)
    other.write_text(json.dumps({"note": "other"}), encoding="utf-8")
    _write_manifest(
        tmp_path,
        summary_path="ingestion_summary.json",
        extra_files=[
            {"path": "reports/ingestion_summary.json", "kind": "report", "sha256": _sha(other)},
        ],
    )
    run = load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)
    assert run.summary_path == tmp_path.resolve() / "ingestion_summary.json"
    reports = [entry for entry in run.declared_files if entry.kind == "report"]
    assert {e.path for e in reports} == {"ingestion_summary.json", "reports/ingestion_summary.json"}


def test_summary_path_error_names_the_offending_value(tmp_path):
    _write_batch(tmp_path)
    _write_summary(tmp_path)
    _write_manifest(tmp_path, summary_path="subdir/ingestion_summary.json")
    with pytest.raises(RawRunValidationError) as info:
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)
    message = str(info.value)
    assert "subdir/ingestion_summary.json" in message


# ---- Correction 2: mandatory summary timestamps ------------------------


def _build_summary_missing(root: Path, drop: str) -> None:
    body = {
        "run_id": "r1",
        "status": "completed",
        "started_at": "2026-08-04T22:00:00Z",
        "finished_at": "2026-08-04T22:15:00Z",
        "items_downloaded": 1,
        "descriptions_downloaded": 0,
    }
    body.pop(drop, None)
    (root / "ingestion_summary.json").write_text(json.dumps(body), encoding="utf-8")


def _build_summary_with(root: Path, key: str, value) -> None:
    body = {
        "run_id": "r1",
        "status": "completed",
        "started_at": "2026-08-04T22:00:00Z",
        "finished_at": "2026-08-04T22:15:00Z",
        "items_downloaded": 1,
        "descriptions_downloaded": 0,
    }
    body[key] = value
    (root / "ingestion_summary.json").write_text(json.dumps(body), encoding="utf-8")


def test_summary_missing_started_at_is_required(tmp_path):
    _write_batch(tmp_path)
    _build_summary_missing(tmp_path, "started_at")
    _write_manifest(tmp_path)
    with pytest.raises(RawRunValidationError, match="summary.started_at is required"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_summary_missing_finished_at_is_required(tmp_path):
    _write_batch(tmp_path)
    _build_summary_missing(tmp_path, "finished_at")
    _write_manifest(tmp_path)
    with pytest.raises(RawRunValidationError, match="summary.finished_at is required"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_summary_started_null_is_rejected(tmp_path):
    _write_batch(tmp_path)
    _build_summary_with(tmp_path, "started_at", None)
    _write_manifest(tmp_path)
    with pytest.raises(RawRunValidationError, match="summary.started_at is required"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_summary_finished_null_is_rejected(tmp_path):
    _write_batch(tmp_path)
    _build_summary_with(tmp_path, "finished_at", None)
    _write_manifest(tmp_path)
    with pytest.raises(RawRunValidationError, match="summary.finished_at is required"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_summary_started_empty_string_is_rejected(tmp_path):
    _write_batch(tmp_path)
    _build_summary_with(tmp_path, "started_at", "")
    _write_manifest(tmp_path)
    with pytest.raises(RawRunValidationError, match="summary.started_at is required"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_summary_finished_empty_string_is_rejected(tmp_path):
    _write_batch(tmp_path)
    _build_summary_with(tmp_path, "finished_at", "")
    _write_manifest(tmp_path)
    with pytest.raises(RawRunValidationError, match="summary.finished_at is required"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_summary_naive_timestamp_is_rejected(tmp_path):
    _write_batch(tmp_path)
    _build_summary_with(tmp_path, "started_at", "2026-08-04T22:00:00")
    _write_manifest(tmp_path)
    with pytest.raises(RawRunValidationError, match="timezone"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_summary_invalid_iso_is_rejected(tmp_path):
    _write_batch(tmp_path)
    _build_summary_with(tmp_path, "started_at", "fecha inválida")
    _write_manifest(tmp_path)
    with pytest.raises(RawRunValidationError, match="ISO-8601"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_summary_timestamp_mismatch_is_rejected(tmp_path):
    _write_batch(tmp_path)
    _build_summary_with(tmp_path, "started_at", "2027-01-01T00:00:00Z")
    _write_manifest(tmp_path)
    with pytest.raises(RawRunValidationError, match="summary.started_at"):
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)


def test_summary_equivalent_offset_is_accepted(tmp_path):
    _write_batch(tmp_path)
    # 22:00 UTC == 19:00 -03:00 → same instant, must be accepted.
    _build_summary_with(tmp_path, "started_at", "2026-08-04T19:00:00-03:00")
    # Also express finished_at with an offset for symmetry.
    body = json.loads((tmp_path / "ingestion_summary.json").read_text(encoding="utf-8"))
    body["finished_at"] = "2026-08-04T16:15:00-06:00"
    (tmp_path / "ingestion_summary.json").write_text(json.dumps(body), encoding="utf-8")
    _write_manifest(tmp_path)
    run = load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)
    assert run.started_at.isoformat() == "2026-08-04T22:00:00+00:00"


def test_summary_timestamp_error_names_the_field(tmp_path):
    _write_batch(tmp_path)
    _build_summary_with(tmp_path, "finished_at", "2027-01-01T00:00:00Z")
    _write_manifest(tmp_path)
    with pytest.raises(RawRunValidationError) as info:
        load_raw_run(tmp_path, data_mode="fixture", fixtures_root=tmp_path)
    message = str(info.value)
    assert "summary.finished_at" in message
    assert "2027-01-01T00:00:00Z" in message
