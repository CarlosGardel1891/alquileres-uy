"""Shared feature preprocessing for the classical models.

The classical models (Ridge, LightGBM) reuse a small sklearn
``ColumnTransformer`` that must be fit **only** on the training
partition. The bathroom imputer, the numeric scaler and the
one-hot encoder are all leak-free by construction because their
``fit`` is called with the train frame alone.

The PyTorch model builds its own vocabularies via
:func:`build_torch_vocabularies` — same rule applies (train only).
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


@dataclass(frozen=True)
class TorchVocabularies:
    neighborhood: dict[str, int]
    property_type: dict[str, int]
    numeric_mean: dict[str, float]
    numeric_std: dict[str, float]

    def as_json(self) -> dict:
        return {
            "neighborhood": self.neighborhood,
            "property_type": self.property_type,
            "numeric_mean": self.numeric_mean,
            "numeric_std": self.numeric_std,
        }


def build_preprocessor() -> ColumnTransformer:
    """Return the shared ColumnTransformer for the classical models.

    Numeric branch imputes bathrooms via train median and standardizes.
    Categorical branch one-hot encodes with ``handle_unknown="ignore"``.
    """
    check_training_leakage(FEATURE_COLUMNS)
    numeric = Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="median")),
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

    Ensures the caller cannot accidentally hand the estimator the
    target column or leaky derivatives.
    """
    missing = [c for c in FEATURE_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(f"input frame is missing feature columns: {missing}")
    check_training_leakage(FEATURE_COLUMNS)
    subset = frame.loc[:, list(FEATURE_COLUMNS)].copy()
    # Ensure numeric dtypes and drop any nullable pandas types the model libs dislike.
    for column in NUMERIC_FEATURES:
        subset[column] = pd.to_numeric(subset[column], errors="coerce").astype(float)
    for column in CATEGORICAL_FEATURES:
        subset[column] = subset[column].astype(str)
    return subset


def resolve_feature_names(preprocessor: ColumnTransformer) -> list[str]:
    """Return the ordered feature names produced by ``build_preprocessor``.

    Sklearn versions differ in exposure; use ``get_feature_names_out``
    when available.
    """
    return list(preprocessor.get_feature_names_out())


def build_torch_vocabularies(train_frame: pd.DataFrame) -> TorchVocabularies:
    """Build categorical vocabularies + numeric normalization stats from train.

    Index 0 is reserved for unknown/missing categories on both fields.
    """
    check_training_leakage(FEATURE_COLUMNS)
    neighborhood_vocab = _make_vocabulary(train_frame["neighborhood_normalized"])
    property_vocab = _make_vocabulary(train_frame["property_type"])

    numeric_mean: dict[str, float] = {}
    numeric_std: dict[str, float] = {}
    for column in NUMERIC_FEATURES:
        values = pd.to_numeric(train_frame[column], errors="coerce").astype(float)
        if column == "bathrooms":
            median = float(values.dropna().median() if not values.dropna().empty else 1.0)
            values = values.fillna(median)
        elif values.isnull().any():
            raise ValueError(f"unexpected null in required feature '{column}'")
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
    )


def encode_torch_frame(
    frame: pd.DataFrame, vocabularies: TorchVocabularies
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Encode ``frame`` with the given vocabularies.

    Returns three arrays: neighborhood indices, property_type indices,
    and the standardized numeric matrix (columns in ``NUMERIC_FEATURES`` order).
    """
    neighborhood_idx = _lookup_indices(frame["neighborhood_normalized"], vocabularies.neighborhood)
    property_idx = _lookup_indices(frame["property_type"], vocabularies.property_type)

    numeric_cols = []
    for column in NUMERIC_FEATURES:
        values = pd.to_numeric(frame[column], errors="coerce").astype(float)
        if column == "bathrooms":
            # Fall back to the train mean captured in the vocabulary.
            fill_value = vocabularies.numeric_mean.get("bathrooms")
            if fill_value is None:
                fill_value = 1.0
            values = values.fillna(fill_value)
        elif values.isnull().any():
            raise ValueError(f"unexpected null in feature '{column}' during encoding")
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
