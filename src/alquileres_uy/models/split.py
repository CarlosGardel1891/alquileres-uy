"""Deterministic temporal split for the training pipeline.

The split is grouped by unique ``date_created`` timestamps so no two
rows sharing the same instant end up in different partitions. The
order is train → validation → test in chronological order:

    max(train.date_created) < min(validation.date_created)
    max(validation.date_created) < min(test.date_created)

There is no shuffle, no random state, and no fallback. If the input
does not contain enough distinct timestamps to satisfy those
invariants the function raises :class:`SplitError`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass

import pandas as pd

from .config import SPLIT_ALGORITHM_VERSION


class SplitError(ValueError):
    """Raised when the input frame cannot be split temporally."""


@dataclass(frozen=True)
class TemporalSplit:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    train_ids: tuple[str, ...]
    validation_ids: tuple[str, ...]
    test_ids: tuple[str, ...]
    train_cutoff: pd.Timestamp
    validation_cutoff: pd.Timestamp
    algorithm_version: str = SPLIT_ALGORITHM_VERSION

    def as_manifest(
        self,
        *,
        seed: int,
        train_fraction: float,
        validation_fraction: float,
        test_fraction: float,
    ) -> dict:
        total = len(self.train) + len(self.validation) + len(self.test)
        return {
            "strategy": "temporal-grouped",
            "algorithm_version": self.algorithm_version,
            "seed": seed,
            "shuffle": False,
            "same_timestamp_kept_together": True,
            "requested_fractions": {
                "train": train_fraction,
                "validation": validation_fraction,
                "test": test_fraction,
            },
            "actual_fractions": {
                "train": len(self.train) / total,
                "validation": len(self.validation) / total,
                "test": len(self.test) / total,
            },
            "row_counts": {
                "train": len(self.train),
                "validation": len(self.validation),
                "test": len(self.test),
                "total": total,
            },
            "date_ranges": {
                "train": _range(self.train),
                "validation": _range(self.validation),
                "test": _range(self.test),
            },
            "cutoffs": {
                "train_to_validation": self.train_cutoff.isoformat(),
                "validation_to_test": self.validation_cutoff.isoformat(),
            },
            "id_hashes": {
                "train": _hash_ids(self.train_ids),
                "validation": _hash_ids(self.validation_ids),
                "test": _hash_ids(self.test_ids),
            },
        }


def temporal_split(
    frame: pd.DataFrame,
    *,
    train_fraction: float,
    validation_fraction: float,
    test_fraction: float,
) -> TemporalSplit:
    if abs(train_fraction + validation_fraction + test_fraction - 1.0) > 1e-6:
        raise SplitError("train + validation + test fractions must sum to 1.0")
    if len(frame) == 0:
        raise SplitError("input frame is empty")
    if "date_created" not in frame.columns or "source_item_id" not in frame.columns:
        raise SplitError("input frame must include date_created and source_item_id")

    ordered = frame.sort_values(["date_created", "source_item_id"]).reset_index(drop=True)
    unique_timestamps = ordered["date_created"].drop_duplicates().reset_index(drop=True)
    if len(unique_timestamps) < 3:
        raise SplitError(
            "temporal split requires at least three unique timestamps, "
            f"got {len(unique_timestamps)}"
        )

    # Cumulative row counts per unique timestamp let us pick group
    # boundaries that respect same-timestamp grouping.
    counts_per_ts = ordered.groupby("date_created", sort=True).size()
    cumulative = counts_per_ts.cumsum()
    total_rows = int(cumulative.iloc[-1])

    train_target = train_fraction * total_rows
    validation_target = (train_fraction + validation_fraction) * total_rows

    train_ts = _pick_boundary(cumulative, train_target)
    validation_ts = _pick_boundary(cumulative, validation_target, minimum_ts=train_ts)

    train_mask = ordered["date_created"] <= train_ts
    validation_mask = (ordered["date_created"] > train_ts) & (
        ordered["date_created"] <= validation_ts
    )
    test_mask = ordered["date_created"] > validation_ts

    train = ordered.loc[train_mask].reset_index(drop=True)
    validation = ordered.loc[validation_mask].reset_index(drop=True)
    test = ordered.loc[test_mask].reset_index(drop=True)

    if train.empty or validation.empty or test.empty:
        raise SplitError(
            "temporal split produced an empty partition — dataset likely has too few "
            "distinct timestamps for the requested fractions"
        )

    # Invariants the prompt calls out explicitly.
    if train["date_created"].max() >= validation["date_created"].min():
        raise SplitError("train max date must be strictly before validation min date")
    if validation["date_created"].max() >= test["date_created"].min():
        raise SplitError("validation max date must be strictly before test min date")
    overlap = (
        set(train["source_item_id"]) & set(validation["source_item_id"])
        | set(train["source_item_id"]) & set(test["source_item_id"])
        | set(validation["source_item_id"]) & set(test["source_item_id"])
    )
    if overlap:
        raise SplitError(f"source_item_id overlap across splits: {sorted(overlap)[:5]}")

    return TemporalSplit(
        train=train,
        validation=validation,
        test=test,
        train_ids=tuple(train["source_item_id"].astype(str)),
        validation_ids=tuple(validation["source_item_id"].astype(str)),
        test_ids=tuple(test["source_item_id"].astype(str)),
        train_cutoff=pd.Timestamp(train["date_created"].max()),
        validation_cutoff=pd.Timestamp(validation["date_created"].max()),
    )


def _pick_boundary(cumulative: pd.Series, target: float, *, minimum_ts=None) -> pd.Timestamp:
    """Pick the earliest timestamp whose cumulative rows meet ``target``."""
    for ts, running in cumulative.items():
        if minimum_ts is not None and ts <= minimum_ts:
            continue
        if running >= target:
            return ts
    return cumulative.index[-1]


def _range(frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {"min": None, "max": None}
    return {
        "min": pd.Timestamp(frame["date_created"].min()).isoformat(),
        "max": pd.Timestamp(frame["date_created"].max()).isoformat(),
    }


def _hash_ids(ids: Iterable[str]) -> str:
    joined = "\n".join(str(x) for x in ids).encode("utf-8")
    return hashlib.sha256(joined).hexdigest()


__all__ = ["SplitError", "TemporalSplit", "temporal_split"]
