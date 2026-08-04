"""End-to-end style tests for :class:`IngestionService`."""

from __future__ import annotations

import copy
import json
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from alquileres_uy.ingest.config import IngestionConfig
from alquileres_uy.ingest.repository import IngestionRepository
from alquileres_uy.ingest.service import IngestionService

from .conftest import FakeResponse, approved_contract, load_fixture


class _FakeMercadoLibreClient:
    """Client stub that replays scripted responses per endpoint."""

    def __init__(
        self,
        search_pages: list[dict[str, Any]],
        multiget_batches: list[list[dict[str, Any]]],
        description_body: dict[str, Any],
    ) -> None:
        self._search_pages = list(search_pages)
        self._multiget_batches = list(multiget_batches)
        self._description_body = description_body
        self.search_calls: list[dict[str, Any] | None] = []
        self.get_items_calls: list[list[str]] = []
        self.description_calls: list[str] = []

    def search_items(self, site_id: str, params: dict[str, Any] | None = None) -> FakeResponse:
        self.search_calls.append(params)
        if not self._search_pages:
            return FakeResponse(json_data={"paging": {"total": 0}, "results": []})
        return FakeResponse(json_data=self._search_pages.pop(0))

    def get_items(self, item_ids: Iterable[str]) -> FakeResponse:
        ids = list(item_ids)
        self.get_items_calls.append(ids)
        if not self._multiget_batches:
            return FakeResponse(json_data=[])
        return FakeResponse(json_data=self._multiget_batches.pop(0))

    def get_item_description(self, item_id: str) -> FakeResponse:
        self.description_calls.append(item_id)
        return FakeResponse(json_data=dict(self._description_body))


def _config(tmp_path: Path) -> IngestionConfig:
    return IngestionConfig(
        output_dir=tmp_path / "raw",
        database_path=tmp_path / "ingestion.sqlite",
        max_items=40,
        requests_per_second=1e9,
    )


def _clock_factory(start: datetime):
    counter = {"tick": 0}

    def _clock() -> datetime:
        counter["tick"] += 1
        return start + timedelta(seconds=counter["tick"])

    return _clock


def _build_service(
    tmp_path: Path,
    client: _FakeMercadoLibreClient,
    started_at: datetime | None = None,
) -> IngestionService:
    config = _config(tmp_path)
    clock = _clock_factory(started_at or datetime(2026, 8, 4, 12, 0, tzinfo=UTC))
    return IngestionService(
        config,
        contract=approved_contract(),
        client_factory=lambda _cfg: client,
        repository_factory=IngestionRepository,
        clock=clock,
    )


def _build_search_page(ids: list[str], total: int) -> dict[str, Any]:
    return {
        "site_id": "MLU",
        "paging": {"total": total, "offset": 0, "limit": 100, "primary_results": len(ids)},
        "results": [{"id": item_id, "title": f"item {item_id}"} for item_id in ids],
        "available_filters": [],
    }


def test_dry_run_returns_plan_without_touching_network(tmp_path: Path) -> None:
    service = _build_service(tmp_path, _FakeMercadoLibreClient([], [], {}))
    plan = service.dry_run()

    assert plan["dry_run"] is True
    assert plan["seed_segment_count"] == 2
    assert plan["gate_approval_hash"] == "0" * 64
    assert not (tmp_path / "raw").exists()
    assert not (tmp_path / "ingestion.sqlite").exists()


def test_full_run_deduplicates_ids_and_downloads_items(tmp_path: Path) -> None:
    multiget = load_fixture("item_multiget_success.json")
    description = load_fixture("description_success.json")
    all_ids = [entry["body"]["id"] for entry in multiget]

    page_1 = _build_search_page(all_ids[:20], total=30)
    empty_page = _build_search_page([], total=0)

    client = _FakeMercadoLibreClient(
        search_pages=[page_1, empty_page, page_1, empty_page],
        multiget_batches=[multiget],
        description_body=description,
    )

    result = _build_service(tmp_path, client).run()

    assert result.summary["items_downloaded"] == 20
    assert result.summary["candidate_items"] >= 1
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["authentication"] == {"token_used": False}
    assert "access_token" not in json.dumps(manifest)


def test_repeated_page_stops_segment_and_is_recorded(tmp_path: Path) -> None:
    # A page must have MAX_SEARCH_PAGE_SIZE (100) IDs for pagination to
    # continue; otherwise the segment ends normally after one page.
    full_ids = [f"MLU{i:07d}" for i in range(100)]
    page = _build_search_page(full_ids, total=500)
    repeated = _build_search_page(full_ids, total=500)  # identical IDs
    empty = _build_search_page([], total=0)

    # Two seed segments (apartment + house); each gets [page, repeated, ...].
    client = _FakeMercadoLibreClient(
        search_pages=[page, repeated, empty, empty],
        multiget_batches=[[]],  # multiget not really exercised here
        description_body={"plain_text": ""},
    )
    # Raise max_items above the page size so pagination is not cut off
    # by the global cap before the repeated page can be exercised.
    config = _config(tmp_path)
    from dataclasses import replace as dc_replace

    config = dc_replace(config, max_items=500)
    service = IngestionService(
        config,
        contract=approved_contract(),
        client_factory=lambda _cfg: client,
        repository_factory=IngestionRepository,
        clock=_clock_factory(datetime(2026, 8, 4, 12, 0, tzinfo=UTC)),
    )

    result = service.run()

    assert result.summary["repeated_pages_detected"] >= 1
    repo = IngestionRepository(_config(tmp_path).database_path)
    try:
        rows = repo._connection.execute(
            "SELECT segment_key, repeated_page_detected, pages_downloaded FROM queries"
        ).fetchall()
        detected = [row for row in rows if row["repeated_page_detected"] == 1]
        assert detected, "at least one query row must flag the repeated page"
        raw_pages = list((result.workdir / "searches").glob("query_*/page_*.json"))
        assert len(raw_pages) >= 2  # both the initial page and the repeat are kept
    finally:
        repo.close()


def test_run_items_carry_the_query_id_that_discovered_them(tmp_path: Path) -> None:
    multiget = load_fixture("item_multiget_success.json")
    ids = [entry["body"]["id"] for entry in multiget]
    empty = _build_search_page([], total=0)

    client = _FakeMercadoLibreClient(
        search_pages=[_build_search_page(ids, total=20), empty, empty, empty],
        multiget_batches=[multiget],
        description_body={"plain_text": "x"},
    )

    result = _build_service(tmp_path, client).run()

    repo = IngestionRepository(_config(tmp_path).database_path)
    try:
        rows = list(repo.run_items(result.run_id))
        assert rows, "expected at least one run_item"
        for row in rows:
            assert row["query_id"] is not None
            assert row["query_id"].startswith(result.run_id + "-")
    finally:
        repo.close()


def test_duplicate_across_queries_does_not_reassign_query_id(tmp_path: Path) -> None:
    multiget = load_fixture("item_multiget_success.json")
    ids = [entry["body"]["id"] for entry in multiget]
    # Each seed segment gets exactly one page under 100 IDs, so it stops
    # after one page. The second query sees the same IDs → all count as
    # cross-query duplicates.
    first_query_page = _build_search_page(ids[:10], total=10)
    second_query_page = _build_search_page(ids[:10], total=10)

    client = _FakeMercadoLibreClient(
        search_pages=[first_query_page, second_query_page],
        multiget_batches=[multiget[:10]],
        description_body={"plain_text": "x"},
    )

    result = _build_service(tmp_path, client).run()

    assert result.summary["duplicate_ids_across_queries"] >= 10
    repo = IngestionRepository(_config(tmp_path).database_path)
    try:
        rows = list(repo.run_items(result.run_id))
        first_query_id = f"{result.run_id}-0001"
        for row in rows:
            assert row["query_id"] == first_query_id
    finally:
        repo.close()


def test_position_reflects_discovery_order_not_alphabetical_batch(tmp_path: Path) -> None:
    ids = ["MLU200003", "MLU200001", "MLU200002"]
    multiget = [
        {
            "code": 200,
            "body": {
                "id": item_id,
                "category_id": "MLU1743",
                "price": 1000,
                "currency_id": "USD",
                "location": {"state": {"name": "Montevideo"}},
                "attributes": [
                    {"id": "OPERATION", "value_name": "Alquiler"},
                    {"id": "PROPERTY_TYPE", "value_name": "Apartamento"},
                    {"id": "BEDROOMS", "value_name": "1"},
                    {"id": "TOTAL_AREA", "value_name": "50 m2"},
                ],
                "date_created": "2026-08-01T00:00:00Z",
            },
        }
        for item_id in ids
    ]
    empty = _build_search_page([], total=0)
    client = _FakeMercadoLibreClient(
        search_pages=[_build_search_page(ids, total=3), empty, empty, empty],
        multiget_batches=[multiget],
        description_body={"plain_text": "x"},
    )

    result = _build_service(tmp_path, client).run()

    repo = IngestionRepository(_config(tmp_path).database_path)
    try:
        rows = {row["item_id"]: row for row in repo.run_items(result.run_id)}
        # Discovery order: 200003 (pos 1), 200001 (pos 2), 200002 (pos 3).
        # sorted batches would put 200001 first — that MUST NOT be the position.
        assert rows["MLU200003"]["position"] == 1
        assert rows["MLU200001"]["position"] == 2
        assert rows["MLU200002"]["position"] == 3
    finally:
        repo.close()


def test_second_run_preserves_first_seen_at_and_does_not_duplicate_items(tmp_path: Path) -> None:
    multiget = load_fixture("item_multiget_success.json")
    ids = [entry["body"]["id"] for entry in multiget]
    empty = _build_search_page([], total=0)

    def _fresh_client() -> _FakeMercadoLibreClient:
        return _FakeMercadoLibreClient(
            search_pages=[_build_search_page(ids, total=20), empty, empty, empty],
            multiget_batches=[copy.deepcopy(multiget)],
            description_body={"plain_text": "x"},
        )

    first = _build_service(tmp_path, _fresh_client()).run()
    second = _build_service(
        tmp_path,
        _fresh_client(),
        started_at=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
    ).run()

    repo = IngestionRepository(_config(tmp_path).database_path)
    try:
        assert repo.count_items() == 20
        item = repo.item(ids[0])
        assert item is not None
        assert item["first_seen_at"] < item["last_seen_at"]
    finally:
        repo.close()

    assert first.run_id != second.run_id
    assert first.workdir != second.workdir
    assert first.workdir.exists()
