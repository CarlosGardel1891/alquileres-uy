"""Tests for exchange-rate ↔ ETL data_mode consistency."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from alquileres_uy.etl.config import EtlConfig
from alquileres_uy.etl.currency import (
    ExchangeRateModeMismatch,
    InvalidExchangeRate,
    ensure_mode_consistent,
    load_exchange_rate,
)
from alquileres_uy.etl.pipeline import EtlPipeline


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


def test_fixture_mode_accepts_fixture_rate(tmp_path):
    rate = load_exchange_rate(_write_rate(tmp_path / "r.json"))
    ensure_mode_consistent(rate, "fixture")


def test_real_mode_accepts_real_rate(tmp_path):
    path = _write_rate(
        tmp_path / "r.json",
        data_mode="real",
        source="banco-central",
        retrieved_at="2026-08-04T10:00:00-03:00",
    )
    rate = load_exchange_rate(path)
    ensure_mode_consistent(rate, "real")


def test_real_mode_rejects_fixture_rate(tmp_path):
    rate = load_exchange_rate(_write_rate(tmp_path / "r.json"))
    with pytest.raises(ExchangeRateModeMismatch, match="does not match"):
        ensure_mode_consistent(rate, "real")


def test_fixture_mode_rejects_real_rate(tmp_path):
    path = _write_rate(
        tmp_path / "r.json",
        data_mode="real",
        source="banco-central",
        retrieved_at="2026-08-04T10:00:00+00:00",
    )
    rate = load_exchange_rate(path)
    with pytest.raises(ExchangeRateModeMismatch):
        ensure_mode_consistent(rate, "fixture")


def test_real_mode_rejects_source_fixture(tmp_path):
    path = _write_rate(
        tmp_path / "r.json",
        data_mode="real",
        source="fixture",
        retrieved_at="2026-08-04T10:00:00+00:00",
    )
    rate = load_exchange_rate(path)
    with pytest.raises(ExchangeRateModeMismatch, match="source"):
        ensure_mode_consistent(rate, "real")


def test_load_rate_rejects_retrieved_at_without_timezone(tmp_path):
    path = _write_rate(tmp_path / "r.json", retrieved_at="2026-01-01T00:00:00")
    with pytest.raises(InvalidExchangeRate, match="timezone"):
        load_exchange_rate(path)


def test_pipeline_dry_run_detects_mode_mismatch(tmp_path, etl_fixture_run):
    bad_rate = _write_rate(
        tmp_path / "r.json",
        data_mode="real",
        source="banco-central",
        retrieved_at="2026-08-04T10:00:00+00:00",
    )
    config = EtlConfig(
        input_run_dirs=(etl_fixture_run,),
        exchange_rate_path=bad_rate,
        output_dir=tmp_path / "out",
        fixture_mode=True,
    )
    with pytest.raises(ExchangeRateModeMismatch):
        EtlPipeline(config).dry_run()


def test_pipeline_run_leaves_no_output_on_mode_mismatch(
    tmp_path, etl_fixture_run, neighborhood_aliases_path
):
    bad_rate = _write_rate(
        tmp_path / "r.json",
        data_mode="real",
        source="banco-central",
        retrieved_at="2026-08-04T10:00:00+00:00",
    )
    output_dir = tmp_path / "out"
    config = EtlConfig(
        input_run_dirs=(etl_fixture_run,),
        exchange_rate_path=bad_rate,
        neighborhood_aliases_path=neighborhood_aliases_path,
        output_dir=output_dir,
        fixture_mode=True,
    )
    with pytest.raises(ExchangeRateModeMismatch):
        EtlPipeline(config).run()
    assert not output_dir.exists()


def test_cli_returns_2_on_mode_mismatch(tmp_path, etl_fixture_run):
    from importlib import util

    bad_rate = _write_rate(
        tmp_path / "r.json",
        data_mode="real",
        source="banco-central",
        retrieved_at="2026-08-04T10:00:00+00:00",
    )
    cli_path = Path(__file__).resolve().parents[2] / "scripts" / "run_etl.py"
    spec = util.spec_from_file_location("_etl_cli", cli_path)
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    exit_code = module.main(
        [
            "--fixture-mode",
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
