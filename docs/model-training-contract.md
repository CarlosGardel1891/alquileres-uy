# Model Training Contract (Fase 3)

This document is the source of truth for how the training pipeline
consumes an ETL run and turns it into a versioned bundle of artifacts.
Every rule listed here is enforced by code and by tests in
`tests/models/`.

## Input contract

The pipeline reads a single ETL run directory (`--etl-run-dir PATH`)
and requires four files at the top level:

```
model_ready.parquet
etl_summary.json
lineage.json
schema.json
```

`alquileres_uy.models.contracts.load_training_input()` validates:

* `etl_summary.status == "completed"`;
* `etl_summary.data_mode ∈ {"fixture", "real"}`;
* `etl_summary.etl_run_id` non-empty; `schema_version` ∈ supported list;
* `etl_summary.input_items / canonical_items / model_ready_items ≥ 0`;
* `etl_summary.started_at / finished_at` are ISO-8601 with an explicit tz;
* `lineage.etl_run_id / data_mode / etl_schema_version` match `etl_summary`;
* `lineage.output_files.model_ready == "model_ready.parquet"`;
* `lineage.output_sha256.{model_ready, etl_summary, schema}` match the
  real SHA-256 of each file on disk;
* every `lineage.output_files` path is relative and inside the run;
* `schema.json.schema_version` matches; required columns include
  `source_item_id, property_type, neighborhood_normalized, bedrooms,
  total_area_m2, price_usd, date_created`;
* the Parquet passes the model-ready data contract:
  strings non-empty and unique for `source_item_id`; `property_type ∈
  {apartment, house}`; `neighborhood_normalized` non-null; `bedrooms`
  numeric and non-negative; `bathrooms` (optional) non-negative; area
  and price finite and strictly positive; `date_created` tz-aware
  (normalized to UTC on load).

Any failure raises `TrainingInputError`. The CLI translates that to
exit code **2** without dumping a stack trace.

## Real-mode approval

Real training requires `--etl-approval PATH` pointing to an
`etl_production_approval.json` file with the exact shape:

```json
{
  "status": "ETL_PRODUCTION_VALIDATED",
  "data_mode": "real",
  "etl_run_id": "…",
  "etl_summary_sha256": "…",
  "lineage_sha256": "…",
  "model_ready_sha256": "…",
  "approved_at": "ISO-8601 tz-aware",
  "approved_by": "…"
}
```

`load_etl_approval()` re-hashes the three files and refuses to proceed
unless every hash matches. A real approval against a fixture ETL run
(or vice-versa) is rejected. Real mode without `--etl-approval` exits
2 immediately — no output directory, no model training, no PyTorch
import.

`config/etl_production_approval.example.json` ships as documentation
only and is not a valid approval (all placeholder hashes).

## Features and target

* Target: `price_usd`.
* Numeric features: `bedrooms`, `bathrooms`, `total_area_m2`.
* Categorical features: `neighborhood_normalized`, `property_type`.
* `date_created` is used exclusively for the temporal split.
* `source_item_id` is used exclusively for lineage.

`check_training_leakage(feature_columns)` rejects any of the forbidden
columns: `price_usd, price_per_m2, price_bucket,
total_monthly_cost_usd, source_item_id, date_created`. It runs inside
every model at fit time — a regression that adds a forbidden feature
fails the pytest suite before the model can be trained.

## Temporal split (no shuffle)

Algorithm (`split.temporal_split`, version `temporal-grouped-v1`):

1. Sort rows by `date_created` then `source_item_id`.
2. Group by unique timestamps.
3. Assign whole groups to train (~70%), validation (~15%), test (~15%).
4. Enforce:
   * `max(train.date_created) < min(validation.date_created)`;
   * `max(validation.date_created) < min(test.date_created)`;
   * no `source_item_id` appears in more than one partition;
   * at least three unique timestamps overall.

`split_manifest.json` is emitted with strategy/algorithm version, seed,
requested and actual fractions, row counts, per-split date ranges,
cutoffs, per-split id-hashes, plus explicit `shuffle=false` and
`same_timestamp_kept_together=true` flags.

## Models

| Model     | Family                        | Serialization           | Serving eligible |
| --------- | ----------------------------- | ----------------------- | ---------------- |
| baseline  | median price per m² (by group)| `baseline.json`         | yes              |
| linear    | Ridge (sklearn Pipeline)       | `linear.joblib`         | yes              |
| lightgbm  | LightGBMRegressor              | `lightgbm.joblib`       | yes              |
| torch     | Embedding + MLP (SmoothL1)     | `torch/state_dict.pt` + JSON side-cars | **no** — architecture decision |

* Ridge tunes `alpha ∈ {0.1, 1.0, 10.0}` on validation MAE, then refits
  on train + validation with the winning alpha.
* LightGBM uses a fixed 4-cell grid (`learning_rate`, `num_leaves`,
  `min_child_samples`) with `n_jobs=1`, `deterministic=True`, early
  stopping on validation, then refits on train + validation with the
  winning `best_iteration`.
* PyTorch runs on CPU only, seeds `random / numpy / torch`, uses Adam
  + SmoothL1Loss, `num_workers=0`, and early stopping on validation
  MAE. State is restored to the best epoch. Serialization uses
  `state_dict` + JSON side-cars (never a pickle).

## Metrics

`metrics.compute_metrics` returns MAE (USD), RMSE (USD), MAPE
(fraction and percent), and rows. Targets must be strictly positive;
zero/negative targets are rejected rather than hidden behind an
epsilon. `improvement_vs_baseline = (baseline_mae - model_mae) /
baseline_mae`.

## Selection

`selection.select_models` picks two different models:

* **best_overall_model** — smallest validation MAE across the four
  candidates (torch included).
* **serving_candidate** — smallest validation MAE among the classical
  models only (baseline, linear, lightgbm). If a simpler model is
  within `SERVING_TIE_TOLERANCE = 5 USD` of the current best, we
  prefer the simpler one. `model_selection.json` records the criterion
  and the reason each excluded model was left out.

Fixture bundles always ship `deployable=false` and
`blocked_reason="fixture training run"`.

## Reproducibility

`set_global_seed(seed, include_torch=…)` seeds Python `random`, NumPy
and (optionally) PyTorch. LightGBM inherits `deterministic=True`.
`reproducibility.json` records seed, versions, thread counts,
determinism flags, git commit, platform and the split algorithm
version. Two runs with the same seed and configuration produce
identical split id-hashes, hyperparameters, serving candidate, and
metrics within tolerance.

## Failure modes

| Situation                                    | Exit |
| -------------------------------------------- | ---- |
| Missing/invalid ETL contract                 | 2    |
| Wrong hash in `lineage.json`                 | 2    |
| Real mode without `--etl-approval`           | 2    |
| Fixture mode with `--etl-approval`           | 2    |
| Mode mismatch (fixture ETL + real training)  | 2    |
| `--include-torch` without torch installed    | 2    |
| Successful training or dry-run               | 0    |
| Anything else                                | 1    |

Errors of type `TrainingInputError`, `TrainingConfigError`,
`SplitError`, and `ServingBundleError` all map to exit 2 and are logged
without stack traces.
