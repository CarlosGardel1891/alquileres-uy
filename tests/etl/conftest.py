"""Shared test helpers for the ETL suite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from alquileres_uy.etl.currency import ExchangeRate, load_exchange_rate

FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures"
ETL_FIXTURE_RUN = FIXTURES_ROOT / "etl" / "raw_run"
EXCHANGE_RATE_EXAMPLE = (
    Path(__file__).resolve().parents[2] / "config" / "exchange_rate.example.json"
)
NEIGHBORHOOD_ALIASES_EXAMPLE = (
    Path(__file__).resolve().parents[2] / "config" / "neighborhood_aliases.json"
)


@pytest.fixture
def etl_fixture_run() -> Path:
    return ETL_FIXTURE_RUN


@pytest.fixture
def exchange_rate() -> ExchangeRate:
    return load_exchange_rate(EXCHANGE_RATE_EXAMPLE)


@pytest.fixture
def exchange_rate_path() -> Path:
    return EXCHANGE_RATE_EXAMPLE


@pytest.fixture
def neighborhood_aliases_path() -> Path:
    return NEIGHBORHOOD_ALIASES_EXAMPLE


def write_fixture_run(
    root: Path, items: list[dict], descriptions: dict[str, dict] | None = None
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    items_dir = root / "items"
    items_dir.mkdir(exist_ok=True)
    (items_dir / "batch_0001.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if descriptions:
        descriptions_dir = root / "descriptions"
        descriptions_dir.mkdir(exist_ok=True)
        for item_id, body in descriptions.items():
            (descriptions_dir / f"{item_id}.json").write_text(
                json.dumps(body, ensure_ascii=False), encoding="utf-8"
            )
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": root.name,
                "source": "mercadolibre",
                "site_id": "MLU",
                "started_at": "2026-08-04T22:00:00Z",
                "finished_at": "2026-08-04T22:10:00Z",
                "status": "completed",
            }
        ),
        encoding="utf-8",
    )
    (root / "ingestion_summary.json").write_text(
        json.dumps({"run_id": root.name, "status": "completed"}), encoding="utf-8"
    )
    return root
