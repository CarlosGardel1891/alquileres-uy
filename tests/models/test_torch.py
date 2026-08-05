"""PyTorch tabular model tests (marked so classical CI can skip them)."""

from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="torch is not installed")

# The torch_model import happens after importorskip so the classical CI
# job (which does not install torch) can still parse this file safely.
from alquileres_uy.models.torch_model import (  # noqa: E402
    TorchNotAvailableError,
    TorchTabularModel,
    fit_torch_model,
)

pytestmark = pytest.mark.torch


def _small_config(fixture):
    return dict(
        target_column="price_usd",
        seed=42,
        max_epochs=25,
        patience=6,
        batch_size=16,
    )


def test_forward_pass_shape(temporal_split_fixture):
    model = fit_torch_model(
        temporal_split_fixture.train,
        temporal_split_fixture.validation,
        **_small_config(temporal_split_fixture),
    )
    pred = model.predict(temporal_split_fixture.test)
    assert pred.shape == (len(temporal_split_fixture.test),)
    assert np.isfinite(pred).all()


def test_early_stopping_records_best_epoch(temporal_split_fixture):
    model = fit_torch_model(
        temporal_split_fixture.train,
        temporal_split_fixture.validation,
        **_small_config(temporal_split_fixture),
    )
    assert model.history.best_epoch >= 0
    assert model.history.stopped_at_epoch >= model.history.best_epoch


def test_training_history_records_losses(temporal_split_fixture):
    model = fit_torch_model(
        temporal_split_fixture.train,
        temporal_split_fixture.validation,
        **_small_config(temporal_split_fixture),
    )
    assert model.history.train_loss
    assert model.history.validation_loss
    assert model.history.validation_mae


def test_state_dict_round_trip(temporal_split_fixture, tmp_path):
    original = fit_torch_model(
        temporal_split_fixture.train,
        temporal_split_fixture.validation,
        **_small_config(temporal_split_fixture),
    )
    directory = tmp_path / "torch"
    original.save(directory)
    reloaded = TorchTabularModel.load(directory)
    expected = original.predict(temporal_split_fixture.test)
    got = reloaded.predict(temporal_split_fixture.test)
    assert np.allclose(expected, got, atol=1e-4)


def test_predictions_are_non_negative(temporal_split_fixture):
    model = fit_torch_model(
        temporal_split_fixture.train,
        temporal_split_fixture.validation,
        **_small_config(temporal_split_fixture),
    )
    prediction = model.predict(temporal_split_fixture.test)
    assert (prediction >= 0).all()


def test_unknown_categories_map_to_index_zero(temporal_split_fixture):
    model = fit_torch_model(
        temporal_split_fixture.train,
        temporal_split_fixture.validation,
        **_small_config(temporal_split_fixture),
    )
    unknown = temporal_split_fixture.test.head(1).copy()
    unknown["neighborhood_normalized"] = "MartianColony"
    prediction = model.predict(unknown)
    assert np.isfinite(prediction).all()


def test_eligible_for_api_serving_is_false(temporal_split_fixture):
    model = fit_torch_model(
        temporal_split_fixture.train,
        temporal_split_fixture.validation,
        **_small_config(temporal_split_fixture),
    )
    assert model.eligible_for_api_serving is False


def test_cpu_only(temporal_split_fixture):
    model = fit_torch_model(
        temporal_split_fixture.train,
        temporal_split_fixture.validation,
        **_small_config(temporal_split_fixture),
    )
    for parameter in model.module.parameters():
        assert parameter.device.type == "cpu"


def test_error_when_torch_missing(monkeypatch):
    # Simulate torch not being importable by shadowing the resolution helper.
    from alquileres_uy.models import torch_model as tm

    def _fake_import():
        raise ImportError("simulated")

    monkeypatch.setattr(
        tm, "_import_torch", lambda: (_ for _ in ()).throw(TorchNotAvailableError("stub"))
    )
    with pytest.raises(TorchNotAvailableError):
        tm._import_torch()
