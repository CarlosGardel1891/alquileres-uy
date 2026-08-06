"""Ridge (linear) model tests."""

from __future__ import annotations

import numpy as np

from alquileres_uy.models.linear import LinearModel, tune_linear


def test_alpha_selected_from_validation(temporal_split_fixture):
    model = tune_linear(
        temporal_split_fixture.train,
        temporal_split_fixture.validation,
        target_column="price_usd",
        alphas=(0.1, 1.0, 10.0),
    )
    # The chosen alpha must be the one with the lowest validation MAE in the log.
    logged_best = min(model.validation_mae_by_alpha.items(), key=lambda kv: kv[1])[0]
    assert float(logged_best) == model.alpha


def test_predictions_are_finite_and_non_negative(temporal_split_fixture):
    model = tune_linear(
        temporal_split_fixture.train,
        temporal_split_fixture.validation,
        target_column="price_usd",
        alphas=(0.1, 1.0, 10.0),
    )
    prediction = model.predict(temporal_split_fixture.test)
    assert np.isfinite(prediction).all()
    assert (prediction >= 0).all()


def test_unknown_neighborhood_does_not_break_predict(temporal_split_fixture):
    model = tune_linear(
        temporal_split_fixture.train,
        temporal_split_fixture.validation,
        target_column="price_usd",
        alphas=(0.1, 1.0, 10.0),
    )
    unknown = temporal_split_fixture.test.head(1).copy()
    unknown["neighborhood_normalized"] = "MartianColony"
    prediction = model.predict(unknown)
    assert np.isfinite(prediction).all()


def test_joblib_round_trip(temporal_split_fixture, tmp_path):
    original = tune_linear(
        temporal_split_fixture.train,
        temporal_split_fixture.validation,
        target_column="price_usd",
        alphas=(0.1, 1.0),
    )
    path = original.save(tmp_path / "linear.joblib")
    reloaded = LinearModel.load(path)
    expected = original.predict(temporal_split_fixture.test)
    got = reloaded.predict(temporal_split_fixture.test)
    assert np.allclose(expected, got, atol=1e-6)
    assert reloaded.alpha == original.alpha


def test_coefficients_summary_has_expected_shape(temporal_split_fixture):
    model = tune_linear(
        temporal_split_fixture.train,
        temporal_split_fixture.validation,
        target_column="price_usd",
        alphas=(1.0,),
    )
    summary = model.coefficients_summary()
    assert "intercept" in summary
    assert len(summary["coefficients"]) == len(model.feature_names)
    assert len(summary["top_positive"]) <= 5
    assert len(summary["top_negative"]) <= 5


def test_feature_names_include_categoricals(temporal_split_fixture):
    model = tune_linear(
        temporal_split_fixture.train,
        temporal_split_fixture.validation,
        target_column="price_usd",
        alphas=(1.0,),
    )
    joined = "|".join(model.feature_names)
    assert "neighborhood" in joined or "cat__" in joined
