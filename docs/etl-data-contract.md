# ETL data contract (Fase 2)

The ETL turns raw MercadoLibre responses (as persisted by the Fase 1 ingestion) into four Parquet datasets plus JSON metadata. This document is the authoritative contract for those outputs.

- `ETL_SCHEMA_VERSION = "1.0.0"`
- Written to disk under `data/processed/<timestamp>_<etl-run-id>/`
- Every field in every dataset comes from `src/alquileres_uy/etl/models.CANONICAL_COLUMN_ORDER` (canonical) or a documented derivative

## `listings.parquet` — canonical dataset

One row per unique `(source, source_item_id)`. Rows that fail the scope gate (operation, property type, department, price, currency) go to `rejected_listings.parquet` instead. Individual optional fields may be null, so downstream code cannot assume completeness — see `model_ready.parquet` for the stricter subset.

Column order is fixed by `CANONICAL_COLUMN_ORDER`. Highlights:

| Column | Type | Notes |
| --- | --- | --- |
| `schema_version` | string | Always `"1.0.0"` for this fase. |
| `data_mode` | string | `fixture` or `real`. Bit-for-bit propagated from the CLI. |
| `source` | string | `"mercadolibre"`. |
| `source_run_id` | string | The Fase 1 `run_id`. |
| `source_item_id` | string | Primary key. |
| `raw_item_path` | string | `<run>/items/batch_XXXX.json` relative to the run root. |
| `raw_description_path` | string \| null | Relative path to the description JSON, or null. |
| `operation` | string | Always `"monthly_rent"` after acceptance. |
| `property_type` | string | `"apartment"` or `"house"`. |
| `department` | string | Always `"Montevideo"` after acceptance. |
| `neighborhood_raw` | string \| null | Original neighborhood as MELI returned it, cleaned. |
| `neighborhood_normalized` | string \| null | Canonical name via `config/neighborhood_aliases.json`. |
| `neighborhood_known` | bool | `true` when a canonical alias was found. |
| `price_original` / `currency_original` / `price_usd` | Decimal→float64 / string / float64 | See §3 for the conversion. |
| `common_expenses_*` | mixed | See §4. |
| `total_monthly_cost_usd` | float64 | Informational only. **Never** used as ML input. |
| `exchange_rate_uyu_per_usd` / `exchange_rate_date` / `exchange_rate_source` | scalar | Frozen from the exchange rate file for this run. |
| `possible_duplicate_group_id` | string \| null | Bucketed key (§7). |
| `exact_content_hash` | string \| null | SHA-256 fingerprint (§7). |
| `quality_issues` | string | JSON array of `{field, code, detail}` per row. |
| `first_seen_at` / `last_seen_at` / `observations_count` | timestamp / timestamp / int | Preserved across runs. |

## `model_ready.parquet` — training-ready dataset

Strictly required columns: `source_item_id`, `property_type`, `neighborhood_normalized`, `bedrooms`, `total_area_m2`, `price_usd`, `date_created`. Additional allowed column: `bathrooms` (nullable). No other columns are permitted.

The following are **forbidden** and enforced by `check_model_ready_leakage`:

- `price_per_m2`
- `price_bucket`
- `total_monthly_cost_usd`
- Any other feature derived from `price_usd`

`price_per_m2` may appear in the quality report or EDA, never in `model_ready.parquet`.

## `rejected_listings.parquet` — every rejected row

One row per rejected input envelope, with the exact `rejection_reasons` (pipe-separated codes). Column order:

`source_item_id`, `source_run_id`, `raw_item_path`, `rejection_reasons`, `raw_category_id`, `raw_currency`, `raw_price`, `raw_operation`, `raw_property_type`.

Reason codes are the ones in `src/alquileres_uy/etl/pipeline.py` and the source-scope helpers:

`missing_item_id`, `invalid_item_envelope`, `sale`, `temporary_rental`, `wrong_operation`, `missing_operation`, `wrong_property_type`, `property_type_conflict`, `outside_montevideo`, `missing_location`, `missing_price`, `invalid_price`, `unsupported_currency`.

## `duplicate_candidates.parquet` — conservative near-duplicate groups

Emitted alongside the canonical dataset. Groups have at least two members and share the bucketed key `(property_type, neighborhood_normalized, bedrooms, total_area_m2 // 5, price_usd // 50)`. No row is removed from the canonical dataset. This file is advisory input for future manual review, not an automatic dedup.

## Sidecar JSON

- `etl_summary.json` — top-level counts and duration for the run.
- `data_quality_report.json` — rejection breakdown, missingness, distributions, unmapped attributes, area inconsistencies, common-expenses missingness. In fixture mode a `warning` field is added.
- `unmapped_attributes.json` — `{attribute_id: count}` for every MELI attribute not covered by `ATTRIBUTE_MAP`.
- `lineage.json` — inputs, exchange rate, alias file, output paths (relative names only, never absolute), row counts, SHA-256 digests, `application_version`, `data_mode`. Never contains tokens.
- `schema.json` — snapshot of `ETL_SCHEMA_VERSION`, `CANONICAL_COLUMN_ORDER`, `MODEL_READY_REQUIRED_COLUMNS`, `MODEL_READY_FORBIDDEN_COLUMNS`.

## Non-negotiables

- No feature derived from `price_usd` is ever placed in `model_ready.parquet`.
- Raw run files are read-only for the ETL. The pipeline never modifies `data/raw/**` in place.
- Fixture outputs are labelled `data_mode = "fixture"` and their metrics are **not** project results.
- Real outputs require a valid Fase 1 `source_gate_approval.json`; without it the CLI exits with `2` and writes nothing.
