"""Every configuration error must return exit code 2, even during --dry-run."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_rate(path: Path, **overrides) -> Path:
    body = {
        "base_currency": "USD",
        "quote_currency": "UYU",
        "uyu_per_usd": 40.0,
        "effective_date": "2026-01-01",
        "source": "fixture",
        "retrieved_at": "2026-01-01T00:00:00Z",
        "data_mode": "fixture",
    }
    body.update(overrides)
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def _load_cli() -> ModuleType:
    cli_path = Path(__file__).resolve().parents[2] / "scripts" / "run_etl.py"
    spec = importlib.util.spec_from_file_location(f"_etl_cli_dryrun_{cli_path.stem}", cli_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_dry_run_exit_2_on_rate_mode_mismatch(tmp_path, etl_fixture_run):
    bad_rate = _write_rate(
        tmp_path / "r.json",
        data_mode="real",
        source="banco",
        retrieved_at="2026-08-04T10:00:00+00:00",
    )
    cli = _load_cli()
    exit_code = cli.main(
        [
            "--fixture-mode",
            "--dry-run",
            "--input-run-dir",
            str(etl_fixture_run),
            "--exchange-rate",
            str(bad_rate),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    assert exit_code == 2
    assert not (tmp_path / "out").exists()


def test_dry_run_exit_2_on_invalid_rate(tmp_path, etl_fixture_run):
    bad_rate = tmp_path / "bad.json"
    bad_rate.write_text(
        '{"base_currency":"USD","quote_currency":"UYU","uyu_per_usd":0,'
        '"effective_date":"2026-01-01","source":"x","data_mode":"fixture",'
        '"retrieved_at":"2026-01-01T00:00:00Z"}',
        encoding="utf-8",
    )
    cli = _load_cli()
    exit_code = cli.main(
        [
            "--fixture-mode",
            "--dry-run",
            "--input-run-dir",
            str(etl_fixture_run),
            "--exchange-rate",
            str(bad_rate),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    assert exit_code == 2


def test_dry_run_exit_2_on_manifest_invalid(tmp_path, exchange_rate_path):
    # Build a broken fixture-mode run under tests/fixtures/.
    root = Path(__file__).resolve().parents[1] / "fixtures" / f"etl_broken_{tmp_path.name}"
    root.mkdir(parents=True, exist_ok=True)
    (root / "items").mkdir(exist_ok=True)
    (root / "items" / "batch_0001.json").write_text(json.dumps([]), encoding="utf-8")
    (root / "ingestion_summary.json").write_text(json.dumps({}), encoding="utf-8")
    # manifest missing started_at
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "r1",
                "source": "mercadolibre",
                "status": "completed",
                "files": [],
                "summary_path": "ingestion_summary.json",
            }
        ),
        encoding="utf-8",
    )
    cli = _load_cli()
    exit_code = cli.main(
        [
            "--fixture-mode",
            "--dry-run",
            "--input-run-dir",
            str(root),
            "--exchange-rate",
            str(exchange_rate_path),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    assert exit_code == 2
    assert not (tmp_path / "out").exists()


def test_dry_run_exit_2_on_wrong_hash(tmp_path, exchange_rate_path):
    root = Path(__file__).resolve().parents[1] / "fixtures" / f"etl_wrong_hash_{tmp_path.name}"
    root.mkdir(parents=True, exist_ok=True)
    (root / "items").mkdir(exist_ok=True)
    batch = root / "items" / "batch_0001.json"
    batch.write_text(json.dumps([{"code": 200, "body": {"id": "MLU_TEST_1"}}]), encoding="utf-8")
    summary = root / "ingestion_summary.json"
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
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "r1",
                "source": "mercadolibre",
                "status": "completed",
                "started_at": "2026-08-04T22:00:00Z",
                "finished_at": "2026-08-04T22:15:00Z",
                "files": [
                    {"path": "items/batch_0001.json", "kind": "item_batch", "sha256": "0" * 64},
                    {"path": "ingestion_summary.json", "kind": "report", "sha256": _sha(summary)},
                ],
                "summary_path": "ingestion_summary.json",
            }
        ),
        encoding="utf-8",
    )
    cli = _load_cli()
    exit_code = cli.main(
        [
            "--fixture-mode",
            "--dry-run",
            "--input-run-dir",
            str(root),
            "--exchange-rate",
            str(exchange_rate_path),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    assert exit_code == 2


def test_dry_run_exit_2_on_invalid_aliases(tmp_path, etl_fixture_run, exchange_rate_path):
    bad_aliases = tmp_path / "bad_aliases.json"
    bad_aliases.write_text("not-a-json", encoding="utf-8")
    cli = _load_cli()
    exit_code = cli.main(
        [
            "--fixture-mode",
            "--dry-run",
            "--input-run-dir",
            str(etl_fixture_run),
            "--exchange-rate",
            str(exchange_rate_path),
            "--neighborhood-aliases",
            str(bad_aliases),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    assert exit_code == 2
    assert not (tmp_path / "out").exists()


def test_successful_dry_run_returns_0(
    tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    cli = _load_cli()
    exit_code = cli.main(
        [
            "--fixture-mode",
            "--dry-run",
            "--input-run-dir",
            str(etl_fixture_run),
            "--exchange-rate",
            str(exchange_rate_path),
            "--neighborhood-aliases",
            str(neighborhood_aliases_path),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    assert exit_code == 0
    assert not (tmp_path / "out").exists()


def test_unexpected_exception_returns_1(monkeypatch, tmp_path, etl_fixture_run, exchange_rate_path):
    from alquileres_uy.etl.pipeline import EtlPipeline

    def _boom(self):
        raise RuntimeError("boom")

    monkeypatch.setattr(EtlPipeline, "dry_run", _boom)
    cli = _load_cli()
    exit_code = cli.main(
        [
            "--fixture-mode",
            "--dry-run",
            "--input-run-dir",
            str(etl_fixture_run),
            "--exchange-rate",
            str(exchange_rate_path),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    assert exit_code == 1
