"""Tests for the deterministic temporal split."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from alquileres_uy.models.split import SplitError, temporal_split


def _synthetic_frame(n: int = 60) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source_item_id": [f"id_{i:04d}" for i in range(n)],
            "date_created": pd.to_datetime(
                [datetime(2026, 1, 1, tzinfo=UTC) + pd.Timedelta(days=i) for i in range(n)],
                utc=True,
            ),
        }
    )


def test_temporal_order_is_strict():
    frame = _synthetic_frame()
    sp = temporal_split(frame, train_fraction=0.7, validation_fraction=0.15, test_fraction=0.15)
    assert sp.train["date_created"].max() < sp.validation["date_created"].min()
    assert sp.validation["date_created"].max() < sp.test["date_created"].min()


def test_same_timestamp_kept_together():
    same_day = datetime(2026, 6, 1, tzinfo=UTC)
    rows = []
    for i in range(4):
        rows.append({"source_item_id": f"a_{i}", "date_created": pd.Timestamp(same_day)})
    rows += [
        {
            "source_item_id": f"other_{i:03d}",
            "date_created": pd.Timestamp(datetime(2026, 6, 2 + i, tzinfo=UTC)),
        }
        for i in range(10)
    ]
    frame = pd.DataFrame(rows)
    sp = temporal_split(frame, train_fraction=0.5, validation_fraction=0.25, test_fraction=0.25)
    same_ids = {
        row["source_item_id"] for row in rows if row["date_created"] == pd.Timestamp(same_day)
    }
    partitions = [
        set(sp.train["source_item_id"]),
        set(sp.validation["source_item_id"]),
        set(sp.test["source_item_id"]),
    ]
    matches = sum(1 for p in partitions if same_ids <= p)
    assert matches == 1, "same-timestamp rows must all live in the same partition"


def test_no_source_id_overlap():
    frame = _synthetic_frame(90)
    sp = temporal_split(frame, train_fraction=0.7, validation_fraction=0.15, test_fraction=0.15)
    all_ids = (
        set(sp.train["source_item_id"])
        | set(sp.validation["source_item_id"])
        | set(sp.test["source_item_id"])
    )
    assert len(all_ids) == 90
    assert set(sp.train["source_item_id"]).isdisjoint(sp.validation["source_item_id"])
    assert set(sp.train["source_item_id"]).isdisjoint(sp.test["source_item_id"])
    assert set(sp.validation["source_item_id"]).isdisjoint(sp.test["source_item_id"])


def test_three_partitions_non_empty(temporal_split_fixture):
    assert not temporal_split_fixture.train.empty
    assert not temporal_split_fixture.validation.empty
    assert not temporal_split_fixture.test.empty


def test_fewer_than_three_timestamps_fails():
    frame = pd.DataFrame(
        {
            "source_item_id": ["a", "b", "c", "d"],
            "date_created": pd.to_datetime(
                [
                    datetime(2026, 1, 1, tzinfo=UTC),
                    datetime(2026, 1, 1, tzinfo=UTC),
                    datetime(2026, 1, 2, tzinfo=UTC),
                    datetime(2026, 1, 2, tzinfo=UTC),
                ],
                utc=True,
            ),
        }
    )
    with pytest.raises(SplitError, match="three unique timestamps"):
        temporal_split(frame, train_fraction=0.7, validation_fraction=0.15, test_fraction=0.15)


def test_reproducibility(temporal_split_fixture, training_input):
    other = temporal_split(
        training_input.model_ready,
        train_fraction=0.7,
        validation_fraction=0.15,
        test_fraction=0.15,
    )
    assert temporal_split_fixture.train_ids == other.train_ids
    assert temporal_split_fixture.test_ids == other.test_ids


def test_actual_fractions_reported(temporal_split_fixture):
    manifest = temporal_split_fixture.as_manifest(
        seed=42, train_fraction=0.7, validation_fraction=0.15, test_fraction=0.15
    )
    total = manifest["row_counts"]["total"]
    assert (
        abs(manifest["actual_fractions"]["train"] - temporal_split_fixture.train.shape[0] / total)
        < 1e-9
    )


def test_stable_tie_break_by_source_id():
    same_day = datetime(2026, 6, 1, tzinfo=UTC)
    frame = pd.DataFrame(
        {
            "source_item_id": ["b", "a", "c"],
            "date_created": pd.to_datetime([pd.Timestamp(same_day)] * 3, utc=True),
        }
    )
    frame = pd.concat(
        [
            frame,
            pd.DataFrame(
                {
                    "source_item_id": [f"z_{i:02d}" for i in range(10)],
                    "date_created": pd.to_datetime(
                        [datetime(2026, 6, 2 + i, tzinfo=UTC) for i in range(10)],
                        utc=True,
                    ),
                }
            ),
        ],
        ignore_index=True,
    )
    sp = temporal_split(frame, train_fraction=0.5, validation_fraction=0.25, test_fraction=0.25)
    # Same-day group must stay together across partitions, regardless of
    # source_item_id ordering on input.
    combined = pd.concat([sp.train, sp.validation, sp.test], ignore_index=True)
    order = combined["source_item_id"].tolist()
    # a, b, c should stay together
    positions = sorted(order.index(x) for x in ("a", "b", "c"))
    assert positions == list(range(min(positions), min(positions) + 3))


def test_no_shuffle(temporal_split_fixture):
    train = temporal_split_fixture.train
    # Dates in the train partition must be monotonically non-decreasing.
    dates = train["date_created"].tolist()
    assert dates == sorted(dates)


def test_test_is_always_after_validation(temporal_split_fixture):
    assert (
        temporal_split_fixture.validation["date_created"].max()
        < temporal_split_fixture.test["date_created"].min()
    )


def test_bad_fractions_rejected():
    with pytest.raises(SplitError, match="sum to 1"):
        temporal_split(
            _synthetic_frame(), train_fraction=0.5, validation_fraction=0.2, test_fraction=0.2
        )
