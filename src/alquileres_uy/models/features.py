"""Shared feature preprocessing for every candidate model.

Two entry points:

* :func:`build_preprocessor` returns the classical ColumnTransformer
  (median imputation + StandardScaler on the numeric branch, one-hot
  with ``handle_unknown="ignore"`` on the categorical branch) that
  Ridge and LightGBM share. Every fit must run on the training
  partition only during tuning, and on ``train + validation`` only
  during the final refit — the transformer itself does not know that
  distinction, so the caller is responsible.
* :func:`build_torch_vocabularies` builds the PyTorch-specific
  vocabularies. Index 0 is reserved for unknown/missing tokens on
  both categorical fields. Bathrooms is imputed with the fit-frame
  **median** (train during tuning, ``train + validation`` during the
  final refit); numeric mean / std are computed on the already-imputed
  values so inference and training see the same distribution.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .config import CATEGORICAL_FEATURES, FEATURE_COLUMNS, NUMERIC_FEATURES
from .contracts import check_training_leakage
from .imputation import CONSTANT_FALLBACK, resolve_numeric_imputation_values


@dataclass(frozen=True)
class TorchVocabularies:
    """Vocabularies + numeric statistics learned from a fit frame.

    ``numeric_impute_values`` holds the value used to fill a missing
    observation for each numeric feature: the fit-frame **median** when
    the column had any observations, and ``0.0`` when it did not (all
    values null, or the column was absent and injected as NaN by the
    input contract). ``imputation_sources`` records which case applied.
    ``numeric_mean`` / ``numeric_std`` are computed *after* imputation so
    the standardisation matches what the module sees at inference time.
    """

    neighborhood: dict[str, int]
    property_type: dict[str, int]
    numeric_mean: dict[str, float]
    numeric_std: dict[str, float]
    numeric_impute_values: dict[str, float]
    imputation_sources: dict[str, str]

    def as_json(self) -> dict:
        return {
            "neighborhood": self.neighborhood,
            "property_type": self.property_type,
            "numeric_mean": self.numeric_mean,
            "numeric_std": self.numeric_std,
            "numeric_impute_values": self.numeric_impute_values,
            "imputation_sources": self.imputation_sources,
        }


def build_preprocessor() -> ColumnTransformer:
    """Return the shared ColumnTransformer for the classical models.

    Numeric branch imputes missing values with the fit-frame median and
    standardizes. ``keep_empty_features=True`` preserves ``bathrooms``
    even when the fit frame has no observations for it (sklearn 1.6
    falls back to 0.0 for such columns, matching :mod:`imputation`).
    Categorical branch one-hot encodes with ``handle_unknown="ignore"``.
    """
    check_training_leakage(FEATURE_COLUMNS)
    numeric = Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("scale", StandardScaler()),
        ]
    )
    categorical = OneHotEncoder(handle_unknown="ignore", sparse_output=False, dtype=np.float64)
    return ColumnTransformer(
        transformers=[
            ("num", numeric, list(NUMERIC_FEATURES)),
            ("cat", categorical, list(CATEGORICAL_FEATURES)),
        ]
    )


def feature_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Return the frame limited to the declared feature columns.

    If ``bathrooms`` is absent, add it as an all-NaN column so downstream
    imputers can operate on it without surprising the caller. The input
    frame is never mutated.
    """
    working = frame
    if "bathrooms" not in working.columns:
        working = frame.copy()
        working["bathrooms"] = pd.array([pd.NA] * len(frame), dtype="Float64")
    missing = [c for c in FEATURE_COLUMNS if c not in working.columns]
    if missing:
        raise ValueError(f"input frame is missing feature columns: {missing}")
    check_training_leakage(FEATURE_COLUMNS)
    subset = working.loc[:, list(FEATURE_COLUMNS)].copy()
    for column in NUMERIC_FEATURES:
        subset[column] = pd.to_numeric(subset[column], errors="coerce").astype(float)
    for column in CATEGORICAL_FEATURES:
        subset[column] = subset[column].astype(str)
    return subset


def resolve_feature_names(preprocessor: ColumnTransformer) -> list[str]:
    """Return the ordered feature names produced by ``build_preprocessor``."""
    return list(preprocessor.get_feature_names_out())


def build_torch_vocabularies(fit_frame: pd.DataFrame) -> TorchVocabularies:
    """Build categorical vocabularies + numeric normalization stats.

    ``fit_frame`` is train-only during tuning and ``train + validation``
    during the final refit — the caller decides.
    """
    check_training_leakage(FEATURE_COLUMNS)
    neighborhood_vocab = _make_vocabulary(fit_frame["neighborhood_normalized"])
    property_vocab = _make_vocabulary(fit_frame["property_type"])

    working = fit_frame
    if "bathrooms" not in working.columns:
        working = fit_frame.copy()
        working["bathrooms"] = pd.array([pd.NA] * len(fit_frame), dtype="Float64")

    # Delegate the "median or 0.0 fallback" policy to the shared helper
    # so classical and torch models agree byte-for-byte on the impute
    # value for any all-null / absent numeric column.
    impute_values, imputation_sources = resolve_numeric_imputation_values(working)

    numeric_mean: dict[str, float] = {}
    numeric_std: dict[str, float] = {}
    for column in NUMERIC_FEATURES:
        values = pd.to_numeric(working[column], errors="coerce").astype(float)
        values = values.fillna(impute_values[column])
        mean = float(values.mean())
        std = float(values.std(ddof=0))
        if std == 0.0:
            std = 1.0
        numeric_mean[column] = mean
        numeric_std[column] = std

    return TorchVocabularies(
        neighborhood=neighborhood_vocab,
        property_type=property_vocab,
        numeric_mean=numeric_mean,
        numeric_std=numeric_std,
        numeric_impute_values=dict(impute_values),
        imputation_sources=dict(imputation_sources),
    )


def encode_torch_frame(
    frame: pd.DataFrame, vocabularies: TorchVocabularies
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Encode ``frame`` with the given vocabularies.

    Returns three arrays: neighborhood indices, property_type indices,
    and the standardized numeric matrix (columns in
    ``NUMERIC_FEATURES`` order).
    """
    working = frame
    if "bathrooms" not in working.columns:
        working = frame.copy()
        working["bathrooms"] = pd.array([pd.NA] * len(frame), dtype="Float64")
    neighborhood_idx = _lookup_indices(
        working["neighborhood_normalized"], vocabularies.neighborhood
    )
    property_idx = _lookup_indices(working["property_type"], vocabularies.property_type)

    numeric_cols = []
    for column in NUMERIC_FEATURES:
        values = pd.to_numeric(working[column], errors="coerce").astype(float)
        if values.isnull().any():
            fill_value = vocabularies.numeric_impute_values.get(column, CONSTANT_FALLBACK)
            values = values.fillna(fill_value)
        arr = values.to_numpy()
        std = vocabularies.numeric_std[column]
        mean = vocabularies.numeric_mean[column]
        numeric_cols.append((arr - mean) / (std or 1.0))
    numeric = np.stack(numeric_cols, axis=1).astype(np.float32)
    return neighborhood_idx.astype(np.int64), property_idx.astype(np.int64), numeric


def _make_vocabulary(series: Iterable) -> dict[str, int]:
    # Index 0 is reserved for the unknown/missing token.
    seen: dict[str, int] = {"__unknown__": 0}
    for value in series:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            continue
        key = str(value)
        if key not in seen:
            seen[key] = len(seen)
    return seen


def _lookup_indices(series: pd.Series, vocabulary: dict[str, int]) -> np.ndarray:
    return series.astype(str).map(lambda x: vocabulary.get(x, 0)).astype(np.int64).to_numpy()


__all__ = [
    "TorchVocabularies",
    "build_preprocessor",
    "build_torch_vocabularies",
    "encode_torch_frame",
    "feature_frame",
    "resolve_feature_names",
]
