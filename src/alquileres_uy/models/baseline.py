"""Baseline model: median price per m² per (neighborhood, property_type).

The baseline is intentionally trivial so it acts as a floor for the
learned models. Prediction is the median USD-per-square-meter for the
row's group, multiplied by its declared area, with a strict fallback
chain that guarantees no NaN.

Serialization is plain JSON so the fixture bundle stays trivially
inspectable and free of any pickled objects.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import CATEGORICAL_FEATURES, TARGET_COLUMN

BASELINE_VERSION: str = "1.0.0"
_FALLBACK_ORDER: tuple[str, ...] = ("neighborhood_property", "neighborhood", "property", "global")


@dataclass(frozen=True)
class BaselineModel:
    global_ppm2: float
    neighborhood_ppm2: dict[str, float]
    property_ppm2: dict[str, float]
    combined_ppm2: dict[str, float]  # "neighborhood|property_type"
    train_row_count: int
    data_mode: str
    input_hashes: dict[str, str]
    fallback_order: tuple[str, ...] = _FALLBACK_ORDER
    version: str = BASELINE_VERSION

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return _predict(frame, self)

    def save(self, path: Path) -> Path:
        payload = {
            "version": self.version,
            "train_row_count": self.train_row_count,
            "data_mode": self.data_mode,
            "fallback_order": list(self.fallback_order),
            "global_ppm2": self.global_ppm2,
            "neighborhood_ppm2": self.neighborhood_ppm2,
            "property_ppm2": self.property_ppm2,
            "combined_ppm2": self.combined_ppm2,
            "input_hashes": self.input_hashes,
            "feature_names": [*CATEGORICAL_FEATURES, "total_area_m2"],
        }
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        return path

    @classmethod
    def load(cls, path: Path) -> BaselineModel:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            global_ppm2=float(data["global_ppm2"]),
            neighborhood_ppm2={k: float(v) for k, v in data["neighborhood_ppm2"].items()},
            property_ppm2={k: float(v) for k, v in data["property_ppm2"].items()},
            combined_ppm2={k: float(v) for k, v in data["combined_ppm2"].items()},
            train_row_count=int(data["train_row_count"]),
            data_mode=str(data["data_mode"]),
            input_hashes={k: str(v) for k, v in data.get("input_hashes", {}).items()},
            fallback_order=tuple(data.get("fallback_order", _FALLBACK_ORDER)),
            version=str(data.get("version", BASELINE_VERSION)),
        )

    def sha256(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def as_metadata(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "train_row_count": self.train_row_count,
            "global_ppm2": self.global_ppm2,
            "fallback_order": list(self.fallback_order),
        }


def fit_baseline(
    train_frame: pd.DataFrame,
    *,
    data_mode: str,
    input_hashes: dict[str, str],
) -> BaselineModel:
    if train_frame.empty:
        raise ValueError("baseline requires a non-empty train frame")
    area = pd.to_numeric(train_frame["total_area_m2"], errors="coerce")
    price = pd.to_numeric(train_frame[TARGET_COLUMN], errors="coerce")
    ppm2 = (price / area).astype(float)
    if not np.isfinite(ppm2).all():
        raise ValueError("baseline: price_per_m2 is non-finite in train frame")

    global_median = float(ppm2.median())
    combined_medians: dict[str, float] = {}
    for (neighborhood, prop), group in train_frame.groupby(
        ["neighborhood_normalized", "property_type"], sort=False
    ):
        combined_medians[f"{neighborhood}|{prop}"] = float(
            (
                pd.to_numeric(group[TARGET_COLUMN], errors="coerce")
                / pd.to_numeric(group["total_area_m2"], errors="coerce")
            ).median()
        )
    neighborhood_medians: dict[str, float] = {}
    for neighborhood, group in train_frame.groupby("neighborhood_normalized", sort=False):
        neighborhood_medians[str(neighborhood)] = float(
            (
                pd.to_numeric(group[TARGET_COLUMN], errors="coerce")
                / pd.to_numeric(group["total_area_m2"], errors="coerce")
            ).median()
        )
    property_medians: dict[str, float] = {}
    for prop, group in train_frame.groupby("property_type", sort=False):
        property_medians[str(prop)] = float(
            (
                pd.to_numeric(group[TARGET_COLUMN], errors="coerce")
                / pd.to_numeric(group["total_area_m2"], errors="coerce")
            ).median()
        )

    return BaselineModel(
        global_ppm2=global_median,
        neighborhood_ppm2=neighborhood_medians,
        property_ppm2=property_medians,
        combined_ppm2=combined_medians,
        train_row_count=int(len(train_frame)),
        data_mode=data_mode,
        input_hashes=dict(input_hashes),
    )


def _predict(frame: pd.DataFrame, model: BaselineModel) -> np.ndarray:
    area = pd.to_numeric(frame["total_area_m2"], errors="coerce").astype(float).to_numpy()
    neighborhoods = frame["neighborhood_normalized"].astype(str).tolist()
    properties = frame["property_type"].astype(str).tolist()

    ppm2 = np.empty(len(frame), dtype=float)
    for i, (neigh, prop) in enumerate(zip(neighborhoods, properties, strict=True)):
        key = f"{neigh}|{prop}"
        value = model.combined_ppm2.get(key)
        if value is None:
            value = model.neighborhood_ppm2.get(neigh)
        if value is None:
            value = model.property_ppm2.get(prop)
        if value is None:
            value = model.global_ppm2
        ppm2[i] = float(value)

    prediction = np.clip(ppm2 * area, a_min=0.0, a_max=None)
    if not np.isfinite(prediction).all():
        raise ValueError("baseline: prediction produced non-finite values")
    return prediction


__all__ = ["BASELINE_VERSION", "BaselineModel", "fit_baseline"]
