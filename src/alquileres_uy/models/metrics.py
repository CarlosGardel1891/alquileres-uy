"""Regression metrics: MAE, RMSE, MAPE, improvement vs. baseline.

All metrics are computed in USD; MAPE is reported both as a fraction
and as a percentage. Targets must be strictly positive — MAPE against
zero would silently misrepresent errors, so we raise rather than
introduce an epsilon.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


class MetricsError(ValueError):
    """Raised when metric inputs are invalid."""


@dataclass(frozen=True)
class RegressionMetrics:
    mae_usd: float
    rmse_usd: float
    mape_fraction: float
    mape_percent: float
    rows: int

    def as_json(self, *, baseline_mae: float | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "mae_usd": self.mae_usd,
            "rmse_usd": self.rmse_usd,
            "mape_fraction": self.mape_fraction,
            "mape_percent": self.mape_percent,
            "rows": self.rows,
        }
        if baseline_mae is not None and baseline_mae > 0:
            payload["improvement_vs_baseline"] = float((baseline_mae - self.mae_usd) / baseline_mae)
        return payload


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> RegressionMetrics:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    if y_true.shape != y_pred.shape:
        raise MetricsError(f"shape mismatch: y_true={y_true.shape} vs y_pred={y_pred.shape}")
    if y_true.size == 0:
        raise MetricsError("cannot compute metrics on empty arrays")
    if not np.isfinite(y_true).all():
        raise MetricsError("y_true contains non-finite values")
    if not np.isfinite(y_pred).all():
        raise MetricsError("y_pred contains non-finite values")
    if (y_true <= 0).any():
        raise MetricsError("MAPE requires strictly positive targets; got zero or negative values")

    residual = y_pred - y_true
    absolute = np.abs(residual)
    mae = float(np.mean(absolute))
    rmse = float(np.sqrt(np.mean(residual**2)))
    mape_fraction = float(np.mean(np.abs(residual / y_true)))
    return RegressionMetrics(
        mae_usd=mae,
        rmse_usd=rmse,
        mape_fraction=mape_fraction,
        mape_percent=mape_fraction * 100.0,
        rows=int(y_true.size),
    )


__all__ = ["MetricsError", "RegressionMetrics", "compute_metrics"]
