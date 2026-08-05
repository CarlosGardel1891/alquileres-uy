"""LightGBM regressor with tuning + final refit separation.

* :func:`tune_lightgbm` fits every grid cell on **train only**, feeding
  validation solely as ``eval_set`` for early stopping and MAE
  comparison. The returned tuning model is the winning configuration
  still fit on train alone.
* :func:`refit_lightgbm` builds a new pipeline with the tuning
  hyperparameters and ``n_estimators=best_iteration``, then fits on
  ``train + validation`` **without** any eval_set (test is never
  observed).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

from .features import build_preprocessor, feature_frame, resolve_feature_names

LIGHTGBM_MODEL_VERSION: str = "1.0.0"


def _grid() -> list[dict]:
    """A tiny, fixed 4-cell grid to keep training deterministic and fast."""
    return [
        {"learning_rate": 0.05, "num_leaves": 15, "min_child_samples": 5},
        {"learning_rate": 0.1, "num_leaves": 15, "min_child_samples": 5},
        {"learning_rate": 0.05, "num_leaves": 31, "min_child_samples": 3},
        {"learning_rate": 0.1, "num_leaves": 31, "min_child_samples": 3},
    ]


@dataclass(frozen=True)
class LightGBMModel:
    pipeline: Pipeline
    hyperparameters: dict
    feature_names: tuple[str, ...]
    best_iteration: int
    validation_mae_by_config: list[dict]
    feature_importance: dict[str, float]
    train_row_count: int
    stage: str  # "tuning" or "final"
    version: str = LIGHTGBM_MODEL_VERSION

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        prediction = self.pipeline.predict(feature_frame(frame))
        return np.clip(prediction, a_min=0.0, a_max=None)

    def save(self, path: Path) -> Path:
        joblib.dump({"pipeline": self.pipeline, "metadata": self._metadata()}, path)
        return path

    @classmethod
    def load(cls, path: Path) -> LightGBMModel:
        payload = joblib.load(path)
        metadata = payload["metadata"]
        return cls(
            pipeline=payload["pipeline"],
            hyperparameters=dict(metadata["hyperparameters"]),
            feature_names=tuple(metadata["feature_names"]),
            best_iteration=int(metadata["best_iteration"]),
            validation_mae_by_config=list(metadata["validation_mae_by_config"]),
            feature_importance={
                str(k): float(v) for k, v in metadata["feature_importance"].items()
            },
            train_row_count=int(metadata["train_row_count"]),
            stage=str(metadata.get("stage", "final")),
            version=str(metadata.get("version", LIGHTGBM_MODEL_VERSION)),
        )

    def _metadata(self) -> dict:
        return {
            "hyperparameters": dict(self.hyperparameters),
            "feature_names": list(self.feature_names),
            "best_iteration": self.best_iteration,
            "validation_mae_by_config": list(self.validation_mae_by_config),
            "feature_importance": dict(self.feature_importance),
            "train_row_count": self.train_row_count,
            "stage": self.stage,
            "version": self.version,
        }


def tune_lightgbm(
    train_frame: pd.DataFrame,
    validation_frame: pd.DataFrame,
    *,
    target_column: str,
    seed: int,
) -> LightGBMModel:
    """Grid-search LightGBM on train + validation and return the tuning model."""
    train_features = feature_frame(train_frame)
    validation_features = feature_frame(validation_frame)
    train_target = (
        pd.to_numeric(train_frame[target_column], errors="coerce").astype(float).to_numpy()
    )
    validation_target = (
        pd.to_numeric(validation_frame[target_column], errors="coerce").astype(float).to_numpy()
    )

    tuning_results: list[dict] = []
    best_config: dict | None = None
    best_pipeline: Pipeline | None = None
    best_mae = float("inf")
    best_iteration = 100
    for candidate_hp in _grid():
        pipeline = Pipeline(
            steps=[
                ("preprocess", build_preprocessor()),
                (
                    "lightgbm",
                    lgb.LGBMRegressor(
                        objective="regression_l1",
                        random_state=seed,
                        n_jobs=1,
                        n_estimators=500,
                        deterministic=True,
                        verbose=-1,
                        **candidate_hp,
                    ),
                ),
            ]
        )
        preprocessor = pipeline.named_steps["preprocess"]
        preprocessor.fit(train_features)
        train_matrix = preprocessor.transform(train_features)
        validation_matrix = preprocessor.transform(validation_features)
        estimator = pipeline.named_steps["lightgbm"]
        estimator.fit(
            train_matrix,
            train_target,
            eval_set=[(validation_matrix, validation_target)],
            eval_metric="l1",
            callbacks=[
                lgb.early_stopping(stopping_rounds=15, verbose=False),
                lgb.log_evaluation(0),
            ],
        )
        best_iter = int(getattr(estimator, "best_iteration_", None) or estimator.n_estimators)
        prediction = np.clip(estimator.predict(validation_matrix), a_min=0.0, a_max=None)
        mae = float(np.mean(np.abs(prediction - validation_target)))
        tuning_results.append(
            {"config": candidate_hp, "validation_mae": mae, "best_iteration": best_iter}
        )
        if mae < best_mae:
            best_mae = mae
            best_config = candidate_hp
            best_pipeline = pipeline
            best_iteration = best_iter

    if best_config is None or best_pipeline is None:
        raise ValueError("LightGBM tuning produced no valid model")

    feature_names = tuple(resolve_feature_names(best_pipeline.named_steps["preprocess"]))
    booster = best_pipeline.named_steps["lightgbm"].booster_
    importance_values = booster.feature_importance(importance_type="gain")
    feature_importance = {
        str(name): float(value)
        for name, value in zip(feature_names, importance_values, strict=False)
    }
    return LightGBMModel(
        pipeline=best_pipeline,
        hyperparameters=dict(best_config),
        feature_names=feature_names,
        best_iteration=int(best_iteration),
        validation_mae_by_config=tuning_results,
        feature_importance=feature_importance,
        train_row_count=int(len(train_frame)),
        stage="tuning",
    )


def refit_lightgbm(
    train_validation_frame: pd.DataFrame,
    *,
    target_column: str,
    seed: int,
    tuning_model: LightGBMModel,
) -> LightGBMModel:
    """Refit LightGBM with the tuning HP/best_iteration on train + validation."""
    features = feature_frame(train_validation_frame)
    target = (
        pd.to_numeric(train_validation_frame[target_column], errors="coerce")
        .astype(float)
        .to_numpy()
    )
    final_pipeline = Pipeline(
        steps=[
            ("preprocess", build_preprocessor()),
            (
                "lightgbm",
                lgb.LGBMRegressor(
                    objective="regression_l1",
                    random_state=seed,
                    n_jobs=1,
                    n_estimators=tuning_model.best_iteration,
                    deterministic=True,
                    verbose=-1,
                    **tuning_model.hyperparameters,
                ),
            ),
        ]
    )
    final_pipeline.fit(features, target)
    feature_names = tuple(resolve_feature_names(final_pipeline.named_steps["preprocess"]))
    booster = final_pipeline.named_steps["lightgbm"].booster_
    importance_values = booster.feature_importance(importance_type="gain")
    feature_importance = {
        str(name): float(value)
        for name, value in zip(feature_names, importance_values, strict=False)
    }
    return LightGBMModel(
        pipeline=final_pipeline,
        hyperparameters=dict(tuning_model.hyperparameters),
        feature_names=feature_names,
        best_iteration=int(tuning_model.best_iteration),
        validation_mae_by_config=list(tuning_model.validation_mae_by_config),
        feature_importance=feature_importance,
        train_row_count=int(len(train_validation_frame)),
        stage="final",
    )


__all__ = [
    "LIGHTGBM_MODEL_VERSION",
    "LightGBMModel",
    "refit_lightgbm",
    "tune_lightgbm",
]
