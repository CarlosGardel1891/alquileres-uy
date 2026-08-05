"""Generate a deterministic synthetic ETL run for model training tests.

The real ETL fixture (``tests/fixtures/etl/raw_run``) yields only ~17
model-ready rows, which is far too small to exercise four model
families. This helper writes a 240-row synthetic ``model_ready.parquet``
that follows the exact Fase 2 output contract (same columns and dtypes)
plus the sibling contract files (``etl_summary.json``, ``schema.json``,
``lineage.json``). The training pipeline validates this fixture through
the same loader used for real ETL outputs.

The dataset is designed to give the learned models room to improve over
the baseline while keeping the target explainable: price is driven by
neighborhood/property_type intercepts, a per-neighborhood price per m2,
bedrooms and bathrooms uplifts, plus a small deterministic noise term.
A handful of validation/test rows carry categories that never appear in
training so ``handle_unknown="ignore"`` gets exercised end-to-end.

Fixture status is stamped on every artifact:

* ``etl_summary.json`` / ``lineage.json`` → ``data_mode: fixture``.
* Warning line printed on stdout when run manually.

**FIXTURE DATA — NOT PROJECT RESULTS.**
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "models" / "etl_run"
SCHEMA_VERSION = "1.0.0"
SEED = 20260805
ROWS = 240

NEIGHBORHOODS_TRAIN = [
    "Pocitos",
    "Cordón",
    "Centro",
    "Punta Carretas",
    "Malvín",
    "Buceo",
    "Parque Batlle",
]
NEIGHBORHOODS_UNKNOWN = ["Carrasco Norte", "Bella Vista"]
PROPERTY_TYPES = ["apartment", "house"]

NEIGHBORHOOD_INTERCEPT = {
    "Pocitos": 22.0,
    "Cordón": 14.0,
    "Centro": 12.0,
    "Punta Carretas": 24.0,
    "Malvín": 18.0,
    "Buceo": 16.0,
    "Parque Batlle": 20.0,
    "Carrasco Norte": 26.0,
    "Bella Vista": 15.0,
}
PROPERTY_INTERCEPT = {"apartment": 0.0, "house": -3.0}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_frame(seed: int, rows: int) -> pd.DataFrame:
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)

    start = datetime(2025, 1, 1, tzinfo=UTC)
    days_span = 300

    records: list[dict] = []
    for i in range(rows):
        # Reserve the very last ~10% of rows for unknown categories so
        # they land squarely in the test partition after the temporal
        # split.
        use_unknown = i >= int(rows * 0.9) and i % 3 == 0
        neighborhood = (
            rng.choice(NEIGHBORHOODS_UNKNOWN) if use_unknown else rng.choice(NEIGHBORHOODS_TRAIN)
        )
        property_type = rng.choices(PROPERTY_TYPES, weights=[0.75, 0.25])[0]
        bedrooms = rng.choices([1, 2, 3, 4], weights=[0.15, 0.5, 0.25, 0.1])[0]
        area = float(np_rng.normal(loc=50 + bedrooms * 12, scale=6))
        area = max(20.0, round(area, 1))
        # 20% of bathrooms are missing to exercise the imputer.
        bathrooms = (
            None if rng.random() < 0.2 else rng.choices([1, 2, 3], weights=[0.4, 0.5, 0.1])[0]
        )

        ppm2 = (
            NEIGHBORHOOD_INTERCEPT[neighborhood]
            + PROPERTY_INTERCEPT[property_type]
            + (bedrooms - 2) * 0.6
            + (0 if bathrooms is None else (bathrooms - 1) * 1.1)
        )
        noise = float(np_rng.normal(loc=0.0, scale=0.6))
        price = max(150.0, round((ppm2 + noise) * area, 2))

        day_offset = int((i / rows) * days_span) + rng.randint(0, 2)
        date_created = start + timedelta(days=day_offset)
        records.append(
            {
                "source_item_id": f"MLU_FIX_{i:04d}",
                "property_type": property_type,
                "neighborhood_normalized": neighborhood,
                "bedrooms": bedrooms,
                "total_area_m2": area,
                "price_usd": price,
                "date_created": date_created,
                "bathrooms": bathrooms,
            }
        )
    df = pd.DataFrame(records)
    df["source_item_id"] = df["source_item_id"].astype("string").astype("object")
    df["property_type"] = df["property_type"].astype("object")
    df["neighborhood_normalized"] = df["neighborhood_normalized"].astype("object")
    df["bedrooms"] = df["bedrooms"].astype("Int64")
    df["bathrooms"] = pd.array(df["bathrooms"].tolist(), dtype="Int64")
    df["total_area_m2"] = df["total_area_m2"].astype("Float64")
    df["price_usd"] = df["price_usd"].astype("Float64")
    df["date_created"] = pd.to_datetime(df["date_created"], utc=True)
    # Sort by date_created + source_item_id so the fixture is byte-stable.
    df = df.sort_values(["date_created", "source_item_id"]).reset_index(drop=True)
    return df


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    df.to_parquet(path, engine="pyarrow", compression="zstd", index=False)


def _write_json(path: Path, payload: dict) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)
    path.write_bytes((text + "\n").encode("utf-8"))


def _build_schema() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "model_ready_required": [
            "source_item_id",
            "property_type",
            "neighborhood_normalized",
            "bedrooms",
            "total_area_m2",
            "price_usd",
            "date_created",
        ],
        "model_ready_forbidden": [
            "price_per_m2",
            "price_bucket",
            "total_monthly_cost_usd",
        ],
        "canonical_columns": [
            "source_item_id",
            "property_type",
            "neighborhood_normalized",
            "bedrooms",
            "bathrooms",
            "total_area_m2",
            "price_usd",
            "date_created",
        ],
    }


def _build_summary(model_ready_rows: int) -> dict:
    return {
        "status": "completed",
        "data_mode": "fixture",
        "etl_run_id": "fixture-model-run-001",
        "schema_version": SCHEMA_VERSION,
        "input_runs": 1,
        "input_items": model_ready_rows,
        "canonical_items": model_ready_rows,
        "model_ready_items": model_ready_rows,
        "rejected_items": 0,
        "duplicate_candidates": 0,
        "started_at": "2026-01-01T00:00:00Z",
        "finished_at": "2026-01-01T00:05:00Z",
        "duration_seconds": 300.0,
        "strict": False,
        "warning": "FIXTURE DATA — NOT PROJECT RESULTS",
    }


def _build_lineage(root: Path, summary_hash: str, schema_hash: str, parquet_hash: str) -> dict:
    return {
        "data_mode": "fixture",
        "etl_run_id": "fixture-model-run-001",
        "etl_schema_version": SCHEMA_VERSION,
        "application_version": "0.1.0",
        "started_at": "2026-01-01T00:00:00Z",
        "finished_at": "2026-01-01T00:05:00Z",
        "lineage_self_hashed": False,
        "warning": "FIXTURE DATA — NOT PROJECT RESULTS",
        "input_runs": [
            {
                "run_directory_name": "synthetic",
                "run_id": "synthetic-run-001",
                "source": "mercadolibre",
                "item_batch_count": 0,
                "description_count": 0,
            }
        ],
        "output_files": {
            "model_ready": "model_ready.parquet",
            "etl_summary": "etl_summary.json",
            "schema": "schema.json",
        },
        "output_sha256": {
            "model_ready": parquet_hash,
            "etl_summary": summary_hash,
            "schema": schema_hash,
        },
        "row_counts": {"model_ready": ROWS},
    }


def generate(target: Path = FIXTURE_DIR, seed: int = SEED, rows: int = ROWS) -> None:
    target.mkdir(parents=True, exist_ok=True)
    df = _build_frame(seed, rows)

    parquet_path = target / "model_ready.parquet"
    _write_parquet(df, parquet_path)
    parquet_hash = _sha256(parquet_path)

    schema_path = target / "schema.json"
    _write_json(schema_path, _build_schema())
    schema_hash = _sha256(schema_path)

    summary_path = target / "etl_summary.json"
    _write_json(summary_path, _build_summary(len(df)))
    summary_hash = _sha256(summary_path)

    lineage_path = target / "lineage.json"
    _write_json(lineage_path, _build_lineage(target, summary_hash, schema_hash, parquet_hash))

    print(
        json.dumps(
            {
                "target": str(target),
                "rows": len(df),
                "unique_dates": int(df["date_created"].nunique()),
                "sha256": {
                    "model_ready.parquet": parquet_hash,
                    "etl_summary.json": summary_hash,
                    "schema.json": schema_hash,
                    "lineage.json": _sha256(lineage_path),
                },
                "warning": "FIXTURE DATA — NOT PROJECT RESULTS",
            },
            indent=2,
            sort_keys=True,
        )
    )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=FIXTURE_DIR)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--rows", type=int, default=ROWS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    generate(args.output_dir, args.seed, args.rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
