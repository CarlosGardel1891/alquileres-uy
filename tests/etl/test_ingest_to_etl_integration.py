"""End-to-end integration between the Fase 1 ingestion writer and Fase 2 loader.

The test spins up a fake HTTP session, runs :class:`IngestionService`
against it (still under ``tests/fixtures/``), reads the manifest that
Fase 1 wrote, and verifies that Fase 2's :func:`load_raw_run` accepts
it without changes. This is the only test that exercises the real
manifest.files shape produced by production ingestion code, so it
guards against the two fases drifting apart.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from alquileres_uy.etl.contracts import RawRunValidationError, load_raw_run
from alquileres_uy.ingest.config import IngestionConfig
from alquileres_uy.ingest.repository import IngestionRepository
from alquileres_uy.ingest.service import IngestionService
from tests.ingest.conftest import FakeResponse, approved_contract  # type: ignore[import-not-found]


class _FakeClient:
    """Minimal client for a self-contained ingestion run."""

    def __init__(self, sample_ids: list[str]) -> None:
        self._sample_ids = sample_ids
        self._search_pages = [
            self._build_search_page(sample_ids),
            self._build_search_page([]),
            self._build_search_page([]),
            self._build_search_page([]),
        ]
        self.description_body = {"plain_text": "descripcion", "text": "<p>x</p>"}

    def _build_search_page(self, ids: list[str]) -> dict:
        return {
            "site_id": "MLU",
            "paging": {"total": 30, "offset": 0, "limit": 100, "primary_results": len(ids)},
            "results": [{"id": item_id, "title": f"item {item_id}"} for item_id in ids],
            "available_filters": [],
        }

    def search_items(self, site_id, params=None):
        return FakeResponse(json_data=self._search_pages.pop(0))

    def get_items(self, item_ids):
        multiget = [
            {
                "code": 200,
                "body": {
                    "id": item_id,
                    "title": f"item {item_id}",
                    "category_id": "MLU_TEST_APARTMENT",
                    "price": 1000,
                    "currency_id": "USD",
                    "date_created": "2026-01-01T09:00:00Z",
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
                },
            }
            for item_id in item_ids
        ]
        return FakeResponse(json_data=multiget)

    def get_item_description(self, item_id):
        return FakeResponse(json_data=dict(self.description_body))


def _clock_factory(start: datetime):
    counter = {"n": 0}

    def _clock() -> datetime:
        counter["n"] += 1
        return start + timedelta(seconds=counter["n"])

    return _clock


@pytest.fixture
def ingest_run_dir(tmp_path):
    """Run a full Fase 1 ingestion under tests/fixtures/ and return its dir."""
    output_root = (
        Path(__file__).resolve().parents[1] / "fixtures" / f"ingest_integration_{tmp_path.name}"
    )
    config = IngestionConfig(
        output_dir=output_root,
        database_path=tmp_path / "ingestion.sqlite",
        max_items=10,
        requests_per_second=1e9,
    )
    fake_ids = [f"MLU_TEST_{i:03d}" for i in range(1, 6)]
    fake_client = _FakeClient(fake_ids)
    service = IngestionService(
        config,
        contract=approved_contract(),
        client_factory=lambda _cfg: fake_client,
        repository_factory=IngestionRepository,
        clock=_clock_factory(datetime(2026, 8, 4, 22, 0, tzinfo=UTC)),
    )
    result = service.run()
    return result.workdir


def test_phase1_manifest_is_readable_by_phase2_loader(ingest_run_dir):
    fixtures_root = ingest_run_dir.parents[1]
    run = load_raw_run(ingest_run_dir, data_mode="fixture", fixtures_root=fixtures_root)
    assert run.item_batch_paths
    assert any(entry.kind == "report" for entry in run.declared_files)
    summary_entry = next(
        entry for entry in run.declared_files if entry.path == "ingestion_summary.json"
    )
    assert summary_entry.kind == "report"


def test_phase1_summary_path_and_timestamps_are_wired_end_to_end(ingest_run_dir):
    """The Fase 1 manifest must satisfy every Fase 2 summary invariant."""
    manifest = json.loads((ingest_run_dir / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((ingest_run_dir / "ingestion_summary.json").read_text(encoding="utf-8"))
    # Exact-path invariant: summary_path is the root file, declared once as report.
    assert manifest["summary_path"] == "ingestion_summary.json"
    reports = [entry for entry in manifest["files"] if entry.get("kind") == "report"]
    matching = [entry for entry in reports if entry["path"] == manifest["summary_path"]]
    assert len(matching) == 1
    # Timestamp invariant: both are present and match the manifest instant.
    assert isinstance(summary.get("started_at"), str) and summary["started_at"]
    assert isinstance(summary.get("finished_at"), str) and summary["finished_at"]
    assert summary["started_at"] == manifest["started_at"]
    assert summary["finished_at"] == manifest["finished_at"]
    # And the loader accepts it without adaptations.
    fixtures_root = ingest_run_dir.parents[1]
    load_raw_run(ingest_run_dir, data_mode="fixture", fixtures_root=fixtures_root)


def test_phase1_manifest_hashes_match_files(ingest_run_dir):
    manifest = json.loads((ingest_run_dir / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        path = ingest_run_dir / entry["path"]
        expected = entry["sha256"]
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == expected, f"stale hash for {entry['path']}"


def test_phase1_summary_counts_match_envelopes(ingest_run_dir):
    fixtures_root = ingest_run_dir.parents[1]
    load_raw_run(ingest_run_dir, data_mode="fixture", fixtures_root=fixtures_root)


def test_modifying_a_batch_after_the_fact_breaks_the_loader(ingest_run_dir):
    fixtures_root = ingest_run_dir.parents[1]
    batches = list((ingest_run_dir / "items").glob("*.json"))
    batches[0].write_bytes(batches[0].read_bytes() + b"\n")
    with pytest.raises(RawRunValidationError, match="sha256 mismatch"):
        load_raw_run(ingest_run_dir, data_mode="fixture", fixtures_root=fixtures_root)
