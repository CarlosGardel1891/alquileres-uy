import json
from pathlib import Path

import pytest

from alquileres_uy.etl.config import EtlConfig
from alquileres_uy.etl.currency import InvalidExchangeRate
from alquileres_uy.etl.pipeline import EtlPipeline


def _config(
    tmp_path: Path, etl_fixture_run: Path, exchange_rate_path: Path, neighborhood_aliases_path: Path
) -> EtlConfig:
    return EtlConfig(
        input_run_dirs=(etl_fixture_run,),
        exchange_rate_path=exchange_rate_path,
        neighborhood_aliases_path=neighborhood_aliases_path,
        output_dir=tmp_path / "out",
        fixture_mode=True,
    )


def test_fixture_run_produces_all_outputs(
    tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    config = _config(tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path)
    result = EtlPipeline(config).run()
    workdir = result.workdir
    expected = [
        "listings.parquet",
        "model_ready.parquet",
        "rejected_listings.parquet",
        "duplicate_candidates.parquet",
        "etl_summary.json",
        "data_quality_report.json",
        "unmapped_attributes.json",
        "lineage.json",
        "schema.json",
    ]
    for name in expected:
        assert (workdir / name).exists(), f"missing {name}"


def test_summary_marks_data_mode_fixture(
    tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    config = _config(tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path)
    result = EtlPipeline(config).run()
    summary = json.loads((result.workdir / "etl_summary.json").read_text(encoding="utf-8"))
    assert summary["data_mode"] == "fixture"


def test_pipeline_does_not_touch_raw_run(
    tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    before = {p: p.read_bytes() for p in etl_fixture_run.rglob("*.json")}
    config = _config(tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path)
    EtlPipeline(config).run()
    after = {p: p.read_bytes() for p in etl_fixture_run.rglob("*.json")}
    assert before == after


def test_dry_run_makes_no_output(
    tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    output_dir = tmp_path / "out"
    config = EtlConfig(
        input_run_dirs=(etl_fixture_run,),
        exchange_rate_path=exchange_rate_path,
        neighborhood_aliases_path=neighborhood_aliases_path,
        output_dir=output_dir,
        fixture_mode=True,
        dry_run=True,
    )
    plan = EtlPipeline(config).dry_run()
    assert plan["dry_run"] is True
    assert not output_dir.exists()


def test_deterministic_row_counts(
    tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    config_a = _config(
        tmp_path / "a", etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
    )
    config_b = _config(
        tmp_path / "b", etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
    )
    result_a = EtlPipeline(config_a).run()
    result_b = EtlPipeline(config_b).run()
    assert result_a.summary["canonical_items"] == result_b.summary["canonical_items"]
    assert result_a.summary["rejected_items"] == result_b.summary["rejected_items"]


def test_rejected_dataset_contains_reasons(
    tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    config = _config(tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path)
    result = EtlPipeline(config).run()
    reasons = set()
    for value in result.rejected["rejection_reasons"].dropna():
        reasons.update(value.split("|"))
    assert "sale" in reasons
    assert "temporary_rental" in reasons
    assert "outside_montevideo" in reasons


def test_model_ready_has_no_leakage_columns(
    tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    config = _config(tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path)
    result = EtlPipeline(config).run()
    forbidden = {"price_per_m2", "price_bucket", "total_monthly_cost_usd"}
    assert not forbidden.intersection(result.model_ready.columns)


def test_lineage_has_no_absolute_paths(
    tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    config = _config(tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path)
    result = EtlPipeline(config).run()
    lineage = json.loads((result.workdir / "lineage.json").read_text(encoding="utf-8"))
    for value in lineage["output_files"].values():
        assert Path(value).name == value
    assert lineage["data_mode"] == "fixture"


def test_second_run_uses_new_workdir(
    tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    config = _config(tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path)
    first = EtlPipeline(config).run()
    second = EtlPipeline(config).run()
    assert first.workdir != second.workdir


def test_invalid_exchange_rate_stops_pipeline(tmp_path, etl_fixture_run, neighborhood_aliases_path):
    bad_rate = tmp_path / "bad.json"
    bad_rate.write_text(
        '{"base_currency":"USD","quote_currency":"UYU","uyu_per_usd":0,'
        '"effective_date":"2026-01-01","source":"x","data_mode":"fixture",'
        '"retrieved_at":"2026-01-01T00:00:00Z"}',
        encoding="utf-8",
    )
    config = EtlConfig(
        input_run_dirs=(etl_fixture_run,),
        exchange_rate_path=bad_rate,
        neighborhood_aliases_path=neighborhood_aliases_path,
        output_dir=tmp_path / "out",
        fixture_mode=True,
    )
    with pytest.raises(InvalidExchangeRate):
        EtlPipeline(config).run()
