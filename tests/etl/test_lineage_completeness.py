"""Additional lineage.json guarantees on top of the existing suite."""

from __future__ import annotations

import json
from pathlib import Path

from alquileres_uy.etl.config import EtlConfig
from alquileres_uy.etl.pipeline import EtlPipeline


def _run(tmp_path: Path, etl_fixture_run: Path, exchange_rate_path: Path, aliases_path: Path):
    config = EtlConfig(
        input_run_dirs=(etl_fixture_run,),
        exchange_rate_path=exchange_rate_path,
        neighborhood_aliases_path=aliases_path,
        output_dir=tmp_path / "out",
        fixture_mode=True,
    )
    return EtlPipeline(config).run()


def _lineage(result) -> dict:
    return json.loads((result.workdir / "lineage.json").read_text(encoding="utf-8"))


def test_manifest_appears_in_input_hashes(
    tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    result = _run(tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path)
    lineage = _lineage(result)
    keys = list(lineage["input_file_sha256"].keys())
    assert any(key.endswith("/manifest.json") for key in keys)


def test_summary_appears_in_input_hashes(
    tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    result = _run(tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path)
    lineage = _lineage(result)
    keys = list(lineage["input_file_sha256"].keys())
    assert any(key.endswith("/ingestion_summary.json") for key in keys)


def test_all_batches_and_descriptions_appear(
    tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    result = _run(tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path)
    lineage = _lineage(result)
    keys = list(lineage["input_file_sha256"].keys())
    batches = [key for key in keys if "/items/" in key]
    descriptions = [key for key in keys if "/descriptions/" in key]
    assert len(batches) == 2
    assert len(descriptions) == 3


def test_input_file_count_matches_dict(
    tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    result = _run(tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path)
    lineage = _lineage(result)
    assert lineage["input_file_count"] == len(lineage["input_file_sha256"])


def test_every_output_json_appears(
    tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    result = _run(tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path)
    lineage = _lineage(result)
    expected_outputs = {
        "listings",
        "model_ready",
        "rejected_listings",
        "duplicate_candidates",
        "data_quality_report",
        "unmapped_attributes",
        "etl_summary",
        "schema",
    }
    assert expected_outputs.issubset(set(lineage["output_files"].keys()))


def test_lineage_never_self_hashes(
    tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    result = _run(tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path)
    lineage = _lineage(result)
    assert lineage["lineage_self_hashed"] is False
    assert "lineage" not in lineage["output_files"]


def test_dry_run_includes_input_hashes(
    tmp_path, etl_fixture_run, exchange_rate_path, neighborhood_aliases_path
):
    config = EtlConfig(
        input_run_dirs=(etl_fixture_run,),
        exchange_rate_path=exchange_rate_path,
        neighborhood_aliases_path=neighborhood_aliases_path,
        output_dir=tmp_path / "out",
        fixture_mode=True,
        dry_run=True,
    )
    plan = EtlPipeline(config).dry_run()
    assert plan["input_file_count"] > 0
    assert plan["exchange_rate_sha256"] is not None
    assert not (tmp_path / "out").exists()
