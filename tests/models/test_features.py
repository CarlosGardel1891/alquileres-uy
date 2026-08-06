"""Feature preprocessing and leakage-guarantee tests."""

from __future__ import annotations

import numpy as np
import pytest

from alquileres_uy.models.features import (
    build_preprocessor,
    build_torch_vocabularies,
    encode_torch_frame,
    feature_frame,
)


def test_preprocessor_fits_only_on_train(temporal_split_fixture):
    preprocessor = build_preprocessor()
    train_features = feature_frame(temporal_split_fixture.train)
    validation_features = feature_frame(temporal_split_fixture.validation)
    preprocessor.fit(train_features)
    train_transformed = preprocessor.transform(train_features)
    validation_transformed = preprocessor.transform(validation_features)
    assert train_transformed.shape[0] == len(train_features)
    assert validation_transformed.shape[0] == len(validation_features)
    assert train_transformed.shape[1] == validation_transformed.shape[1]


def test_preprocessor_one_hot_handles_unknown(temporal_split_fixture):
    preprocessor = build_preprocessor()
    preprocessor.fit(feature_frame(temporal_split_fixture.train))
    unknown = feature_frame(temporal_split_fixture.test).head(1).copy()
    unknown["neighborhood_normalized"] = "MartianColony"
    transformed = preprocessor.transform(unknown)
    assert transformed.shape[0] == 1
    assert np.isfinite(transformed).all()


def test_preprocessor_imputer_fills_bathrooms(temporal_split_fixture):
    preprocessor = build_preprocessor()
    preprocessor.fit(feature_frame(temporal_split_fixture.train))
    with_missing = feature_frame(temporal_split_fixture.test).head(3).copy()
    with_missing["bathrooms"] = np.nan
    transformed = preprocessor.transform(with_missing)
    assert np.isfinite(transformed).all()


def test_feature_frame_only_returns_declared_features(temporal_split_fixture):
    sub = feature_frame(temporal_split_fixture.train)
    assert "price_usd" not in sub.columns
    assert "source_item_id" not in sub.columns
    assert "date_created" not in sub.columns
    assert set(sub.columns) == {
        "bedrooms",
        "bathrooms",
        "total_area_m2",
        "neighborhood_normalized",
        "property_type",
    }


def test_feature_frame_missing_feature_raises():
    import pandas as pd

    with pytest.raises(ValueError, match="missing feature columns"):
        feature_frame(pd.DataFrame({"bedrooms": [1]}))


def test_torch_vocabularies_reserve_zero_for_unknown(temporal_split_fixture):
    vocabs = build_torch_vocabularies(temporal_split_fixture.train)
    assert vocabs.neighborhood["__unknown__"] == 0
    assert vocabs.property_type["__unknown__"] == 0


def test_torch_vocabularies_fit_on_train_only(temporal_split_fixture):
    vocabs = build_torch_vocabularies(temporal_split_fixture.train)
    unseen = set(temporal_split_fixture.test["neighborhood_normalized"]) - set(
        temporal_split_fixture.train["neighborhood_normalized"]
    )
    for label in unseen:
        assert label not in vocabs.neighborhood


def test_torch_encoder_maps_unknown_to_zero(temporal_split_fixture):
    vocabs = build_torch_vocabularies(temporal_split_fixture.train)
    unknown_row = temporal_split_fixture.test.head(1).copy()
    unknown_row["neighborhood_normalized"] = "MartianColony"
    neigh, prop, num = encode_torch_frame(unknown_row, vocabs)
    assert neigh[0] == 0
    assert num.shape == (1, 3)
    assert np.isfinite(num).all()


def test_torch_encoder_uses_train_median_for_bathrooms(temporal_split_fixture):
    vocabs = build_torch_vocabularies(temporal_split_fixture.train)
    frame = temporal_split_fixture.validation.head(2).copy()
    frame["bathrooms"] = np.nan
    _, _, num = encode_torch_frame(frame, vocabs)
    assert np.isfinite(num).all()
