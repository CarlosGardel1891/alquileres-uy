"""CLI-level tests for ``scripts/run_ingestion.py``.

Loads the CLI module by file path (it lives outside the package) and
exercises its ``main`` function with fabricated approvals.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from alquileres_uy.ingest.approval import APPROVAL_FILENAME
from alquileres_uy.ingest.filesystem import atomic_write_json

CLI_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_ingestion.py"


def _load_cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_ingestion_cli", CLI_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_valid_approval(tmp_path: Path) -> Path:
    coverage_path, coverage_sha = atomic_write_json(tmp_path / "coverage.json", {"x": 1})
    approval = {
        "source": "mercadolibre",
        "site_id": "MLU",
        "decision": "APPROVED",
        "created_at": "2026-08-04T17:00:00Z",
        "category_ids": {"apartment": "MLU1743", "house": "MLU1466"},
        "available_filters": [],
        "operation_filter": {},
        "essential_coverage": {},
        "source_gate_report_path": coverage_path.name,
        "source_gate_report_sha256": coverage_sha,
    }
    approval_path, _ = atomic_write_json(tmp_path / APPROVAL_FILENAME, approval)
    return approval_path


def test_cli_requires_gate_approval_flag(tmp_path: Path, capsys) -> None:
    cli = _load_cli()
    with pytest.raises(SystemExit) as exc_info:
        cli.main([])
    assert exc_info.value.code == 2
    stderr = capsys.readouterr().err
    assert "gate-approval" in stderr


def test_cli_returns_2_when_approval_file_missing(tmp_path: Path) -> None:
    cli = _load_cli()
    exit_code = cli.main(
        [
            "--gate-approval",
            str(tmp_path / "does-not-exist.json"),
            "--output-dir",
            str(tmp_path / "raw"),
            "--database-path",
            str(tmp_path / "ingestion.sqlite"),
            "--dry-run",
        ]
    )
    assert exit_code == 2
    assert not (tmp_path / "raw").exists()
    assert not (tmp_path / "ingestion.sqlite").exists()


def test_cli_returns_2_when_approval_is_inconclusive(tmp_path: Path) -> None:
    approval_path = _write_valid_approval(tmp_path)
    body = json.loads(approval_path.read_text(encoding="utf-8"))
    body["decision"] = "INCONCLUSIVE"
    approval_path.unlink()
    approval_path.write_text(json.dumps(body), encoding="utf-8")

    cli = _load_cli()
    exit_code = cli.main(
        [
            "--gate-approval",
            str(approval_path),
            "--output-dir",
            str(tmp_path / "raw"),
            "--database-path",
            str(tmp_path / "ingestion.sqlite"),
            "--dry-run",
        ]
    )
    assert exit_code == 2
    assert not (tmp_path / "raw").exists()
    assert not (tmp_path / "ingestion.sqlite").exists()


def test_cli_returns_2_when_coverage_hash_mismatches(tmp_path: Path) -> None:
    approval_path = _write_valid_approval(tmp_path)
    # Tamper with the coverage file
    coverage = tmp_path / "coverage.json"
    coverage.write_bytes(coverage.read_bytes() + b"tampered")

    cli = _load_cli()
    exit_code = cli.main(
        [
            "--gate-approval",
            str(approval_path),
            "--output-dir",
            str(tmp_path / "raw"),
            "--database-path",
            str(tmp_path / "ingestion.sqlite"),
            "--dry-run",
        ]
    )
    assert exit_code == 2
    assert not (tmp_path / "raw").exists()
    assert not (tmp_path / "ingestion.sqlite").exists()


def test_cli_dry_run_succeeds_with_valid_approval(tmp_path: Path, capsys) -> None:
    approval_path = _write_valid_approval(tmp_path)
    cli = _load_cli()
    exit_code = cli.main(
        [
            "--gate-approval",
            str(approval_path),
            "--output-dir",
            str(tmp_path / "raw"),
            "--database-path",
            str(tmp_path / "ingestion.sqlite"),
            "--dry-run",
        ]
    )
    assert exit_code == 0
    stdout = capsys.readouterr().out
    plan = json.loads(stdout)
    assert plan["dry_run"] is True
    assert plan["seed_segment_count"] == 2
    assert not (tmp_path / "ingestion.sqlite").exists()
