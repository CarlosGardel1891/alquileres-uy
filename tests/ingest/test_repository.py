"""Tests for the SQLite ingestion repository and its idempotency guarantees."""

from __future__ import annotations

from pathlib import Path

from alquileres_uy.ingest.models import CandidateStatus, QueryStatus, RunStatus
from alquileres_uy.ingest.repository import IngestionRepository


def _open(tmp_path: Path) -> IngestionRepository:
    return IngestionRepository(tmp_path / "ingestion.sqlite")


def _start_run(repo: IngestionRepository, run_id: str, started_at: str) -> None:
    repo.start_run(
        run_id=run_id,
        source="mercadolibre",
        started_at=started_at,
        max_items=5000,
        requests_per_second=2.0,
        query_plan_hash="hash",
    )


def test_start_and_finalize_run(tmp_path: Path) -> None:
    repo = _open(tmp_path)
    _start_run(repo, "run-1", "2026-08-04T00:00:00Z")
    repo.finalize_run(
        run_id="run-1",
        finished_at="2026-08-04T00:05:00Z",
        status=RunStatus.COMPLETED,
        totals={"search_results": 42, "unique_items": 30, "items_downloaded": 30},
    )
    row = repo._connection.execute("SELECT * FROM runs WHERE run_id='run-1'").fetchone()
    assert row["status"] == "completed"
    assert row["total_search_results"] == 42
    repo.close()


def test_upsert_item_preserves_first_seen_at_and_updates_last_seen_at(tmp_path: Path) -> None:
    repo = _open(tmp_path)
    _start_run(repo, "run-1", "2026-08-04T00:00:00Z")

    repo.upsert_item(
        item_id="MLU1",
        source="mercadolibre",
        observed_at="2026-08-04T00:00:00Z",
        latest_raw_path="run-1/items/batch_0001.json",
        category_id="MLU1466",
        status="candidate",
    )
    repo.upsert_item(
        item_id="MLU1",
        source="mercadolibre",
        observed_at="2026-08-11T00:00:00Z",
        latest_raw_path="run-2/items/batch_0001.json",
    )

    row = repo.item("MLU1")
    assert row is not None
    assert row["first_seen_at"] == "2026-08-04T00:00:00Z"
    assert row["last_seen_at"] == "2026-08-11T00:00:00Z"
    assert row["latest_raw_path"] == "run-2/items/batch_0001.json"
    assert row["category_id"] == "MLU1466"
    assert row["status"] == "candidate"
    repo.close()


def test_upsert_does_not_duplicate_item_across_runs(tmp_path: Path) -> None:
    repo = _open(tmp_path)
    _start_run(repo, "run-1", "2026-08-04T00:00:00Z")
    _start_run(repo, "run-2", "2026-08-11T00:00:00Z")

    for run_id, observed in (
        ("run-1", "2026-08-04T00:00:00Z"),
        ("run-2", "2026-08-11T00:00:00Z"),
    ):
        repo.upsert_item(
            item_id="MLU1",
            source="mercadolibre",
            observed_at=observed,
        )
        repo.record_run_item(
            run_id=run_id,
            item_id="MLU1",
            query_id=None,
            raw_path=None,
            position=1,
            candidate_status=CandidateStatus.CANDIDATE,
            exclusion_reason=None,
        )

    assert repo.count_items() == 1
    assert len(list(repo.run_items("run-1"))) == 1
    assert len(list(repo.run_items("run-2"))) == 1
    repo.close()


def test_record_query_and_errors(tmp_path: Path) -> None:
    repo = _open(tmp_path)
    _start_run(repo, "run-1", "2026-08-04T00:00:00Z")
    repo.record_query(
        query_id="q1",
        run_id="run-1",
        segment_key="apartment|Montevideo|rent",
        parameters={"category": "MLU1466"},
        status=QueryStatus.COMPLETED,
        reported_total=3200,
        pages_downloaded=10,
        results_received=1000,
    )
    repo.record_error(
        run_id="run-1",
        endpoint="/sites/MLU/search",
        status_code=500,
        attempt=3,
        error_type="ServerHttpError",
        message="upstream failure",
        occurred_at="2026-08-04T00:01:00Z",
    )
    repo.record_error(
        run_id="run-1",
        endpoint="/items",
        status_code=None,
        attempt=2,
        error_type="TransientNetworkError",
        message="timeout",
        occurred_at="2026-08-04T00:02:00Z",
    )

    counts = repo.errors_by_status("run-1")
    assert counts.get("500") == 1
    assert counts.get("TransientNetworkError") == 1
    repo.close()
