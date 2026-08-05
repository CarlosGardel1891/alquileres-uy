"""Serving-bundle assembly and rehydration.

The bundle is the pointed handoff to a future FastAPI image: one model
file, a runtime-checkable metadata JSON, a feature schema, an empirical
residual interval, and a checksum manifest. PyTorch cannot go in.

The loader refuses ``deployable=false`` bundles unless the caller
explicitly passes ``allow_fixture=True`` — only used inside tests to
verify the round-trip.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .artifacts import sha256_file, write_json
from .config import (
    ARTIFACT_SIZE_LIMIT_BYTES,
    BUNDLE_VERSION,
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    SERVING_ELIGIBLE_MODEL_NAMES,
    TARGET_COLUMN,
)


class ServingBundleError(RuntimeError):
    """Raised when the serving bundle cannot be built or loaded."""


@dataclass(frozen=True)
class ResidualInterval:
    method: str
    quantiles: tuple[float, float]
    values: tuple[float, float]
    validation_rows: int
    coverage: float
    data_mode: str

    def as_json(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "quantiles": {"lower": self.quantiles[0], "upper": self.quantiles[1]},
            "values": {"lower": self.values[0], "upper": self.values[1]},
            "validation_rows": self.validation_rows,
            "coverage_on_validation": self.coverage,
            "data_mode": self.data_mode,
            "warning": ("empirical residual interval; not a statistical confidence interval"),
        }


def compute_residual_interval(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    *,
    lower_q: float = 0.1,
    upper_q: float = 0.9,
    data_mode: str,
) -> ResidualInterval:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    if y_true.shape != y_pred.shape or y_true.size == 0:
        raise ServingBundleError("residual interval needs matching non-empty arrays")
    residuals = y_true - y_pred
    lower = float(np.quantile(residuals, lower_q))
    upper = float(np.quantile(residuals, upper_q))
    coverage = float(np.mean((residuals >= lower) & (residuals <= upper)))
    return ResidualInterval(
        method="empirical residual quantiles",
        quantiles=(lower_q, upper_q),
        values=(lower, upper),
        validation_rows=int(y_true.size),
        coverage=coverage,
        data_mode=data_mode,
    )


def build_feature_schema() -> dict[str, Any]:
    return {
        "target": TARGET_COLUMN,
        "target_excluded_from_input": True,
        "canonical_feature_order": list(NUMERIC_FEATURES) + list(CATEGORICAL_FEATURES),
        "required_fields": {
            "bedrooms": {"type": "number", "min": 0},
            "total_area_m2": {"type": "number", "exclusive_min": 0},
            "neighborhood_normalized": {"type": "string", "not_empty": True},
            "property_type": {"type": "string", "enum": ["apartment", "house"]},
        },
        "optional_fields": {
            "bathrooms": {"type": "number", "min": 0, "nullable": True},
        },
        "categorical_unknown_handling": {
            "neighborhood_normalized": "ignored (weighted as zero for linear, "
            "unknown token for tree/torch)",
            "property_type": "must match one of the enum values",
        },
    }


def _model_versions(model_name: str) -> dict[str, str]:
    versions: dict[str, str] = {
        "python": ".".join(map(str, sys.version_info[:3])),
        "numpy": np.__version__,
        "pandas": pd.__version__,
    }
    try:
        import sklearn

        versions["scikit_learn"] = sklearn.__version__
    except ImportError:
        pass
    try:
        import joblib as _joblib

        versions["joblib"] = _joblib.__version__
    except ImportError:
        pass
    if model_name == "lightgbm":
        try:
            import lightgbm

            versions["lightgbm"] = lightgbm.__version__
        except ImportError:
            pass
    return versions


def build_serving_bundle(
    directory: Path,
    *,
    model_name: str,
    model_object: object,
    validation_metrics: dict,
    test_metrics: dict,
    residual_interval: ResidualInterval,
    training_run_id: str,
    etl_run_id: str,
    data_mode: str,
    input_hashes: dict[str, str],
    git_commit: str | None,
    trained_at: str,
) -> Path:
    if model_name not in SERVING_ELIGIBLE_MODEL_NAMES:
        raise ServingBundleError(f"model {model_name!r} is not eligible for the serving bundle")
    directory.mkdir(parents=True, exist_ok=True)
    model_path = directory / "model.joblib"
    _save_serving_model(model_object, model_path)

    metadata = {
        "bundle_version": BUNDLE_VERSION,
        "model_type": model_name,
        "training_run_id": training_run_id,
        "etl_run_id": etl_run_id,
        "data_mode": data_mode,
        "deployable": data_mode == "real",
        "trained_at": trained_at,
        "git_commit": git_commit,
        "feature_list": list(NUMERIC_FEATURES) + list(CATEGORICAL_FEATURES),
        "target": TARGET_COLUMN,
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "input_hashes": dict(input_hashes),
        "versions": _model_versions(model_name),
        "model_artifact_sha256": sha256_file(model_path),
    }
    write_json(directory / "metadata.json", metadata)
    write_json(directory / "feature_schema.json", build_feature_schema())
    write_json(directory / "residual_interval.json", residual_interval.as_json())

    checksums = {
        p.name: sha256_file(p)
        for p in directory.iterdir()
        if p.is_file() and p.name != "checksums.json"
    }
    write_json(directory / "checksums.json", checksums)

    total_size = sum(p.stat().st_size for p in directory.iterdir() if p.is_file())
    if total_size > ARTIFACT_SIZE_LIMIT_BYTES:
        biggest = max(directory.iterdir(), key=lambda p: p.stat().st_size)
        raise ServingBundleError(
            f"serving bundle is {total_size} bytes, over the {ARTIFACT_SIZE_LIMIT_BYTES} limit; "
            f"largest file: {biggest.name}. Publish binary artifacts via GitHub Releases instead."
        )
    return directory


def _save_serving_model(model_object: object, path: Path) -> None:
    # Baseline exposes a bespoke JSON save alongside the joblib dump for
    # human inspection; the serving loader still reads the joblib blob.
    joblib.dump(model_object, path)


def load_serving_bundle(directory: Path, *, allow_fixture: bool = False) -> dict[str, Any]:
    directory = Path(directory).resolve()
    metadata_path = directory / "metadata.json"
    if not metadata_path.is_file():
        raise ServingBundleError(f"serving bundle metadata missing: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not metadata.get("deployable", False) and not allow_fixture:
        raise ServingBundleError(
            "refusing to load a fixture serving bundle; pass allow_fixture=True in tests only"
        )

    _validate_checksums(directory)
    model = joblib.load(directory / "model.joblib")
    return {"metadata": metadata, "model": model}


def validate_runtime_compatibility(metadata: dict[str, Any]) -> None:
    """Raise if the current runtime is incompatible with the bundle."""
    declared = metadata.get("versions", {})
    current_python = ".".join(map(str, sys.version_info[:2]))
    declared_python = ".".join(str(declared.get("python", "")).split(".")[:2])
    if declared_python and declared_python != current_python:
        raise ServingBundleError(
            f"python version mismatch: bundle {declared_python}, runtime {current_python}"
        )
    _check_version("numpy", declared, np.__version__)
    _check_version("pandas", declared, pd.__version__)
    try:
        import sklearn

        _check_version("scikit_learn", declared, sklearn.__version__)
    except ImportError:
        pass
    if metadata.get("model_type") == "lightgbm":
        try:
            import lightgbm

            _check_version("lightgbm", declared, lightgbm.__version__)
        except ImportError as exc:
            raise ServingBundleError("lightgbm bundle requires lightgbm at runtime") from exc


def _check_version(name: str, declared: dict, runtime: str) -> None:
    expected = declared.get(name)
    if expected and expected != runtime:
        raise ServingBundleError(f"{name} version mismatch: bundle {expected}, runtime {runtime}")


def _validate_checksums(directory: Path) -> None:
    checksum_path = directory / "checksums.json"
    if not checksum_path.is_file():
        raise ServingBundleError(f"checksums.json missing in bundle: {directory}")
    declared = json.loads(checksum_path.read_text(encoding="utf-8"))
    for name, expected in declared.items():
        actual = hashlib.sha256((directory / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ServingBundleError(f"checksum mismatch for bundle file {name!r}")


__all__ = [
    "ResidualInterval",
    "ServingBundleError",
    "build_feature_schema",
    "build_serving_bundle",
    "compute_residual_interval",
    "load_serving_bundle",
    "validate_runtime_compatibility",
]
