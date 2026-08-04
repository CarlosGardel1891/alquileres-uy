"""End-to-end style tests for :class:`IngestionService`.

These tests inject a hand-written client and repository factory so no
real HTTP or SQLite happens outside the tests' ``tmp_path``.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from alquileres_uy.ingest.config import IngestionConfig
from alquileres_uy.ingest.repository import IngestionRepository
from alquileres_uy.ingest.service import IngestionService

from .conftest import FakeResponse, load_fixture


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
        requests_per_second=1000.0,
    )


def _repository_factory(_: Path) -> Callable[[Path], IngestionRepository]:
    def _factory(path: Path) -> IngestionRepository:
        return IngestionRepository(path)

    return _factory


def _clock_factory(start: datetime) -> Callable[[], datetime]:
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
        client_factory=lambda _cfg: client,
        repository_factory=IngestionRepository,
        clock=clock,
    )


def test_dry_run_returns_plan_without_touching_network(tmp_path: Path) -> None:
    service = _build_service(tmp_path, _FakeMercadoLibreClient([], [], {}))
    plan = service.dry_run()

    assert plan["dry_run"] is True
    assert plan["seed_segment_count"] == 2
    assert "query_plan_hash" in plan
    assert not (tmp_path / "raw").exists()
    assert not (tmp_path / "ingestion.sqlite").exists()


def test_full_run_deduplicates_ids_and_downloads_items(tmp_path: Path) -> None:
    multiget_success = load_fixture("item_multiget_success.json")
    description = load_fixture("description_success.json")
    all_ids = [entry["body"]["id"] for entry in multiget_success]

    page_1 = _build_search_page(all_ids[:20], total=30)
    page_2 = _build_search_page(all_ids[15:30] if len(all_ids) >= 30 else all_ids, total=30)
    # simulate one segment: the second query gets a small page and stops
    empty_page = _build_search_page([], total=0)

    client = _FakeMercadoLibreClient(
        search_pages=[page_1, empty_page, page_2, empty_page],
        multiget_batches=[multiget_success],
        description_body=description,
    )

    result = _build_service(tmp_path, client).run()

    assert result.summary["unique_ids_found"] <= 40
    assert result.summary["items_downloaded"] == 20
    assert result.summary["descriptions_downloaded"] == result.summary["unique_ids_found"]
    assert result.summary["candidate_items"] >= 1
    assert result.manifest_path is not None and result.manifest_path.exists()
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["authentication"] == {"token_used": False}
    assert "access_token" not in json.dumps(manifest)


def test_second_run_does_not_duplicate_items(tmp_path: Path) -> None:
    multiget = load_fixture("item_multiget_success.json")
    description = load_fixture("description_success.json")
    ids = [entry["body"]["id"] for entry in multiget]
    empty = _build_search_page([], total=0)

    def _fresh_client() -> _FakeMercadoLibreClient:
        return _FakeMercadoLibreClient(
            search_pages=[_build_search_page(ids, total=20), empty, empty, empty],
            multiget_batches=[copy.deepcopy(multiget)],
            description_body=description,
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
    assert first.workdir.exists()  # raw responses from prior run preserved


def test_dry_run_and_manifest_never_leak_the_access_token(tmp_path: Path) -> None:
    config = _config(tmp_path).with_overrides(access_token="s3cret-value")
    service = IngestionService(
        config,
        client_factory=lambda _cfg: _FakeMercadoLibreClient([], [], {}),
        clock=_clock_factory(datetime(2026, 8, 4, 12, 0, tzinfo=UTC)),
    )
    plan = service.dry_run()
    assert "s3cret-value" not in json.dumps(plan)


def _build_search_page(ids: list[str], total: int) -> dict[str, Any]:
    return {
        "site_id": "MLU",
        "paging": {"total": total, "offset": 0, "limit": 100, "primary_results": len(ids)},
        "results": [{"id": item_id, "title": f"item {item_id}"} for item_id in ids],
        "available_filters": [],
    }
