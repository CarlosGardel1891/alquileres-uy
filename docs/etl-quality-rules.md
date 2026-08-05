# ETL quality rules

## Currency

- Accepted currencies: `USD`, `UYU`.
- USD passes through unchanged.
- UYU divided by `uyu_per_usd` from the exchange rate configuration.
- Anything else → row rejected with `unsupported_currency`.
- Arithmetic uses `Decimal`; the DataFrame coerces to `float64` on the way out.
- The exchange rate configuration is loaded from a JSON file passed via `--exchange-rate PATH`. The ETL **never** consults an API; the rate is frozen for the run and its path + SHA-256 are recorded in `lineage.json`.

## Common expenses

- Missing → all `common_expenses_*` null, `reported=False`.
- Zero → `reported=True`, values are `0`. Zero and missing are never conflated.
- Amount present but currency missing → the listing's currency is inferred and `common_expenses_currency_inferred=True`.
- Unsupported currency → the listing survives but `common_expenses_usd` is null and a quality issue is recorded.
- `total_monthly_cost_usd = price_usd + common_expenses_usd` when both are non-null. Informational only.

## Areas

- `TOTAL_AREA` preferred. If missing, `COVERED_AREA` is used and `total_area_derived_from_covered=True`.
- If both are present and `covered > total`, no silent swap: a quality issue `covered_area_greater_than_total` is added and the row is excluded from `model_ready`.
- Ranges (`"65-70"`), free-form words (`"sesenta y cinco"`) and other non-numeric strings return null with an `invalid_number` / `invalid_range` reason.

## Dates

- Both `date_created` and `last_updated` parse ISO-8601 with offset. Anything without a timezone is converted to null and flagged with `timezone_missing`. Anything unparseable is null with `invalid_date`.
- A missing `date_created` keeps the row in canonical but excludes it from `model_ready`.

## Scope

- `operation` must resolve to `monthly_rent` from `OPERATION.value_name` or `value_id`; venta, temporal, vacation, short-term, sale → rejected with the matching reason.
- `property_type` must be `apartment` or `house`, resolved via the verified category ID (from the source contract in real mode) or the `PROPERTY_TYPE` attribute. A conflict between the two sources → `property_type_conflict`.
- `department` must equal `Montevideo` after `normalize_key`. The title is never used to fill the location.

## Neighborhoods

- `neighborhood_raw` is preserved.
- `neighborhood_normalized` uses `config/neighborhood_aliases.json`. Unknown neighborhoods are kept with `neighborhood_known=False` — the ETL never invents an alias.
- A missing neighborhood keeps the row in canonical but excludes it from `model_ready`.

## Duplicates

- Same `source_item_id` across runs → deduped down to a single row, keeping the observation with the newest `last_updated`, then newest `last_seen_at`, then lexicographically largest `raw_item_path`. `first_seen_at` is preserved and `observations_count` reflects how many times we saw the ID.
- Same content across different IDs → `exact_content_hash` groups them. **Nothing is deleted**; the hash is a signal for the human review to follow.
- Similar listings across agencies → `possible_duplicate_group_id` with a conservative bucket of price (USD 50) and area (5 m²). Also never deleted; emitted to `duplicate_candidates.parquet` for review.

## Data leakage

- `model_ready.parquet` is closed to any column derived from `price_usd`. `check_model_ready_leakage` runs before the file is written.
- `price_per_m2` and similar metrics live only in the quality report or EDA notebooks.

## Fixture vs. real mode

- Fixture mode marks every output with `data_mode="fixture"` and adds a warning to the quality report. Metrics from fixture runs are **not** project results and must not be published as such.
- Real mode requires `--gate-approval PATH` pointing at a validated `source_gate_approval.json`. Without a valid approval the CLI exits `2` before any Parquet is written.

## Schema failures

- Pandera schemas run before the Parquet files are written. Any violation raises `SchemaErrors` and the CLI exits `1`. No partial output is committed.
