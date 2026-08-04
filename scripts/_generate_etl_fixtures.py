"""One-off script that regenerates the ETL fixtures.

Not part of the production surface; kept in scripts/ so it lives with
the rest of the tooling but is trivial to spot in a review.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def make_item(idx: int, **overrides) -> dict:
    body = {
        "id": f"MLU_TEST_{idx:03d}",
        "title": f"Apartamento en Pocitos {idx}",
        "category_id": "MLU_TEST_APARTMENT",
        "price": 1000 + idx * 100,
        "currency_id": "USD",
        "date_created": f"2026-0{(idx % 6) + 1}-01T09:00:00.000Z",
        "last_updated": f"2026-0{(idx % 6) + 1}-15T10:00:00.000Z",
        "permalink": f"https://articulo.mercadolibre.com.uy/MLU_TEST_{idx:03d}",
        "location": {
            "state": {"name": "Montevideo"},
            "city": {"name": "Pocitos"},
            "neighborhood": {"name": "Pocitos"},
            "latitude": -34.9,
            "longitude": -56.16,
        },
        "attributes": [
            {"id": "OPERATION", "value_id": "242075", "value_name": "Alquiler"},
            {"id": "PROPERTY_TYPE", "value_id": "242060", "value_name": "Apartamento"},
            {"id": "BEDROOMS", "value_name": str((idx % 3) + 1)},
            {"id": "FULL_BATHROOMS", "value_name": "1"},
            {"id": "TOTAL_AREA", "value_name": f"{40 + idx * 2} m2"},
        ],
    }
    body.update(overrides)
    return {"code": 200, "body": body}


def build_items() -> list[dict]:
    items: list[dict] = []
    for i in range(1, 9):
        items.append(make_item(i))

    house = make_item(
        9,
        category_id="MLU_TEST_HOUSE",
        title="Casa amplia",
        attributes=[
            {"id": "OPERATION", "value_id": "242075", "value_name": "Alquiler"},
            {"id": "PROPERTY_TYPE", "value_name": "Casa"},
            {"id": "BEDROOMS", "value_name": "3"},
            {"id": "FULL_BATHROOMS", "value_name": "2"},
            {"id": "TOTAL_AREA", "value_name": "120 m2"},
        ],
    )
    items.append(house)

    uyu = make_item(10, price=40000, currency_id="UYU")
    uyu["body"]["title"] = "Apartamento en Punta Carretas"
    uyu["body"]["location"] = {
        "state": {"name": "Montevideo"},
        "city": {"name": "Punta Carretas"},
        "neighborhood": {"name": "Punta Carretas"},
    }
    items.append(uyu)

    sale = make_item(11)
    sale["body"]["attributes"] = [
        {"id": "OPERATION", "value_name": "Venta"},
        {"id": "PROPERTY_TYPE", "value_name": "Apartamento"},
    ]
    items.append(sale)

    temporal = make_item(12)
    temporal["body"]["attributes"] = [
        {"id": "OPERATION", "value_name": "Alquiler temporal"},
        {"id": "PROPERTY_TYPE", "value_name": "Apartamento"},
    ]
    items.append(temporal)

    outside = make_item(13)
    outside["body"]["location"] = {
        "state": {"name": "Canelones"},
        "city": {"name": "Ciudad de la Costa"},
        "neighborhood": {"name": "Solymar"},
    }
    items.append(outside)

    conflict = make_item(14, category_id="MLU_TEST_HOUSE")
    conflict["body"]["attributes"] = [
        {"id": "OPERATION", "value_id": "242075", "value_name": "Alquiler"},
        {"id": "PROPERTY_TYPE", "value_name": "Apartamento"},
        {"id": "BEDROOMS", "value_name": "2"},
        {"id": "TOTAL_AREA", "value_name": "80 m2"},
    ]
    items.append(conflict)

    unsupported = make_item(15, currency_id="ARS", price=1200000)
    items.append(unsupported)

    zero_ce = make_item(16)
    zero_ce["body"]["attributes"].append(
        {"id": "COMMON_EXPENSES", "value_struct": {"number": 0, "unit": "USD"}, "value_name": "0"}
    )
    items.append(zero_ce)

    inferred_ce = make_item(17, price=45000, currency_id="UYU")
    inferred_ce["body"]["attributes"].append({"id": "COMMON_EXPENSES", "value_name": "5000"})
    items.append(inferred_ce)

    area_bad = make_item(18)
    area_bad["body"]["attributes"] = [
        {"id": "OPERATION", "value_id": "242075", "value_name": "Alquiler"},
        {"id": "PROPERTY_TYPE", "value_name": "Apartamento"},
        {"id": "BEDROOMS", "value_name": "2"},
        {"id": "TOTAL_AREA", "value_name": "50 m2"},
        {"id": "COVERED_AREA", "value_name": "80 m2"},
    ]
    items.append(area_bad)

    only_covered = make_item(19)
    only_covered["body"]["attributes"] = [
        {"id": "OPERATION", "value_id": "242075", "value_name": "Alquiler"},
        {"id": "PROPERTY_TYPE", "value_name": "Apartamento"},
        {"id": "BEDROOMS", "value_name": "2"},
        {"id": "COVERED_AREA", "value_name": "60 m2"},
    ]
    items.append(only_covered)

    unknown = make_item(20)
    unknown["body"]["attributes"].append({"id": "UNKNOWN_ATTR", "value_name": "xyz"})
    items.append(unknown)

    # Possible duplicate of item 1: same neighborhood, bedrooms, buckets.
    dup = make_item(21)
    dup["body"]["title"] = "Apartamento en Pocitos DUPLICADO"
    dup["body"]["price"] = 1100
    dup["body"]["attributes"][2] = {"id": "BEDROOMS", "value_name": "2"}
    dup["body"]["attributes"][4] = {"id": "TOTAL_AREA", "value_name": "42 m2"}
    items.append(dup)

    # Exact-ID duplicate of item 1 with a fresher last_updated.
    dup_id = make_item(1)
    dup_id["body"]["title"] = "Apartamento en Pocitos 1 (re-observed)"
    dup_id["body"]["last_updated"] = "2026-09-15T10:00:00.000Z"
    items.append(dup_id)

    invalid_date = make_item(23)
    invalid_date["body"]["date_created"] = "not-a-date"
    items.append(invalid_date)

    missing_op = make_item(24)
    missing_op["body"]["attributes"] = [
        {"id": "PROPERTY_TYPE", "value_name": "Apartamento"},
        {"id": "BEDROOMS", "value_name": "2"},
        {"id": "TOTAL_AREA", "value_name": "55 m2"},
    ]
    items.append(missing_op)

    no_description = make_item(25)
    items.append(no_description)

    return items


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "etl" / "raw_run"
    items_dir = root / "items"
    descriptions_dir = root / "descriptions"
    items_dir.mkdir(parents=True, exist_ok=True)
    descriptions_dir.mkdir(parents=True, exist_ok=True)

    items = build_items()
    envelope_failures = [
        {"code": 404, "body": {"message": "not found"}},
        {"code": 500, "body": None},
    ]

    batch_1 = items[:15]
    batch_2 = items[15:] + envelope_failures

    (items_dir / "batch_0001.json").write_text(
        json.dumps(batch_1, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (items_dir / "batch_0002.json").write_text(
        json.dumps(batch_2, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    for i in (1, 2, 3):
        body = {
            "plain_text": f"Descripcion del item {i}",
            "text": f"<p>Descripcion del item {i}</p>",
        }
        (descriptions_dir / f"MLU_TEST_{i:03d}.json").write_text(
            json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    file_entries = _describe_files(root)
    manifest = {
        "run_id": "fixture-run-001",
        "source": "mercadolibre",
        "site_id": "MLU",
        "started_at": "2026-08-04T22:00:00Z",
        "finished_at": "2026-08-04T22:15:00Z",
        "status": "completed",
        "application_version": "0.1.0",
        "query_plan_hash": "fixture-hash",
        "config": {"max_items": 5000, "requests_per_second": 2, "timeout_seconds": 20},
        "authentication": {"token_used": False},
        "files": file_entries,
        "summary_path": "ingestion_summary.json",
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    summary = {
        "run_id": "fixture-run-001",
        "status": "completed",
        "data_mode": "fixture",
        "unique_ids_found": len(items),
        "items_downloaded": len(items),
        "descriptions_downloaded": 3,
    }
    (root / "ingestion_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(f"generated {len(items)} items across 2 batches")


def _describe_files(root: Path) -> list[dict[str, str]]:
    """Build manifest.files entries with SHA-256 for every JSON under the run."""
    entries: list[dict[str, str]] = []
    for subdir, kind in (("items", "item_batch"), ("descriptions", "description")):
        for candidate in sorted((root / subdir).glob("*.json")):
            entries.append(
                {
                    "path": f"{subdir}/{candidate.name}",
                    "kind": kind,
                    "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
                }
            )
    return entries


if __name__ == "__main__":
    main()
