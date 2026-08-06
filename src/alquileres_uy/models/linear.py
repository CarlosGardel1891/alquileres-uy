"""Ridge regression (the project's regularized linear model).

Two functions:

* :func:`tune_linear` runs the alpha grid on train only, evaluates
  every candidate on validation, and returns the tuning model (fit on
  train only) plus the winning alpha.
* :func:`refit_linear` builds a new pipeline with the tuning alpha and
  fits it on ``train + validation``.

Both produce a :class:`LinearModel`. The final artifact stored under
``models/`` and inside the serving bundle is always the refit; the
tuning model is retained in memory so validation metrics and the
residual interval stay out-of-sample.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline

from .features import build_preprocessor, feature_frame, resolve_feature_names

LINEAR_MODEL_VERSION: str = "1.0.0"


@dataclass(frozen=True)
class LinearModel:
    pipeline: Pipeline
    alpha: float
    feature_names: tuple[str, ...]
    train_row_count: int
    validation_mae_by_alpha: dict[str, float]
    stage: str  # "tuning" or "final"
    version: str = LINEAR_MODEL_VERSION

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        prediction = self.pipeline.predict(feature_frame(frame))
        return np.clip(prediction, a_min=0.0, a_max=None)

    def coefficients_summary(self) -> dict:
        estimator = self.pipeline.named_steps["ridge"]
        preprocessor = self.pipeline.named_steps["preprocess"]
        feature_names = resolve_feature_names(preprocessor)
        coefficients = estimator.coef_.tolist()
        pairs = sorted(zip(feature_names, coefficients, strict=True), key=lambda x: x[1])
        top_negative = [{"feature": f, "coefficient": c} for f, c in pairs[:5]]
        top_positive = [{"feature": f, "coefficient": c} for f, c in pairs[-5:][::-1]]
        return {
            "alpha": self.alpha,
            "intercept": float(estimator.intercept_),
            "coefficients": [
                {"feature": f, "coefficient": c}
                for f, c in zip(feature_names, coefficients, strict=True)
            ],
            "top_positive": top_positive,
            "top_negative": top_negative,
        }

    def save(self, path: Path) -> Path:
        joblib.dump({"pipeline": self.pipeline, "metadata": self._metadata()}, path)
        return path

    @classmethod
    def load(cls, path: Path) -> LinearModel:
        payload = joblib.load(path)
        metadata = payload["metadata"]
        return cls(
            pipeline=payload["pipeline"],
            alpha=float(metadata["alpha"]),
            feature_names=tuple(metadata["feature_names"]),
            train_row_count=int(metadata["train_row_count"]),
            validation_mae_by_alpha={
                str(k): float(v) for k, v in metadata["validation_mae_by_alpha"].items()
            },
            stage=str(metadata.get("stage", "final")),
            version=str(metadata.get("version", LINEAR_MODEL_VERSION)),
        )

    def _metadata(self) -> dict:
        return {
            "alpha": self.alpha,
            "feature_names": list(self.feature_names),
            "train_row_count": self.train_row_count,
            "validation_mae_by_alpha": {str(k): v for k, v in self.validation_mae_by_alpha.items()},
            "stage": self.stage,
            "version": self.version,
        }


def tune_linear(
    train_frame: pd.DataFrame,
    validation_frame: pd.DataFrame,
    *,
    target_column: str,
    alphas: tuple[float, ...],
) -> LinearModel:
    """Tune Ridge alpha on validation. Model is fit on train only."""
    train_features = feature_frame(train_frame)
    validation_features = feature_frame(validation_frame)
    train_target = (
        pd.to_numeric(train_frame[target_column], errors="coerce").astype(float).to_numpy()
    )
    validation_target = (
        pd.to_numeric(validation_frame[target_column], errors="coerce").astype(float).to_numpy()
    )

    mae_by_alpha: dict[str, float] = {}
    best_alpha: float | None = None
    best_mae: float = float("inf")
    best_pipeline: Pipeline | None = None
    for alpha in alphas:
        candidate = Pipeline(
            steps=[
                ("preprocess", build_preprocessor()),
                ("ridge", Ridge(alpha=alpha, random_state=0)),
            ]
        )
        candidate.fit(train_features, train_target)
        predictions = np.clip(candidate.predict(validation_features), a_min=0.0, a_max=None)
        mae = float(np.mean(np.abs(predictions - validation_target)))
        mae_by_alpha[str(alpha)] = mae
        if mae < best_mae:
            best_mae = mae
            best_alpha = alpha
            best_pipeline = candidate

    if best_alpha is None or best_pipeline is None:
        raise ValueError("Ridge alpha selection failed — grid was empty")

    feature_names = tuple(resolve_feature_names(best_pipeline.named_steps["preprocess"]))
    return LinearModel(
        pipeline=best_pipeline,
        alpha=float(best_alpha),
        feature_names=feature_names,
        train_row_count=int(len(train_frame)),
        validation_mae_by_alpha=mae_by_alpha,
        stage="tuning",
    )


def refit_linear(
    train_validation_frame: pd.DataFrame,
    *,
    target_column: str,
    tuning_model: LinearModel,
) -> LinearModel:
    """Fit a fresh Ridge pipeline with the tuning alpha on train + validation."""
    features = feature_frame(train_validation_frame)
    target = (
        pd.to_numeric(train_validation_frame[target_column], errors="coerce")
        .astype(float)
        .to_numpy()
    )
    final = Pipeline(
        steps=[
            ("preprocess", build_preprocessor()),
            ("ridge", Ridge(alpha=tuning_model.alpha, random_state=0)),
        ]
    )
    final.fit(features, target)
    feature_names = tuple(resolve_feature_names(final.named_steps["preprocess"]))
    return LinearModel(
        pipeline=final,
        alpha=tuning_model.alpha,
        feature_names=feature_names,
        train_row_count=int(len(train_validation_frame)),
        validation_mae_by_alpha=dict(tuning_model.validation_mae_by_alpha),
        stage="final",
    )


__all__ = ["LINEAR_MODEL_VERSION", "LinearModel", "refit_linear", "tune_linear"]
