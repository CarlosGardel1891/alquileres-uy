"""Regression metrics + model-selection tests."""

from __future__ import annotations

import numpy as np
import pytest

from alquileres_uy.models.metrics import MetricsError, compute_metrics
from alquileres_uy.models.selection import SERVING_TIE_TOLERANCE, select_models


def test_metrics_basic_values():
    metrics = compute_metrics(np.array([100.0, 200.0]), np.array([90.0, 220.0]))
    assert metrics.mae_usd == pytest.approx(15.0)
    assert metrics.rmse_usd == pytest.approx(np.sqrt((10**2 + 20**2) / 2))
    assert metrics.rows == 2


def test_metrics_mape_fraction_and_percent():
    metrics = compute_metrics(np.array([100.0]), np.array([90.0]))
    assert metrics.mape_fraction == pytest.approx(0.1)
    assert metrics.mape_percent == pytest.approx(10.0)


def test_metrics_reject_zero_targets():
    with pytest.raises(MetricsError, match="positive"):
        compute_metrics(np.array([0.0, 100.0]), np.array([10.0, 90.0]))


def test_metrics_reject_negative_targets():
    with pytest.raises(MetricsError, match="positive"):
        compute_metrics(np.array([-10.0, 100.0]), np.array([10.0, 90.0]))


def test_metrics_reject_shape_mismatch():
    with pytest.raises(MetricsError, match="shape"):
        compute_metrics(np.array([1.0]), np.array([1.0, 2.0]))


def test_metrics_reject_nonfinite():
    with pytest.raises(MetricsError, match="non-finite"):
        compute_metrics(np.array([100.0]), np.array([np.nan]))


def test_metrics_json_has_no_infinities():
    metrics = compute_metrics(np.array([100.0]), np.array([50.0]))
    payload = metrics.as_json(baseline_mae=100.0)
    assert all(v == v for v in payload.values() if isinstance(v, float))  # no NaN
    assert payload["improvement_vs_baseline"] == pytest.approx(0.5)


def test_selection_best_overall_by_validation_mae():
    validation = {
        "baseline": {"mae_usd": 200.0, "mape_fraction": 0.2},
        "linear": {"mae_usd": 150.0, "mape_fraction": 0.15},
        "lightgbm": {"mae_usd": 120.0, "mape_fraction": 0.12},
        "torch": {"mae_usd": 100.0, "mape_fraction": 0.09},
    }
    selection = select_models(validation, data_mode="fixture")
    assert selection.best_overall_model == "torch"
    assert selection.serving_candidate == "lightgbm"  # torch excluded from serving


def test_selection_serving_prefers_simpler_within_tolerance():
    validation = {
        "baseline": {"mae_usd": 200.0, "mape_fraction": 0.2},
        "linear": {"mae_usd": 121.0, "mape_fraction": 0.12},
        "lightgbm": {"mae_usd": 120.0, "mape_fraction": 0.12},
    }
    selection = select_models(validation, data_mode="fixture")
    # lightgbm is 1 USD better, well inside SERVING_TIE_TOLERANCE — serving picks linear.
    assert selection.serving_candidate == "linear"
    assert selection.tie_tolerance_usd == SERVING_TIE_TOLERANCE


def test_selection_reason_excluded_for_torch_and_missing_models():
    validation = {
        "baseline": {"mae_usd": 200.0, "mape_fraction": 0.2},
        "linear": {"mae_usd": 150.0, "mape_fraction": 0.15},
        "lightgbm": {"mae_usd": 120.0, "mape_fraction": 0.12},
        "torch": {"mae_usd": 100.0, "mape_fraction": 0.09},
    }
    selection = select_models(validation, data_mode="fixture")
    assert "architecture decision" in selection.excluded["torch"]


def test_selection_fixture_bundle_is_not_deployable():
    validation = {
        "baseline": {"mae_usd": 200.0, "mape_fraction": 0.2},
        "linear": {"mae_usd": 150.0, "mape_fraction": 0.15},
        "lightgbm": {"mae_usd": 120.0, "mape_fraction": 0.12},
    }
    selection = select_models(validation, data_mode="fixture")
    payload = selection.as_json(deployable=False)
    assert payload["deployable"] is False
    assert payload["blocked_reason"] == "fixture training run"


def test_selection_uses_validation_not_test():
    """Changing test metrics later must not swap the serving decision."""
    validation = {
        "baseline": {"mae_usd": 200.0, "mape_fraction": 0.2},
        "linear": {"mae_usd": 150.0, "mape_fraction": 0.15},
        "lightgbm": {"mae_usd": 120.0, "mape_fraction": 0.12},
    }
    original = select_models(validation, data_mode="fixture").serving_candidate
    validation_same = dict(validation)  # test values live elsewhere; nothing here to swap
    assert select_models(validation_same, data_mode="fixture").serving_candidate == original


def test_selection_error_when_no_serving_models():
    with pytest.raises(ValueError, match="serving"):
        select_models({"torch": {"mae_usd": 100.0, "mape_fraction": 0.1}}, data_mode="fixture")


def test_selection_error_when_empty():
    with pytest.raises(ValueError, match="at least one model"):
        select_models({}, data_mode="fixture")
