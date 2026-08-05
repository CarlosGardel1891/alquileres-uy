# Model Artifact Contract (Fase 3)

Every successful training run publishes an atomic directory tree under
`<output-dir>/<timestamp>_<training-run-id[:8]>`. Content is stable so
downstream consumers (this project's future FastAPI image, the offline
review tooling, and CI smoke tests) can rely on it without special-casing
individual files.

## Directory layout

```
<output-dir>/<timestamp>_<run-id>/
├── metrics.json
├── model_selection.json
├── dataset_profile.json
├── split_manifest.json
├── reproducibility.json
├── training_config.json
├── training_summary.json
├── training_lineage.json
├── predictions.parquet
├── worst_errors.csv
├── error_analysis.json
├── models/
│   ├── baseline.json
│   ├── linear.joblib
│   ├── lightgbm.joblib
│   └── torch/          (only when --include-torch)
│       ├── state_dict.pt
│       ├── config.json
│       ├── vocabularies.json
│       ├── numeric_scaler.json
│       └── training_history.json
├── plots/
│   ├── predicted_vs_actual.png
│   ├── feature_importance.png
│   └── residuals.png
└── serving_bundle/
    ├── model.joblib
    ├── metadata.json
    ├── feature_schema.json
    ├── residual_interval.json
    └── checksums.json
```

The whole tree is written to `<final>.tmp` first and renamed at the end
of the run. On any error the tmp is removed; a run never overwrites an
existing directory.

## Serving bundle

`serving_bundle/` corresponds to the `serving_candidate` — never
PyTorch. Files:

* `model.joblib` — the pipeline (preprocessor + estimator) or the
  baseline model.
* `metadata.json` — bundle version, model type, training run id, ETL
  run id, `deployable`, feature list, target, validation/test metrics,
  Python / numpy / pandas / scikit-learn / joblib / (lightgbm) versions,
  git commit, `trained_at`, `input_hashes`, and `model_artifact_sha256`.
* `feature_schema.json` — required and optional fields, allowed
  categorical values, unknown-handling policy, canonical feature
  order; `price_usd` is explicitly excluded.
* `residual_interval.json` — `method="empirical residual quantiles"`
  with the q10 and q90 residuals computed from the serving candidate's
  validation set, plus the observed coverage.
* `checksums.json` — SHA-256 of every other file in the bundle; the
  loader verifies each one before deserializing the model.

Bundle size gate: the total must be under **50 MB**. Otherwise the run
fails, names the largest file, and directs the operator to GitHub
Releases.

## Fixture bundles

Fixture runs still emit a serving bundle for contract testing, but the
metadata always carries `deployable=false`. `load_serving_bundle()`
refuses fixture bundles by default; tests opt in explicitly with
`allow_fixture=True`.

## Runtime compatibility check

`validate_runtime_compatibility(metadata)` compares Python major/minor,
NumPy, pandas, scikit-learn, joblib, and (when the bundle is a LightGBM
one) LightGBM versions between the bundle and the current runtime.
**All of these version fields are required** — a bundle whose metadata
omits any of them is rejected. Any mismatch raises `ServingBundleError`.

**Load order** (`load_serving_bundle`):

1. resolve directory and confirm every required file is present;
2. read `checksums.json`, validate names + hex hashes, verify every
   file's SHA-256;
3. read `metadata.json` and check `bundle_version`, `model_type`,
   `data_mode`, `model_artifact_sha256`;
4. reject fixture bundles unless `allow_fixture=True`;
5. call `validate_runtime_compatibility(metadata)`;
6. **only then** invoke `joblib.load(model.joblib)`.

If any of steps 1–5 fails, `joblib.load` is never reached — verified by
tests that monkey-patch it and assert the call count remains zero.

## Lineage

`training_lineage.json` records SHA-256 of every input consumed and
every output emitted (except itself — `lineage_self_hashed: false`).
Inputs cover `model_ready.parquet`, `etl_summary.json`, ETL
`lineage.json`, `schema.json`. Outputs enumerate every file inside the
training run directory produced before lineage was written.

## Security notes

* `joblib` is used only on artifacts produced by this project. Never
  load a joblib file whose provenance you cannot verify.
* Paths inside artifacts are always relative and inside the training
  run directory.
* Nothing in the artifact tree carries secrets or complete raw data.
* No `pickle.load` on untrusted sources; PyTorch persists via
  `state_dict`, not the pickled module.

## PyTorch exclusion

PyTorch participates in the metric comparison but never in the serving
bundle. The training loop tags the torch model with
`eligible_for_api_serving=false`. The API image (Fase 4) will not
carry a PyTorch wheel, and the bundle builder raises
`ServingBundleError` if asked to package one.
