# Model Training Contract (Fase 3)

Source of truth for how the training pipeline consumes an ETL run and
turns it into a versioned bundle of artifacts. Every rule listed here
is enforced by code and by tests in `tests/models/`.

## Training protocol

**Protocol version: `tune-then-refit-v2`.**

The pipeline runs in strict stages so validation stays out-of-sample:

1. **Tuning stage** — every candidate is fit on the training partition
   only. Ridge picks its alpha on validation MAE; LightGBM tunes its
   grid + `best_iteration` on validation with early stopping; PyTorch
   trains with validation as the early-stopping signal and restores
   the best state; baseline computes its medians on train.
2. **Validation metrics** — computed with the tuning models. These
   metrics are the exclusive input to selection. Nothing peeks at test.
3. **Selection** — see below.
4. **Final refit** — fresh models built with the frozen tuning
   configuration are fit on `train + validation`:
   - baseline: recompute medians on `train + validation`;
   - Ridge: same alpha, new pipeline;
   - LightGBM: same hyperparameters and `n_estimators = best_iteration`,
     no eval_set (test is never observed);
   - PyTorch: fresh vocabularies, scaler and module; same seed and
     architecture; train exactly `final_epochs = best_epoch + 1` epochs.
5. **Test metrics** — computed once from the final models.
6. **Residual interval** — computed on validation using the **tuning**
   model of the serving candidate. The interval therefore reflects the
   out-of-sample error of the model configuration that goes to
   production. The final refit predicts, the tuning residuals bound.
7. **Serving bundle** — contains the *final* serving candidate.
8. **`predictions.parquet`** — includes train / validation / test rows
   for every candidate, with a `model_stage` column identifying which
   object produced each row (`tuning_model` for train + validation,
   `final_refit` for test).

`tuning_model.train_row_count == len(train)`;
`final_model.train_row_count == len(train + validation)`.

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
  * `source_item_id` — every value is a real `str` (not an int, bool,
    bytes or None), non-empty when trimmed, unique across rows;
  * `property_type` — real string, exactly `apartment` or `house`;
  * `neighborhood_normalized` — real string, non-empty when trimmed;
  * `bedrooms` — finite number, non-negative, no nulls;
  * `bathrooms` — **optional column**. When present, non-null values
    must be finite and non-negative; nulls are accepted. When the
    column is absent, the loader injects an all-NaN column internally
    without mutating the Parquet on disk;
  * `total_area_m2`, `price_usd` — finite and strictly greater than zero;
  * `date_created` — timezone-aware (normalized to UTC on load).

Any failure raises `TrainingInputError`. The CLI translates that to
exit code **2** without dumping a stack trace.

## Bathrooms imputation

`bathrooms` is optional at the Parquet level. When the column is
absent, or present with **every value null**, both model families use
the shared fallback described here — never inspecting validation or
test.

* Classical branch (`build_preprocessor`) — `SimpleImputer(
  strategy="median", keep_empty_features=True)` fit on the training
  partition during tuning, and on `train + validation` during the
  final refit. `keep_empty_features=True` preserves the feature slot
  even when the fit frame has no observations for it; sklearn 1.6
  falls back to 0.0 for such columns, matching the shared helper.
* PyTorch branch (`build_torch_vocabularies`) — delegates to
  `resolve_numeric_imputation_values`:
  - if at least one observation exists in the fit frame → use its
    **median** (`imputation_sources = "fit_frame_median"`);
  - if every value is null → use the constant **0.0**
    (`imputation_sources = "constant_fallback_no_observed_values"`).
  The chosen value is stored in `numeric_impute_values`;
  standardisation statistics are computed on the already-imputed
  series so training and inference see the same distribution. When
  the column is entirely missing, `mean = 0.0` and `std = 1.0`.

`numeric_impute_values` and `imputation_sources` are exported in
`vocabularies.json` and `numeric_scaler.json` for the torch model.

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

## Selection

* **best_overall_model** — smallest validation MAE across every trained
  candidate (torch included). Ties break by validation MAPE, then by
  model name. **Simplicity does not affect best-overall.**
* **serving_candidate** — restricted to the classical models
  (`baseline / linear / lightgbm`). Anchored to the smallest eligible
  MAE: the practical-tie set is every model whose MAE is within
  `SERVING_TIE_TOLERANCE = 5 USD` of that anchor. The simplest model
  inside the practical-tie set wins (`baseline < linear < lightgbm`).
  No chained tie logic — a model outside the tolerance from the
  anchor cannot become the serving candidate even if it is inside the
  tolerance of some intermediate model.

Test metrics never influence selection. `model_selection.json` records
`best_eligible_mae`, `practical_tie_threshold`, `practical_tie_models`,
`simplicity_order`, and the reason each excluded model was left out.

## Predictions and residual semantics

Convention: `residual = actual - predicted`.
Therefore `absolute_error_usd = abs(residual)` and
`percentage_error = absolute_error_usd / actual` — always ≥ 0.

`predictions.parquet` contains one row per publication × model × split
across train / validation / test. The `model_stage` column identifies
which object produced each row: `tuning_model` for train + validation,
`final_refit` for test.

`worst_errors.csv` contains only test rows produced by the final refit
of the serving candidate, sorted by `absolute_error_usd` descending.

## Reproducibility

`set_global_seed(seed, include_torch=…)` seeds Python `random`, NumPy
and (optionally) PyTorch. LightGBM inherits `deterministic=True`.
`reproducibility.json` records seed, versions, thread counts,
determinism flags, git commit, platform, split algorithm version, and
training protocol version. Two runs with the same seed and
configuration produce identical split id-hashes, hyperparameters,
serving candidate, and validation metrics within tolerance.

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
