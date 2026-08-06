"""End-to-end orchestration of the training pipeline.

Protocol (contract-first, no test leakage):

1. **Tuning stage** — every candidate is fit on the training partition
   only. Baseline uses the train medians; Ridge picks its alpha on
   validation; LightGBM tunes its grid + best_iteration on validation;
   PyTorch trains with validation as early-stopping signal and
   restores the best state. Nothing peeks at test.
2. **Validation metrics** — computed with the tuning models. These
   metrics are the exclusive input to selection.
3. **Selection** — best_overall (MAE, MAPE, name) across all four
   candidates; serving_candidate anchored to the smallest eligible MAE
   with the simplest model chosen inside the practical-tie tolerance.
4. **Final refit** — fresh models built with the frozen tuning
   configuration are fit on ``train + validation``. Test is never
   observed during fitting.
5. **Test metrics** — computed once from the final models.
6. **Residual interval** — computed on validation using the tuning
   model of the serving candidate, so the interval stays out-of-sample.
7. **Serving bundle** — contains the *final* serving candidate.
8. **Predictions.parquet** — includes train / validation / test for
   every candidate, with a ``model_stage`` column identifying which
   object produced each row.

Output layout under ``<output-dir>/<timestamp>_<training-run-id[:8]>``:

    metrics.json
    model_selection.json
    dataset_profile.json
    split_manifest.json
    reproducibility.json
    training_config.json
    training_summary.json
    training_lineage.json
    predictions.parquet
    worst_errors.csv
    error_analysis.json
    models/
        baseline.json
        linear.joblib
        lightgbm.joblib
        torch/         (only when --include-torch)
    plots/
        predicted_vs_actual.png
        feature_importance.png
        residuals.png
    serving_bundle/
        model.joblib
        metadata.json
        feature_schema.json
        residual_interval.json
        checksums.json
"""

from __future__ import annotations

import hashlib
import logging
import os
import platform
import random
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")  # headless before any pyplot import
import matplotlib.pyplot as plt

from .artifacts import (
    artifact_size,
    atomic_run_directory,
    iter_files,
    sha256_file,
    write_json,
)
from .baseline import refit_baseline, tune_baseline
from .config import (
    CATEGORICAL_FEATURES,
    CLASSICAL_MODEL_NAMES,
    FEATURE_COLUMNS,
    MODELS_DIRNAME,
    NUMERIC_FEATURES,
    PLOTS_DIRNAME,
    SERVING_BUNDLE_DIRNAME,
    TARGET_COLUMN,
    TRAINING_PROTOCOL_VERSION,
    TrainingConfig,
)
from .contracts import (
    TrainingInputError,
    check_training_leakage,
    load_etl_approval,
    load_training_input,
)
from .lightgbm_model import refit_lightgbm, tune_lightgbm
from .linear import refit_linear, tune_linear
from .metrics import compute_metrics
from .selection import SERVING_TIE_TOLERANCE, select_models
from .serving import build_serving_bundle, compute_residual_interval
from .split import temporal_split

_LOGGER = logging.getLogger(__name__)

FIXTURE_WARNING = "FIXTURE DATA — NOT PROJECT RESULTS"


@dataclass
class TrainingResult:
    training_run_id: str
    output_dir: Path
    status: str
    data_mode: str
    serving_candidate: str
    best_overall: str
    metrics: dict[str, dict[str, Any]]


def set_global_seed(seed: int, *, include_torch: bool = False) -> None:
    random.seed(seed)
    np.random.seed(seed)
    os.environ.setdefault("PYTHONHASHSEED", str(seed))
    if include_torch:
        try:
            import torch

            torch.manual_seed(seed)
        except ImportError:
            pass  # caller handles the missing-torch case


def dry_run(config: TrainingConfig) -> dict[str, Any]:
    training_input = load_training_input(config.etl_run_dir)
    approval = None
    if not config.fixture_mode:
        approval = load_etl_approval(config.etl_approval_path, training_input)  # type: ignore[arg-type]
    _ensure_mode_matches(config, training_input)
    plan = _plan_split(training_input.model_ready, config)
    check_training_leakage(FEATURE_COLUMNS)
    torch_available = _torch_available()
    if config.include_torch and not torch_available:
        raise TrainingInputError(
            "PyTorch is not installed. Install requirements-torch-cpu.txt "
            "before requesting --include-torch."
        )
    return {
        "status": "dry-run-ok",
        "data_mode": training_input.data_mode,
        "etl_run_id": training_input.etl_run_id,
        "input_hashes": training_input.input_hashes,
        "models_planned": list(_planned_models(config)),
        "features": {"numeric": list(NUMERIC_FEATURES), "categorical": list(CATEGORICAL_FEATURES)},
        "split_plan": plan,
        "torch_requested": config.include_torch,
        "torch_available": torch_available,
        "approval_valid": approval is not None,
    }


def run(config: TrainingConfig) -> TrainingResult:
    training_input = load_training_input(config.etl_run_dir)
    approval_hash: str | None = None
    if not config.fixture_mode:
        load_etl_approval(config.etl_approval_path, training_input)  # type: ignore[arg-type]
        approval_hash = _sha256_of(config.etl_approval_path)  # type: ignore[arg-type]
    _ensure_mode_matches(config, training_input)

    if config.include_torch and not _torch_available():
        raise TrainingInputError(
            "PyTorch is not installed. Install requirements-torch-cpu.txt "
            "before requesting --include-torch."
        )

    set_global_seed(config.seed, include_torch=config.include_torch)

    started_at = datetime.now(tz=UTC)
    training_run_id = uuid.uuid4().hex  # distinct from etl_run_id
    timestamp = started_at.strftime("%Y-%m-%dT%H%M%SZ")
    final_dir = Path(config.output_dir) / f"{timestamp}_{training_run_id[:8]}"

    split = temporal_split(
        training_input.model_ready,
        train_fraction=config.train_fraction,
        validation_fraction=config.validation_fraction,
        test_fraction=config.test_fraction,
    )
    train_validation = pd.concat([split.train, split.validation], ignore_index=True)

    # ---- Stage A — tuning models (train only) --------------------------
    tuning_models: dict[str, Any] = {}
    tuning_models["baseline"] = tune_baseline(
        split.train, data_mode=training_input.data_mode, input_hashes=training_input.input_hashes
    )
    tuning_models["linear"] = tune_linear(
        split.train,
        split.validation,
        target_column=TARGET_COLUMN,
        alphas=config.ridge_alphas,
    )
    tuning_models["lightgbm"] = tune_lightgbm(
        split.train, split.validation, target_column=TARGET_COLUMN, seed=config.seed
    )
    if config.include_torch:
        from .torch_model import tune_torch_model

        tuning_models["torch"] = tune_torch_model(
            split.train,
            split.validation,
            target_column=TARGET_COLUMN,
            seed=config.seed,
            max_epochs=config.max_epochs,
            patience=config.patience,
            batch_size=config.torch_batch_size,
        )

    # ---- Stage B — validation metrics from tuning models --------------
    val_target = split.validation[TARGET_COLUMN].astype(float).to_numpy()
    validation_metrics: dict[str, dict[str, float]] = {}
    tuning_validation_predictions: dict[str, np.ndarray] = {}
    for name, tuning_model in tuning_models.items():
        pred = tuning_model.predict(split.validation)
        tuning_validation_predictions[name] = pred
        validation_metrics[name] = compute_metrics(val_target, pred).as_json()
    baseline_val_mae = validation_metrics["baseline"]["mae_usd"]
    for name in validation_metrics:
        validation_metrics[name]["improvement_vs_baseline"] = _improvement(
            baseline_val_mae, validation_metrics[name]["mae_usd"]
        )

    # ---- Stage B — selection (before any final refit) -----------------
    selection = select_models(validation_metrics, data_mode=training_input.data_mode)

    # ---- Stage C — final refits on train + validation -----------------
    final_models: dict[str, Any] = {}
    final_models["baseline"] = refit_baseline(
        train_validation,
        data_mode=training_input.data_mode,
        input_hashes=training_input.input_hashes,
    )
    final_models["linear"] = refit_linear(
        train_validation,
        target_column=TARGET_COLUMN,
        tuning_model=tuning_models["linear"],
    )
    final_models["lightgbm"] = refit_lightgbm(
        train_validation,
        target_column=TARGET_COLUMN,
        seed=config.seed,
        tuning_model=tuning_models["lightgbm"],
    )
    if config.include_torch:
        from .torch_model import refit_torch_model

        final_models["torch"] = refit_torch_model(
            train_validation,
            target_column=TARGET_COLUMN,
            seed=config.seed,
            batch_size=config.torch_batch_size,
            tuning_model=tuning_models["torch"],
        )

    # ---- Stage D — test metrics from final models ---------------------
    test_target = split.test[TARGET_COLUMN].astype(float).to_numpy()
    test_metrics: dict[str, dict[str, float]] = {}
    for name, final in final_models.items():
        pred = final.predict(split.test)
        test_metrics[name] = compute_metrics(test_target, pred).as_json()
    baseline_test_mae = test_metrics["baseline"]["mae_usd"]
    for name in test_metrics:
        test_metrics[name]["improvement_vs_baseline"] = _improvement(
            baseline_test_mae, test_metrics[name]["mae_usd"]
        )

    # ---- Residual interval — validation, tuning serving candidate ----
    residual_interval = compute_residual_interval(
        val_target,
        tuning_validation_predictions[selection.serving_candidate],
        data_mode=training_input.data_mode,
    )

    with atomic_run_directory(final_dir) as tmp_dir:
        models_dir = tmp_dir / MODELS_DIRNAME
        models_dir.mkdir()
        plots_dir = tmp_dir / PLOTS_DIRNAME
        plots_dir.mkdir()

        # Persist the final models — never the tuning ones.
        final_models["baseline"].save(models_dir / "baseline.json")
        final_models["linear"].save(models_dir / "linear.joblib")
        final_models["lightgbm"].save(models_dir / "lightgbm.joblib")
        if "torch" in final_models:
            final_models["torch"].save(models_dir / "torch")

        deployable = training_input.data_mode == "real"
        serving_final = final_models[selection.serving_candidate]
        bundle_dir = tmp_dir / SERVING_BUNDLE_DIRNAME
        build_serving_bundle(
            bundle_dir,
            model_name=selection.serving_candidate,
            model_object=serving_final,
            validation_metrics=validation_metrics[selection.serving_candidate],
            test_metrics=test_metrics[selection.serving_candidate],
            residual_interval=residual_interval,
            training_run_id=training_run_id,
            etl_run_id=training_input.etl_run_id,
            data_mode=training_input.data_mode,
            input_hashes=training_input.input_hashes,
            git_commit=_git_commit(),
            trained_at=started_at.isoformat(),
        )

        predictions_frames: list[pd.DataFrame] = []
        for name, tuning_model in tuning_models.items():
            predictions_frames.append(
                _predictions_frame(
                    split.train,
                    "train",
                    name,
                    tuning_model.predict(split.train),
                    stage="tuning_model",
                )
            )
            predictions_frames.append(
                _predictions_frame(
                    split.validation,
                    "validation",
                    name,
                    tuning_validation_predictions[name],
                    stage="tuning_model",
                )
            )
        for name, final in final_models.items():
            predictions_frames.append(
                _predictions_frame(
                    split.test,
                    "test",
                    name,
                    final.predict(split.test),
                    stage="final_refit",
                )
            )

        _write_predictions(predictions_frames, tmp_dir / "predictions.parquet")
        _write_worst_errors_and_analysis(
            predictions_frames, tmp_dir, serving=selection.serving_candidate
        )
        _write_metrics_json(tmp_dir, training_input, validation_metrics, test_metrics)
        _write_selection_json(tmp_dir, selection, deployable=deployable)
        _write_split_manifest(tmp_dir, split, config)
        _write_dataset_profile(tmp_dir, training_input, split)
        _write_reproducibility(tmp_dir, config, training_input)
        _write_training_config_json(
            tmp_dir,
            config=config,
            training_input=training_input,
            training_run_id=training_run_id,
        )
        _generate_plots(
            plots_dir, split, tuning_models, final_models, selection, training_input.data_mode
        )

        finished_at = datetime.now(tz=UTC)
        _write_training_summary(
            tmp_dir,
            training_run_id=training_run_id,
            data_mode=training_input.data_mode,
            started_at=started_at,
            finished_at=finished_at,
            seed=config.seed,
            etl_run_id=training_input.etl_run_id,
            models=list(final_models.keys()),
            serving_candidate=selection.serving_candidate,
            best_overall=selection.best_overall_model,
            row_counts={
                "train": len(split.train),
                "validation": len(split.validation),
                "test": len(split.test),
                "train_validation": len(train_validation),
            },
            tuning_row_count=len(split.train),
            final_refit_row_count=len(train_validation),
            artifact_dir=tmp_dir,
        )
        _write_training_lineage(
            tmp_dir,
            training_input=training_input,
            training_run_id=training_run_id,
            approval_hash=approval_hash,
        )

    _LOGGER.info(
        "training complete: training_run_id=%s etl_run_id=%s serving=%s output=%s",
        training_run_id,
        training_input.etl_run_id,
        selection.serving_candidate,
        final_dir,
    )
    return TrainingResult(
        training_run_id=training_run_id,
        output_dir=final_dir,
        status="completed",
        data_mode=training_input.data_mode,
        serving_candidate=selection.serving_candidate,
        best_overall=selection.best_overall_model,
        metrics={"validation": validation_metrics, "test": test_metrics},
    )


# ---- internals ------------------------------------------------------


def _planned_models(config: TrainingConfig) -> list[str]:
    plan = list(CLASSICAL_MODEL_NAMES)
    if config.include_torch:
        plan.append("torch")
    return plan


def _ensure_mode_matches(config: TrainingConfig, training_input) -> None:
    if config.fixture_mode and training_input.data_mode != "fixture":
        raise TrainingInputError(
            "--fixture-mode requires an ETL run with data_mode='fixture'; refusing to mix modes"
        )
    if not config.fixture_mode and training_input.data_mode != "real":
        raise TrainingInputError("real training run requires an ETL run with data_mode='real'")


def _plan_split(frame: pd.DataFrame, config: TrainingConfig) -> dict[str, Any]:
    split = temporal_split(
        frame,
        train_fraction=config.train_fraction,
        validation_fraction=config.validation_fraction,
        test_fraction=config.test_fraction,
    )
    return {
        "rows": {
            "train": len(split.train),
            "validation": len(split.validation),
            "test": len(split.test),
        },
        "cutoffs": {
            "train_to_validation": split.train_cutoff.isoformat(),
            "validation_to_test": split.validation_cutoff.isoformat(),
        },
    }


def _torch_available() -> bool:
    try:
        import torch  # noqa: F401

        return True
    except ImportError:
        return False


def _predictions_frame(
    frame: pd.DataFrame, split_name: str, model_name: str, pred: np.ndarray, *, stage: str
) -> pd.DataFrame:
    result = frame[
        [
            "source_item_id",
            "date_created",
            "property_type",
            "neighborhood_normalized",
            "bedrooms",
            "total_area_m2",
            TARGET_COLUMN,
        ]
    ].copy()
    if "bathrooms" in frame.columns:
        result["bathrooms"] = frame["bathrooms"].values
    else:
        result["bathrooms"] = pd.NA
    result["split"] = split_name
    result["model_name"] = model_name
    result["model_stage"] = stage
    result["predicted_price_usd"] = pred.astype(float)
    result = result.rename(columns={TARGET_COLUMN: "actual_price_usd"})
    # Contract convention: residual = actual - predicted.
    result["residual"] = result["actual_price_usd"] - result["predicted_price_usd"]
    result["absolute_error_usd"] = result["residual"].abs()
    with np.errstate(divide="ignore", invalid="ignore"):
        result["percentage_error"] = np.where(
            result["actual_price_usd"] > 0,
            result["absolute_error_usd"] / result["actual_price_usd"],
            np.nan,
        )
    return result


def _write_predictions(frames: list[pd.DataFrame], path: Path) -> None:
    combined = pd.concat(frames, ignore_index=True)
    combined["date_created"] = pd.to_datetime(combined["date_created"], utc=True)
    combined.to_parquet(path, engine="pyarrow", compression="zstd", index=False)


def _write_worst_errors_and_analysis(
    frames: list[pd.DataFrame], root: Path, *, serving: str
) -> None:
    combined = pd.concat(frames, ignore_index=True)
    test_serving = combined[
        (combined["split"] == "test")
        & (combined["model_name"] == serving)
        & (combined["model_stage"] == "final_refit")
    ].copy()
    top10 = test_serving.sort_values("absolute_error_usd", ascending=False).head(10)
    top10.to_csv(root / "worst_errors.csv", index=False)

    def _bucket(area: float) -> str:
        if area < 40:
            return "<40"
        if area < 60:
            return "40-60"
        if area < 90:
            return "60-90"
        return ">=90"

    top10 = top10.copy()
    top10["area_bucket"] = top10["total_area_m2"].astype(float).map(_bucket)
    analysis = {
        "note": "Synthetic fixture behavior only; no market conclusion can be drawn.",
        "row_count": int(len(top10)),
        "by_neighborhood": top10.groupby("neighborhood_normalized").size().to_dict(),
        "by_property_type": top10.groupby("property_type").size().to_dict(),
        "by_area_bucket": top10.groupby("area_bucket").size().to_dict(),
        "by_bedrooms": {
            int(k): int(v) for k, v in top10.groupby("bedrooms").size().to_dict().items()
        },
        "actual_price_min": float(top10["actual_price_usd"].min()) if not top10.empty else None,
        "actual_price_max": float(top10["actual_price_usd"].max()) if not top10.empty else None,
    }
    write_json(root / "error_analysis.json", analysis)


def _write_metrics_json(root: Path, training_input, validation: dict, test: dict) -> None:
    payload: dict[str, Any] = {
        "data_mode": training_input.data_mode,
        "etl_run_id": training_input.etl_run_id,
        "protocol": {
            "training_protocol_version": TRAINING_PROTOCOL_VERSION,
            "validation_source": "tuning_model",
            "test_source": "final_refit",
        },
        "models": {
            name: {"validation": validation[name], "test": test[name]} for name in validation
        },
    }
    if training_input.data_mode == "fixture":
        payload["warning"] = FIXTURE_WARNING
    write_json(root / "metrics.json", payload)


def _write_selection_json(root: Path, selection, *, deployable: bool) -> None:
    write_json(root / "model_selection.json", selection.as_json(deployable=deployable))


def _write_split_manifest(root: Path, split, config: TrainingConfig) -> None:
    write_json(
        root / "split_manifest.json",
        split.as_manifest(
            seed=config.seed,
            train_fraction=config.train_fraction,
            validation_fraction=config.validation_fraction,
            test_fraction=config.test_fraction,
        ),
    )


def _write_dataset_profile(root: Path, training_input, split) -> None:
    frame = training_input.model_ready
    profile = {
        "data_mode": training_input.data_mode,
        "total_rows": int(len(frame)),
        "row_counts": {
            "train": int(len(split.train)),
            "validation": int(len(split.validation)),
            "test": int(len(split.test)),
        },
        "date_range": {
            "min": pd.Timestamp(frame["date_created"].min()).isoformat(),
            "max": pd.Timestamp(frame["date_created"].max()).isoformat(),
        },
        "date_range_by_split": {
            "train": {
                "min": pd.Timestamp(split.train["date_created"].min()).isoformat(),
                "max": pd.Timestamp(split.train["date_created"].max()).isoformat(),
            },
            "validation": {
                "min": pd.Timestamp(split.validation["date_created"].min()).isoformat(),
                "max": pd.Timestamp(split.validation["date_created"].max()).isoformat(),
            },
            "test": {
                "min": pd.Timestamp(split.test["date_created"].min()).isoformat(),
                "max": pd.Timestamp(split.test["date_created"].max()).isoformat(),
            },
        },
        "target_stats": {
            "min": float(frame[TARGET_COLUMN].min()),
            "max": float(frame[TARGET_COLUMN].max()),
            "median": float(frame[TARGET_COLUMN].median()),
            "mean": float(frame[TARGET_COLUMN].mean()),
            "p10": float(np.quantile(frame[TARGET_COLUMN].astype(float), 0.1)),
            "p90": float(np.quantile(frame[TARGET_COLUMN].astype(float), 0.9)),
        },
        "missingness": {column: int(frame[column].isnull().sum()) for column in frame.columns},
        "property_type_counts": frame["property_type"].value_counts().to_dict(),
        "neighborhood_counts": frame["neighborhood_normalized"].value_counts().to_dict(),
        "unknown_neighborhoods_in_test": sorted(
            set(split.test["neighborhood_normalized"].unique())
            - set(split.train["neighborhood_normalized"].unique())
        ),
        "unknown_neighborhoods_in_validation": sorted(
            set(split.validation["neighborhood_normalized"].unique())
            - set(split.train["neighborhood_normalized"].unique())
        ),
        "id_hashes": {
            "train": _hash_of(tuple(split.train["source_item_id"])),
            "validation": _hash_of(tuple(split.validation["source_item_id"])),
            "test": _hash_of(tuple(split.test["source_item_id"])),
        },
    }
    if training_input.data_mode == "fixture":
        profile["warning"] = FIXTURE_WARNING
    write_json(root / "dataset_profile.json", profile)


def _write_reproducibility(root: Path, config: TrainingConfig, training_input) -> None:
    import sklearn

    payload = {
        "seed": config.seed,
        "training_protocol_version": TRAINING_PROTOCOL_VERSION,
        "split_algorithm_version": "temporal-grouped-v1",
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "versions": {
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
            "matplotlib": matplotlib.__version__,
        },
        "thread_counts": {
            "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS"),
            "MKL_NUM_THREADS": os.environ.get("MKL_NUM_THREADS"),
        },
        "determinism_flags": {
            "pytorch_use_deterministic_algorithms": False,
            "lightgbm_deterministic": True,
            "n_jobs": 1,
        },
        "git_commit": _git_commit(),
        "known_nondeterministic_operations": [
            "PyTorch embedding backward on CPU may vary in the last decimal places",
        ],
    }
    try:
        import lightgbm

        payload["versions"]["lightgbm"] = lightgbm.__version__
    except ImportError:
        pass
    if config.include_torch:
        try:
            import torch

            payload["versions"]["torch"] = torch.__version__
        except ImportError:
            pass
    write_json(root / "reproducibility.json", payload)


def _write_training_config_json(
    root: Path,
    *,
    config: TrainingConfig,
    training_input,
    training_run_id: str,
) -> None:
    payload = {
        "training_run_id": training_run_id,
        "training_protocol_version": TRAINING_PROTOCOL_VERSION,
        "data_mode": training_input.data_mode,
        "seed": config.seed,
        "include_torch": config.include_torch,
        "fractions": {
            "train": config.train_fraction,
            "validation": config.validation_fraction,
            "test": config.test_fraction,
        },
        "max_epochs": config.max_epochs,
        "patience": config.patience,
        "torch_batch_size": config.torch_batch_size,
        "ridge_alphas": list(config.ridge_alphas),
        "lightgbm_grid": [
            {"learning_rate": 0.05, "num_leaves": 15, "min_child_samples": 5},
            {"learning_rate": 0.1, "num_leaves": 15, "min_child_samples": 5},
            {"learning_rate": 0.05, "num_leaves": 31, "min_child_samples": 3},
            {"learning_rate": 0.1, "num_leaves": 31, "min_child_samples": 3},
        ],
        "features": {
            "numeric": list(NUMERIC_FEATURES),
            "categorical": list(CATEGORICAL_FEATURES),
        },
        "target": TARGET_COLUMN,
        "split_algorithm_version": "temporal-grouped-v1",
        "serving_tie_tolerance_usd": SERVING_TIE_TOLERANCE,
    }
    write_json(root / "training_config.json", payload)


def _generate_plots(
    directory, split, tuning_models, final_models, selection, data_mode: str
) -> None:
    directory.mkdir(exist_ok=True)
    y_true = split.test[TARGET_COLUMN].astype(float).to_numpy()

    fig, ax = plt.subplots(figsize=(7, 5))
    for name, model in final_models.items():
        pred = model.predict(split.test)
        ax.scatter(y_true, pred, s=14, alpha=0.6, label=name)
    limits = [float(min(y_true.min(), 0)), float(y_true.max()) * 1.1]
    ax.plot(limits, limits, color="black", linewidth=1, linestyle="--")
    ax.set_xlabel("Actual price (USD)")
    ax.set_ylabel("Predicted price (USD)")
    prefix = f"{data_mode} — " + ("FIXTURE — NOT PROJECT RESULTS" if data_mode == "fixture" else "")
    ax.set_title(f"Predicted vs Actual (test, final refit) [{prefix.strip(' —')}]")
    ax.legend()
    fig.tight_layout()
    fig.savefig(directory / "predicted_vs_actual.png", dpi=100)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    serving = final_models[selection.serving_candidate]
    if selection.serving_candidate == "lightgbm":
        importance = serving.feature_importance
        names = list(importance.keys())
        values = [importance[n] for n in names]
        order = np.argsort(values)[::-1][:15]
        ax.barh(np.array(names)[order][::-1], np.array(values)[order][::-1])
        ax.set_xlabel("Gain")
    elif selection.serving_candidate == "linear":
        summary = serving.coefficients_summary()
        pairs = sorted(summary["coefficients"], key=lambda c: abs(c["coefficient"]), reverse=True)[
            :15
        ]
        ax.barh([p["feature"] for p in pairs][::-1], [abs(p["coefficient"]) for p in pairs][::-1])
        ax.set_xlabel("|coefficient|")
    else:
        keys = list(serving.combined_ppm2.keys())[:12]
        ax.barh(keys, [serving.combined_ppm2[k] for k in keys])
        ax.set_xlabel("Median price per m² (train + validation)")
    ax.set_title(f"Feature importance ({selection.serving_candidate}) [{data_mode}]")
    fig.tight_layout()
    fig.savefig(directory / "feature_importance.png", dpi=100)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    pred = serving.predict(split.test)
    # Contract convention: residual = actual - predicted.
    residual = y_true - pred
    ax.scatter(pred, residual, s=14, alpha=0.6)
    ax.axhline(0, color="black", linewidth=1, linestyle="--")
    ax.set_xlabel("Prediction (USD)")
    ax.set_ylabel("Residual: actual - predicted (USD)")
    ax.set_title(f"Residuals (test, final refit) [{data_mode}]")
    fig.tight_layout()
    fig.savefig(directory / "residuals.png", dpi=100)
    plt.close(fig)


def _write_training_summary(
    root: Path,
    *,
    training_run_id: str,
    data_mode: str,
    started_at: datetime,
    finished_at: datetime,
    seed: int,
    etl_run_id: str,
    models: list[str],
    serving_candidate: str,
    best_overall: str,
    row_counts: dict[str, int],
    tuning_row_count: int,
    final_refit_row_count: int,
    artifact_dir: Path,
) -> Path:
    payload = {
        "training_run_id": training_run_id,
        "etl_run_id": etl_run_id,
        "training_protocol_version": TRAINING_PROTOCOL_VERSION,
        "status": "completed",
        "data_mode": data_mode,
        "seed": seed,
        "models_ran": models,
        "serving_candidate": serving_candidate,
        "best_overall_model": best_overall,
        "row_counts": row_counts,
        "tuning_row_count": tuning_row_count,
        "final_refit_row_count": final_refit_row_count,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": (finished_at - started_at).total_seconds(),
        "artifact_count": sum(1 for _ in iter_files(artifact_dir)),
        "artifact_total_bytes": artifact_size(artifact_dir),
    }
    if data_mode == "fixture":
        payload["warning"] = FIXTURE_WARNING
    path = root / "training_summary.json"
    write_json(path, payload)
    return path


def _write_training_lineage(
    root: Path,
    *,
    training_input,
    training_run_id: str,
    approval_hash: str | None,
) -> None:
    inputs: dict[str, str | None] = {
        "model_ready": training_input.input_hashes.get("model_ready"),
        "etl_summary": training_input.input_hashes.get("etl_summary"),
        "etl_lineage": training_input.input_hashes.get("lineage"),
        "etl_schema": training_input.input_hashes.get("schema"),
        "training_config": sha256_file(root / "training_config.json"),
    }
    if training_input.data_mode == "real":
        inputs["etl_approval"] = approval_hash
    outputs: dict[str, str] = {}
    for path in iter_files(root):
        if path.name == "training_lineage.json":
            continue
        outputs[str(path.relative_to(root)).replace("\\", "/")] = sha256_file(path)
    payload = {
        "training_run_id": training_run_id,
        "etl_run_id": training_input.etl_run_id,
        "training_protocol_version": TRAINING_PROTOCOL_VERSION,
        "data_mode": training_input.data_mode,
        "inputs_sha256": inputs,
        "outputs_sha256": outputs,
        "lineage_self_hashed": False,
    }
    if training_input.data_mode == "fixture":
        payload["warning"] = FIXTURE_WARNING
    write_json(root / "training_lineage.json", payload)


def _improvement(baseline_mae: float, model_mae: float) -> float:
    if baseline_mae <= 0:
        return 0.0
    return (baseline_mae - model_mae) / baseline_mae


def _git_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
        if completed.returncode == 0:
            return completed.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _hash_of(ids: tuple[str, ...]) -> str:
    return hashlib.sha256("\n".join(str(x) for x in ids).encode("utf-8")).hexdigest()


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "FIXTURE_WARNING",
    "TrainingResult",
    "dry_run",
    "run",
    "set_global_seed",
]
