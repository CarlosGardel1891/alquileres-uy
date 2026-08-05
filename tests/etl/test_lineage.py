from pathlib import Path

from alquileres_uy.etl.contracts import load_raw_run
from alquileres_uy.etl.lineage import build_lineage


def test_lineage_lists_inputs_and_outputs(etl_fixture_run, tmp_path, exchange_rate_path):
    run = load_raw_run(
        etl_fixture_run,
        data_mode="fixture",
        fixtures_root=etl_fixture_run.parents[2],
    )
    (tmp_path / "listings.parquet").write_bytes(b"")
    lineage = build_lineage(
        etl_run_id="run-a",
        etl_schema_version="1.0.0",
        data_mode="fixture",
        started_at="2026-08-04T22:00:00Z",
        finished_at="2026-08-04T22:15:00Z",
        runs=[run],
        gate_approval_path=None,
        exchange_rate_path=exchange_rate_path,
        neighborhood_aliases_path=None,
        output_files={"listings": tmp_path / "listings.parquet"},
        row_counts={"canonical": 10},
    )
    assert lineage["data_mode"] == "fixture"
    assert lineage["gate_approval_path"] is None
    assert lineage["input_file_count"] > 0
    for value in lineage["output_files"].values():
        assert Path(value).name == value  # no absolute paths
    assert "token" not in str(lineage).lower()
