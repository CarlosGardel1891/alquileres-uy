"""Shared numeric imputation policy for training features.

The classical branch (`SimpleImputer(strategy="median",
keep_empty_features=True)`) silently returns 0.0 for a column with no
observed values. PyTorch builds its own vocabularies, so both branches
need to agree on the fallback. This module owns that decision:

* if the fit frame carries at least one non-null observation for a
  numeric feature → use the median of the observed values;
* if every value is null (or the column was absent and injected as
  NaN by the input contract) → use the constant fallback ``0.0``.

The helper is called on the tuning frame during tuning and on
``train + validation`` during the final refit; validation and test are
never inspected.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd

from .config import NUMERIC_FEATURES

ImputationStrategy = Literal["fit_frame_median", "constant_fallback_no_observed_values"]

CONSTANT_FALLBACK: float = 0.0


def resolve_numeric_imputation_values(
    fit_frame: pd.DataFrame,
) -> tuple[dict[str, float], dict[str, ImputationStrategy]]:
    """Return ``(impute_values, imputation_sources)`` for :data:`NUMERIC_FEATURES`.

    ``impute_values`` maps each numeric feature to a scalar the model
    should use in place of missing observations. ``imputation_sources``
    is a parallel dict that records why the value was chosen so the
    training artifacts can explain it (``fit_frame_median`` when the
    column had observations, ``constant_fallback_no_observed_values``
    when it did not).
    """
    values: dict[str, float] = {}
    sources: dict[str, ImputationStrategy] = {}
    for column in NUMERIC_FEATURES:
        if column not in fit_frame.columns:
            values[column] = CONSTANT_FALLBACK
            sources[column] = "constant_fallback_no_observed_values"
            continue
        series = pd.to_numeric(fit_frame[column], errors="coerce").astype(float)
        observed = series.dropna()
        if observed.empty:
            values[column] = CONSTANT_FALLBACK
            sources[column] = "constant_fallback_no_observed_values"
        else:
            values[column] = float(observed.median())
            sources[column] = "fit_frame_median"
    return values, sources


__all__ = [
    "CONSTANT_FALLBACK",
    "ImputationStrategy",
    "resolve_numeric_imputation_values",
]
