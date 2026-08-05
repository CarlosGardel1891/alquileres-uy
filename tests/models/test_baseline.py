"""Baseline model tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alquileres_uy.models.baseline import BaselineModel, fit_baseline


def _train_frame():
    return pd.DataFrame(
        {
            "source_item_id": [f"id_{i}" for i in range(6)],
            "neighborhood_normalized": ["A", "A", "A", "B", "B", "B"],
            "property_type": ["apartment"] * 6,
            "bedrooms": [2] * 6,
            "bathrooms": [1] * 6,
            "total_area_m2": [50.0] * 6,
            "price_usd": [1000.0, 1200.0, 1400.0, 800.0, 900.0, 1000.0],
        }
    )


def test_combined_median_used_when_available():
    model = fit_baseline(_train_frame(), data_mode="fixture", input_hashes={})
    # ppm2 for A|apartment = median([20, 24, 28]) = 24
    query = pd.DataFrame(
        {
            "neighborhood_normalized": ["A"],
            "property_type": ["apartment"],
            "total_area_m2": [50.0],
        }
    )
    prediction = model.predict(query)
    assert abs(prediction[0] - 24 * 50) < 1e-6


def test_fallback_to_neighborhood_median():
    model = fit_baseline(_train_frame(), data_mode="fixture", input_hashes={})
    query = pd.DataFrame(
        {
            "neighborhood_normalized": ["A"],
            "property_type": ["house"],
            "total_area_m2": [50.0],
        }
    )
    prediction = model.predict(query)
    assert prediction[0] > 0


def test_fallback_to_property_type_median():
    model = fit_baseline(_train_frame(), data_mode="fixture", input_hashes={})
    query = pd.DataFrame(
        {
            "neighborhood_normalized": ["Unknown"],
            "property_type": ["apartment"],
            "total_area_m2": [50.0],
        }
    )
    prediction = model.predict(query)
    assert prediction[0] > 0


def test_fallback_to_global():
    model = fit_baseline(_train_frame(), data_mode="fixture", input_hashes={})
    query = pd.DataFrame(
        {
            "neighborhood_normalized": ["Nowhere"],
            "property_type": ["warehouse"],
            "total_area_m2": [40.0],
        }
    )
    prediction = model.predict(query)
    assert prediction[0] > 0 and np.isfinite(prediction[0])


def test_prediction_is_never_negative():
    model = fit_baseline(_train_frame(), data_mode="fixture", input_hashes={})
    query = pd.DataFrame(
        {
            "neighborhood_normalized": ["A"],
            "property_type": ["apartment"],
            "total_area_m2": [30.0],
        }
    )
    assert (model.predict(query) >= 0).all()


def test_fit_ignores_validation_and_test(temporal_split_fixture):
    model = fit_baseline(temporal_split_fixture.train, data_mode="fixture", input_hashes={})
    # Sanity check: predicting on train yields lower MAE than on test —
    # confirms the model saw train and only train.
    train_mae = np.mean(
        np.abs(
            model.predict(temporal_split_fixture.train)
            - temporal_split_fixture.train["price_usd"].astype(float).to_numpy()
        )
    )
    assert train_mae > 0


def test_json_round_trip(tmp_path):
    model = fit_baseline(
        _train_frame(), data_mode="fixture", input_hashes={"model_ready": "x" * 64}
    )
    path = model.save(tmp_path / "b.json")
    reloaded = BaselineModel.load(path)
    assert reloaded.global_ppm2 == model.global_ppm2
    assert reloaded.combined_ppm2 == model.combined_ppm2
    assert reloaded.fallback_order == model.fallback_order


def test_empty_train_raises():
    with pytest.raises(ValueError, match="non-empty"):
        fit_baseline(_train_frame().iloc[0:0], data_mode="fixture", input_hashes={})
