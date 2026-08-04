"""Tests for the --strict quality gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from alquileres_uy.etl.config import EtlConfig
from alquileres_uy.etl.pipeline import EtlPipeline, StrictQualityGateError


def _config(
    tmp_path: Path,
    etl_fixture_run: Path,
    exchange_rate_path: Path,
    aliases_path: Path,
    *,
    strict: bool,
) -> EtlConfig:
    return EtlConfig(
        input_run_dirs=(etl_fixture_run,),
        exchange_rate_path=exchange_rate_path,
        neighborhood_aliases_path=aliases_path,
        output_dir=tmp_path / "out",
        fixture_mode=True,
        strict=strict,
    )


def test_non_strict_processes_fixture(
    tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    config = _config(
        tmp_path,
        etl_fixture_run,
        exchange_rate_path,
        neighborhood_aliases_path,
        strict=False,
    )
    result = EtlPipeline(config).run()
    assert result.summary["status"] == "completed"


def test_strict_rejects_current_fixture_because_of_rejections(
    tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    config = _config(
        tmp_path,
        etl_fixture_run,
        exchange_rate_path,
        neighborhood_aliases_path,
        strict=True,
    )
    with pytest.raises(StrictQualityGateError) as info:
        EtlPipeline(config).run()
    exc = info.value
    assert exc.rejected_items > 0
    assert exc.unmapped_attributes >= 1
    assert exc.invalid_dates >= 1
    assert exc.area_inconsistencies >= 1


def test_strict_failure_leaves_no_output(
    tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    output_dir = tmp_path / "out"
    config = _config(
        tmp_path,
        etl_fixture_run,
        exchange_rate_path,
        neighborhood_aliases_path,
        strict=True,
    )
    with pytest.raises(StrictQualityGateError):
        EtlPipeline(config).run()
    assert not output_dir.exists()


def test_strict_does_not_modify_input(
    tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    before = {p: p.read_bytes() for p in etl_fixture_run.rglob("*.json")}
    config = _config(
        tmp_path,
        etl_fixture_run,
        exchange_rate_path,
        neighborhood_aliases_path,
        strict=True,
    )
    with pytest.raises(StrictQualityGateError):
        EtlPipeline(config).run()
    after = {p: p.read_bytes() for p in etl_fixture_run.rglob("*.json")}
    assert before == after


def test_dry_run_reports_strict_flag(
    tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    config = _config(
        tmp_path,
        etl_fixture_run,
        exchange_rate_path,
        neighborhood_aliases_path,
        strict=True,
    )
    plan = EtlPipeline(config).dry_run()
    assert plan["strict"] is True


def test_cli_returns_1_on_strict_failure(
    tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    from importlib import util

    cli_path = Path(__file__).resolve().parents[2] / "scripts" / "run_etl.py"
    spec = util.spec_from_file_location("_etl_cli_strict", cli_path)
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    exit_code = module.main(
        [
            "--fixture-mode",
            "--strict",
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
    assert exit_code == 1
    assert not (tmp_path / "out").exists()
