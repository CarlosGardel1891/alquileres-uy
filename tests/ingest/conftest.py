"""Shared testing helpers for the ingestion suite."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest
import requests

from alquileres_uy.ingest.models import ApprovedSourceContract

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "mercadolibre"


def load_fixture(name: str) -> Any:
    path = FIXTURE_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


class FakeResponse:
    """Minimal ``requests.Response`` stand-in for tests."""

    def __init__(
        self,
        *,
        status_code: int = 200,
        json_data: Any = None,
        headers: dict[str, str] | None = None,
        url: str = "https://api.mercadolibre.com/",
    ) -> None:
        self.status_code = status_code
        self._json = json_data
        self.headers = headers or {}
        self.url = url
        self.reason = ""
        self.text = ""

    def json(self) -> Any:
        if self._json is None:
            raise ValueError("no json")
        return self._json


class FakeSession:
    """Deterministic session that pops queued responses on each call.

    Each entry can be a :class:`FakeResponse` or an ``Exception`` instance;
    exceptions are raised as the session would raise them from
    ``requests``. This lets tests script both success and transient
    failure paths.
    """

    def __init__(self, script: Iterable[FakeResponse | Exception]) -> None:
        self._script: list[FakeResponse | Exception] = list(script)
        self.calls: list[dict[str, Any]] = []
        self.headers: dict[str, str] = {}

    def request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> FakeResponse:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "params": params,
                "headers": dict(headers or {}),
                "timeout": timeout,
            }
        )
        if not self._script:
            raise AssertionError(f"unexpected request: {method} {url}")
        entry = self._script.pop(0)
        if isinstance(entry, Exception):
            raise entry
        entry.url = url
        return entry


@pytest.fixture
def make_session():
    """Factory for :class:`FakeSession` from a list of scripted responses."""

    def _factory(script: Iterable[FakeResponse | Exception]) -> FakeSession:
        return FakeSession(script)

    return _factory


@pytest.fixture
def sleep_recorder():
    """Records the delays passed to ``sleep``."""
    recorded: list[float] = []

    def _sleep(seconds: float) -> None:
        recorded.append(seconds)

    return recorded, _sleep


@pytest.fixture
def clock_ticker():
    """Monotonic clock that ticks by 1.0s each call."""
    counter = {"value": 0.0}

    def _clock() -> float:
        counter["value"] += 1.0
        return counter["value"]

    return _clock


@pytest.fixture
def requests_exceptions():
    return requests


def approved_contract(
    *,
    category_ids: dict[str, str] | None = None,
    site_id: str = "MLU",
    source: str = "mercadolibre",
    report_path: str = "/dev/null/coverage.json",
    report_sha256: str = "0" * 64,
) -> ApprovedSourceContract:
    """Build an in-memory contract for tests that don't care about the file."""
    if category_ids is None:
        category_ids = {"apartment": "MLU_TEST_APARTMENT", "house": "MLU_TEST_HOUSE"}
    return ApprovedSourceContract(
        source=source,
        site_id=site_id,
        decision="APPROVED",
        created_at="2026-08-04T17:00:00Z",
        category_ids=dict(category_ids),
        available_filters=["OPERATION", "PROPERTY_TYPE", "BEDROOMS", "price"],
        operation_filter={"mode": "category+attribute"},
        coverage={},
        report_path=report_path,
        report_sha256=report_sha256,
    )
