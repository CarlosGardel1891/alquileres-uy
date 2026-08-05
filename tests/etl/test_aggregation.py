"""Tests that first_seen_at / last_seen_at are aggregated across observations."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from alquileres_uy.etl.config import EtlConfig
from alquileres_uy.etl.pipeline import EtlPipeline


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_run(root: Path, *, run_id: str, started: str, finished: str, items: list[dict]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    items_dir = root / "items"
    items_dir.mkdir(exist_ok=True)
    batch = items_dir / "batch_0001.json"
    envelopes = [{"code": 200, "body": body} for body in items]
    batch.write_text(json.dumps(envelopes, ensure_ascii=False), encoding="utf-8")
    summary_path = root / "ingestion_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "status": "completed",
                "started_at": started,
                "finished_at": finished,
                "items_downloaded": len(items),
                "descriptions_downloaded": 0,
            }
        ),
        encoding="utf-8",
    )
    manifest = {
        "run_id": run_id,
        "source": "mercadolibre",
        "status": "completed",
        "started_at": started,
        "finished_at": finished,
        "files": [
            {"path": "items/batch_0001.json", "kind": "item_batch", "sha256": _sha(batch)},
            {"path": "ingestion_summary.json", "kind": "report", "sha256": _sha(summary_path)},
        ],
        "summary_path": "ingestion_summary.json",
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _body(item_id: str, *, last_updated: str) -> dict:
    return {
        "id": item_id,
        "title": "Apartamento",
        "category_id": "MLU_TEST_APARTMENT",
        "price": 1000,
        "currency_id": "USD",
        "date_created": "2026-01-01T09:00:00Z",
        "last_updated": last_updated,
        "location": {
            "state": {"name": "Montevideo"},
            "city": {"name": "Pocitos"},
            "neighborhood": {"name": "Pocitos"},
        },
        "attributes": [
            {"id": "OPERATION", "value_id": "242075", "value_name": "Alquiler"},
            {"id": "PROPERTY_TYPE", "value_name": "Apartamento"},
            {"id": "BEDROOMS", "value_name": "2"},
            {"id": "TOTAL_AREA", "value_name": "50 m2"},
        ],
    }


def _fixture_root(tmp_path: Path) -> Path:
    fixtures = Path(__file__).resolve().parents[1] / "fixtures" / "etl_agg_tmp"
    # Force the run to live under tests/fixtures for fixture-mode acceptance.
    fixtures.mkdir(parents=True, exist_ok=True)
    return fixtures


def _run_pipeline(runs: list[Path], tmp_path: Path, exchange_rate_path, aliases_path):
    config = EtlConfig(
        input_run_dirs=tuple(runs),
        exchange_rate_path=exchange_rate_path,
        neighborhood_aliases_path=aliases_path,
        output_dir=tmp_path / "out",
        fixture_mode=True,
    )
    return EtlPipeline(config).run()


def test_two_observations_preserve_min_first_seen(
    tmp_path, exchange_rate_path, neighborhood_aliases_path
):
    base = _fixture_root(tmp_path)
    a = _write_run(
        base / f"agg_a_{tmp_path.name}",
        run_id="agg-a",
        started="2026-01-01T00:00:00Z",
        finished="2026-01-01T00:05:00Z",
        items=[_body("MLU_AGG_1", last_updated="2026-01-01T09:00:00Z")],
    )
    b = _write_run(
        base / f"agg_b_{tmp_path.name}",
        run_id="agg-b",
        started="2026-06-01T00:00:00Z",
        finished="2026-06-01T00:05:00Z",
        items=[_body("MLU_AGG_1", last_updated="2026-06-01T09:00:00Z")],
    )
    result = _run_pipeline([a, b], tmp_path, exchange_rate_path, neighborhood_aliases_path)
    row = result.canonical[result.canonical["source_item_id"] == "MLU_AGG_1"].iloc[0]
    assert row["first_seen_at"] == datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    assert row["last_seen_at"] == datetime(2026, 6, 1, 0, 5, tzinfo=UTC)
    assert int(row["observations_count"]) == 2


def test_three_observations_aggregate(tmp_path, exchange_rate_path, neighborhood_aliases_path):
    base = _fixture_root(tmp_path)
    a = _write_run(
        base / f"agg_x_{tmp_path.name}",
        run_id="agg-x",
        started="2026-02-01T00:00:00Z",
        finished="2026-02-01T00:05:00Z",
        items=[_body("MLU_AGG_2", last_updated="2026-02-01T09:00:00Z")],
    )
    b = _write_run(
        base / f"agg_y_{tmp_path.name}",
        run_id="agg-y",
        started="2026-04-01T00:00:00Z",
        finished="2026-04-01T00:05:00Z",
        items=[_body("MLU_AGG_2", last_updated="2026-04-01T09:00:00Z")],
    )
    c = _write_run(
        base / f"agg_z_{tmp_path.name}",
        run_id="agg-z",
        started="2026-07-01T00:00:00Z",
        finished="2026-07-01T00:05:00Z",
        items=[_body("MLU_AGG_2", last_updated="2026-07-01T09:00:00Z")],
    )
    result = _run_pipeline([a, b, c], tmp_path, exchange_rate_path, neighborhood_aliases_path)
    row = result.canonical[result.canonical["source_item_id"] == "MLU_AGG_2"].iloc[0]
    assert row["first_seen_at"] == datetime(2026, 2, 1, 0, 0, tzinfo=UTC)
    assert row["last_seen_at"] == datetime(2026, 7, 1, 0, 5, tzinfo=UTC)
    assert int(row["observations_count"]) == 3
    # Canonical row is the one from the newest last_updated: run agg-z.
    assert row["source_run_id"] == "agg-z"


def test_older_observation_does_not_erase_history(
    tmp_path, exchange_rate_path, neighborhood_aliases_path
):
    base = _fixture_root(tmp_path)
    # newer run processed first
    newer = _write_run(
        base / f"agg_nw_{tmp_path.name}",
        run_id="agg-nw",
        started="2026-06-01T00:00:00Z",
        finished="2026-06-01T00:05:00Z",
        items=[_body("MLU_AGG_3", last_updated="2026-06-01T09:00:00Z")],
    )
    older = _write_run(
        base / f"agg_ol_{tmp_path.name}",
        run_id="agg-ol",
        started="2026-01-01T00:00:00Z",
        finished="2026-01-01T00:05:00Z",
        items=[_body("MLU_AGG_3", last_updated="2026-01-01T09:00:00Z")],
    )
    result = _run_pipeline([newer, older], tmp_path, exchange_rate_path, neighborhood_aliases_path)
    row = result.canonical[result.canonical["source_item_id"] == "MLU_AGG_3"].iloc[0]
    assert row["first_seen_at"] == datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
