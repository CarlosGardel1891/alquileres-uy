"""Tests for the MercadoLibre source gate."""

from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from alquileres_uy.ingest.config import IngestionConfig
from alquileres_uy.ingest.errors import AuthenticationError
from alquileres_uy.ingest.models import SourceGateDecision
from alquileres_uy.ingest.source_gate import run_source_gate

from .conftest import FakeResponse, load_fixture


class _StubClient:
    """Handwritten stub with the four methods the gate needs."""

    def __init__(
        self,
        search_handler: Callable[[str, dict[str, Any] | None], FakeResponse],
        items_response: FakeResponse | None = None,
        description_response: FakeResponse | Exception | None = None,
    ) -> None:
        self._search_handler = search_handler
        self._items_response = items_response
        self._description_response = description_response
        self.search_calls: list[tuple[str, dict[str, Any] | None]] = []
        self.description_calls: list[str] = []

    def search_items(self, site_id: str, params: dict[str, Any] | None = None) -> FakeResponse:
        self.search_calls.append((site_id, params))
        return self._search_handler(site_id, params)

    def get_items(self, item_ids):
        if self._items_response is None:
            raise AssertionError("no items response configured")
        return self._items_response

    def get_item_description(self, item_id: str) -> FakeResponse:
        self.description_calls.append(item_id)
        if isinstance(self._description_response, Exception):
            raise self._description_response
        if self._description_response is None:
            raise AssertionError("no description response configured")
        return self._description_response


def _successful_search() -> FakeResponse:
    return FakeResponse(json_data=load_fixture("search_success.json"))


def _successful_multiget() -> FakeResponse:
    return FakeResponse(json_data=load_fixture("item_multiget_success.json"))


def _description() -> FakeResponse:
    return FakeResponse(json_data=load_fixture("description_success.json"))


def _config(tmp_path: Path, token: str | None = None) -> IngestionConfig:
    return IngestionConfig(
        output_dir=tmp_path / "raw",
        database_path=tmp_path / "ingestion.sqlite",
        access_token=token,
    )


def test_source_gate_approved_with_full_fixtures(tmp_path: Path) -> None:
    client = _StubClient(
        search_handler=lambda site_id, params: _successful_search(),
        items_response=_successful_multiget(),
        description_response=_description(),
    )
    workdir = tmp_path / "gate"

    report, artifacts = run_source_gate(_config(tmp_path), client, workdir)

    assert report.decision is SourceGateDecision.APPROVED
    assert report.sample_size == 20
    assert artifacts.search_no_auth is not None
    assert artifacts.items_batch is not None
    assert artifacts.coverage is not None
    assert (workdir / "coverage.json").exists()


def test_source_gate_rejected_when_essential_fields_missing(tmp_path: Path) -> None:
    payload = load_fixture("item_multiget_success.json")
    stripped = copy.deepcopy(payload)
    for entry in stripped:
        entry["body"]["attributes"] = []
        entry["body"].pop("location", None)
    client = _StubClient(
        search_handler=lambda site_id, params: _successful_search(),
        items_response=FakeResponse(json_data=stripped),
        description_response=_description(),
    )

    report, _ = run_source_gate(_config(tmp_path), client, tmp_path / "gate")

    assert report.decision is SourceGateDecision.REJECTED


def test_source_gate_inconclusive_when_search_lacks_results(tmp_path: Path) -> None:
    empty = {
        "site_id": "MLU",
        "paging": {"total": 0, "offset": 0, "limit": 20},
        "results": [],
        "available_filters": [],
    }
    client = _StubClient(
        search_handler=lambda site_id, params: FakeResponse(json_data=empty),
        items_response=None,
        description_response=None,
    )

    report, _ = run_source_gate(_config(tmp_path), client, tmp_path / "gate")

    assert report.decision is SourceGateDecision.INCONCLUSIVE
    assert report.sample_size == 0


def test_source_gate_marks_token_used_when_401_retry_succeeds(tmp_path: Path) -> None:
    call_counter = {"n": 0}

    def _search(site_id: str, params: dict[str, Any] | None) -> FakeResponse:
        call_counter["n"] += 1
        if call_counter["n"] == 1:
            raise AuthenticationError(401, "unauthorized", url="/sites/MLU/search")
        return _successful_search()

    client = _StubClient(
        search_handler=_search,
        items_response=_successful_multiget(),
        description_response=_description(),
    )

    report, _ = run_source_gate(_config(tmp_path, token="tok"), client, tmp_path / "gate")

    assert call_counter["n"] == 2
    assert report.token_used is True
    assert report.decision is SourceGateDecision.APPROVED


def test_source_gate_stays_token_free_when_no_token_available(tmp_path: Path) -> None:
    def _search(site_id: str, params: dict[str, Any] | None) -> FakeResponse:
        raise AuthenticationError(401, "unauthorized", url="/sites/MLU/search")

    client = _StubClient(
        search_handler=_search,
        items_response=None,
        description_response=None,
    )

    report, _ = run_source_gate(_config(tmp_path, token=None), client, tmp_path / "gate")

    assert report.token_used is False
    assert report.decision is SourceGateDecision.INCONCLUSIVE
    assert any("no MELI_ACCESS_TOKEN" in note for note in report.notes)


def test_source_gate_records_description_coverage(tmp_path: Path) -> None:
    client = _StubClient(
        search_handler=lambda site_id, params: _successful_search(),
        items_response=_successful_multiget(),
        description_response=_description(),
    )

    report, _ = run_source_gate(_config(tmp_path), client, tmp_path / "gate")

    assert report.description_coverage.total == 20
    assert report.description_coverage.present == 20


@pytest.mark.parametrize("missing_field", ["price"])
def test_source_gate_reports_partial_coverage(tmp_path: Path, missing_field: str) -> None:
    payload = load_fixture("item_multiget_success.json")
    weakened = copy.deepcopy(payload)
    for entry in weakened[:5]:
        entry["body"].pop(missing_field, None)
    client = _StubClient(
        search_handler=lambda site_id, params: _successful_search(),
        items_response=FakeResponse(json_data=weakened),
        description_response=_description(),
    )

    report, _ = run_source_gate(_config(tmp_path), client, tmp_path / "gate")

    assert report.essential_coverage[missing_field].present == 15
    assert report.decision is SourceGateDecision.REJECTED
