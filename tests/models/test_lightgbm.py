"""LightGBM model tests."""

from __future__ import annotations

import numpy as np

from alquileres_uy.models.lightgbm_model import LightGBMModel, tune_lightgbm


def test_hyperparameters_selected_from_validation(temporal_split_fixture):
    model = tune_lightgbm(
        temporal_split_fixture.train,
        temporal_split_fixture.validation,
        target_column="price_usd",
        seed=42,
    )
    logged_best = min(model.validation_mae_by_config, key=lambda row: row["validation_mae"])
    assert logged_best["config"] == model.hyperparameters


def test_deterministic_seed(temporal_split_fixture):
    a = tune_lightgbm(
        temporal_split_fixture.train,
        temporal_split_fixture.validation,
        target_column="price_usd",
        seed=42,
    )
    b = tune_lightgbm(
        temporal_split_fixture.train,
        temporal_split_fixture.validation,
        target_column="price_usd",
        seed=42,
    )
    pred_a = a.predict(temporal_split_fixture.test)
    pred_b = b.predict(temporal_split_fixture.test)
    assert np.allclose(pred_a, pred_b)


def test_early_stopping_reports_best_iteration(temporal_split_fixture):
    model = tune_lightgbm(
        temporal_split_fixture.train,
        temporal_split_fixture.validation,
        target_column="price_usd",
        seed=42,
    )
    assert model.best_iteration >= 1
    for row in model.validation_mae_by_config:
        assert row["best_iteration"] >= 1


def test_predictions_are_finite_and_non_negative(temporal_split_fixture):
    model = tune_lightgbm(
        temporal_split_fixture.train,
        temporal_split_fixture.validation,
        target_column="price_usd",
        seed=42,
    )
    prediction = model.predict(temporal_split_fixture.test)
    assert np.isfinite(prediction).all()
    assert (prediction >= 0).all()


def test_feature_importance_non_empty(temporal_split_fixture):
    model = tune_lightgbm(
        temporal_split_fixture.train,
        temporal_split_fixture.validation,
        target_column="price_usd",
        seed=42,
    )
    assert model.feature_importance
    assert all(v >= 0 for v in model.feature_importance.values())


def test_unknown_neighborhood_still_predicts(temporal_split_fixture):
    model = tune_lightgbm(
        temporal_split_fixture.train,
        temporal_split_fixture.validation,
        target_column="price_usd",
        seed=42,
    )
    unknown = temporal_split_fixture.test.head(1).copy()
    unknown["neighborhood_normalized"] = "MartianColony"
    prediction = model.predict(unknown)
    assert np.isfinite(prediction).all()


def test_joblib_round_trip(temporal_split_fixture, tmp_path):
    model = tune_lightgbm(
        temporal_split_fixture.train,
        temporal_split_fixture.validation,
        target_column="price_usd",
        seed=42,
    )
    path = model.save(tmp_path / "lightgbm.joblib")
    reloaded = LightGBMModel.load(path)
    expected = model.predict(temporal_split_fixture.test)
    got = reloaded.predict(temporal_split_fixture.test)
    assert np.allclose(expected, got, atol=1e-6)


def test_n_jobs_is_one(temporal_split_fixture):
    model = tune_lightgbm(
        temporal_split_fixture.train,
        temporal_split_fixture.validation,
        target_column="price_usd",
        seed=42,
    )
    estimator = model.pipeline.named_steps["lightgbm"]
    assert estimator.n_jobs == 1
    assert estimator.get_params()["deterministic"] is True
