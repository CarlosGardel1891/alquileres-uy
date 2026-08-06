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

    # Only hash the four required payloads. Never enumerate the directory —
    # that could accidentally cover unexpected files and mask a corruption.
    checksums = {
        name: sha256_file(directory / name) for name in sorted(REQUIRED_BUNDLE_PAYLOAD_FILES)
    }
    write_json(directory / "checksums.json", checksums)

    total_size = sum(p.stat().st_size for p in directory.iterdir() if p.is_file())
    if total_size > ARTIFACT_SIZE_LIMIT_BYTES:
        biggest = max(directory.iterdir(), key=lambda p: p.stat().st_size)
        raise ServingBundleError(
            f"serving bundle is {total_size} bytes, over the {ARTIFACT_SIZE_LIMIT_BYTES} limit; "
            f"largest file: {biggest.name}. Publish binary artifacts via GitHub Releases instead."
        )
    # Verify the bundle satisfies the loader's structural contract without
    # deserializing the model — catches builder regressions immediately.
    validate_serving_bundle_integrity(directory)
    return directory


def _save_serving_model(model_object: object, path: Path) -> None:
    # Baseline exposes a bespoke JSON save alongside the joblib dump for
    # human inspection; the serving loader still reads the joblib blob.
    joblib.dump(model_object, path)


_SHA256_HEX_RE = __import__("re").compile(r"^[0-9a-fA-F]{64}$")
REQUIRED_BUNDLE_PAYLOAD_FILES: frozenset[str] = frozenset(
    {
        "model.joblib",
        "metadata.json",
        "feature_schema.json",
        "residual_interval.json",
    }
)
REQUIRED_BUNDLE_FILES: frozenset[str] = REQUIRED_BUNDLE_PAYLOAD_FILES | {"checksums.json"}
_REQUIRED_VERSIONS: tuple[str, ...] = ("python", "numpy", "pandas", "scikit_learn", "joblib")


def load_serving_bundle(directory: Path, *, allow_fixture: bool = False) -> dict[str, Any]:
    """Load a serving bundle, deferring ``joblib.load`` until every gate passes.

    Order:

    1. resolve + confirm the directory contains exactly the five expected
       files and nothing else (no subdirs, no symlinks, no extras);
    2. validate ``checksums.json`` — keys must equal
       :data:`REQUIRED_BUNDLE_PAYLOAD_FILES`, values must be hex sha256,
       hash of every payload must match;
    3. only then read ``metadata.json``;
    4. verify ``bundle_version``, ``model_type``, ``data_mode``,
       ``deployable`` (boolean coherent with ``data_mode``) and
       ``model_artifact_sha256``;
    5. reject fixture bundles unless ``allow_fixture=True``;
    6. run :func:`validate_runtime_compatibility`;
    7. finally invoke ``joblib.load(model.joblib)``.

    Any failure raises :class:`ServingBundleError` before deserialization.
    """
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise ServingBundleError(f"serving bundle directory missing: {directory}")

    validate_serving_bundle_integrity(directory)

    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ServingBundleError("metadata.json root must be a JSON object")
    if metadata.get("bundle_version") != BUNDLE_VERSION:
        raise ServingBundleError(
            f"bundle_version mismatch: expected {BUNDLE_VERSION!r}, "
            f"got {metadata.get('bundle_version')!r}"
        )
    model_type = metadata.get("model_type")
    if model_type not in SERVING_ELIGIBLE_MODEL_NAMES:
        raise ServingBundleError(f"metadata.model_type is not eligible: {model_type!r}")

    data_mode = metadata.get("data_mode")
    if not isinstance(data_mode, str) or data_mode not in {"fixture", "real"}:
        raise ServingBundleError(f"metadata.data_mode is invalid: {data_mode!r}")

    deployable = metadata.get("deployable")
    # ``bool`` is a subclass of ``int``; use ``type(...) is bool`` to
    # reject ``0``, ``1``, ``"true"``, null and other look-alikes.
    if type(deployable) is not bool:
        raise ServingBundleError("metadata.deployable must be a boolean")

    expected_deployable = data_mode == "real"
    if deployable is not expected_deployable:
        raise ServingBundleError(
            f"metadata deployability is inconsistent: data_mode={data_mode!r} "
            f"requires deployable={'true' if expected_deployable else 'false'}"
        )

    declared_hash = metadata.get("model_artifact_sha256")
    actual_hash = sha256_file(directory / "model.joblib")
    if declared_hash != actual_hash:
        raise ServingBundleError(
            "metadata.model_artifact_sha256 does not match the model.joblib on disk"
        )

    if not deployable and not allow_fixture:
        raise ServingBundleError(
            "refusing to load a fixture serving bundle; pass allow_fixture=True in tests only"
        )

    validate_runtime_compatibility(metadata)

    model = joblib.load(directory / "model.joblib")
    return {"metadata": metadata, "model": model}


def validate_serving_bundle_integrity(directory: Path) -> None:
    """Check the bundle's structural + integrity contract without deserializing.

    Public helper used by :func:`build_serving_bundle` to verify a freshly
    written bundle without invoking ``joblib.load``.
    """
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise ServingBundleError(f"serving bundle directory missing: {directory}")
    _validate_bundle_file_set(directory)
    _validate_checksums(directory)


def _validate_bundle_file_set(directory: Path) -> None:
    """Enforce the exact top-level file set (no subdirs / symlinks / extras)."""
    actual: set[str] = set()
    for entry in directory.iterdir():
        # Reject subdirectories, symlinks and non-regular files up front.
        if entry.is_symlink():
            raise ServingBundleError(f"serving bundle contains a symlink: {entry.name!r}")
        if entry.is_dir():
            raise ServingBundleError(
                f"serving bundle contains an unexpected directory: {entry.name!r}"
            )
        if not entry.is_file():
            raise ServingBundleError(f"serving bundle entry {entry.name!r} is not a regular file")
        actual.add(entry.name)

    missing = sorted(REQUIRED_BUNDLE_FILES - actual)
    if missing:
        raise ServingBundleError(f"serving bundle is missing required files: {missing}")
    extra = sorted(actual - REQUIRED_BUNDLE_FILES)
    if extra:
        raise ServingBundleError(f"serving bundle contains undeclared files: {extra}")


def validate_runtime_compatibility(metadata: dict[str, Any]) -> None:
    """Raise if the current runtime is incompatible with the bundle.

    All entries in :data:`_REQUIRED_VERSIONS` (plus ``lightgbm`` for
    lightgbm bundles) must be declared and equal to the runtime. Missing
    declarations are rejected instead of silently accepted.
    """
    declared = metadata.get("versions")
    if not isinstance(declared, dict):
        raise ServingBundleError("metadata.versions must be an object")

    for required in _REQUIRED_VERSIONS:
        if required not in declared or not declared[required]:
            raise ServingBundleError(f"metadata.versions.{required} is required")

    current_python = ".".join(map(str, sys.version_info[:2]))
    declared_python = ".".join(str(declared["python"]).split(".")[:2])
    if declared_python != current_python:
        raise ServingBundleError(
            f"python version mismatch: bundle {declared_python}, runtime {current_python}"
        )
    _check_exact_version("numpy", declared, np.__version__)
    _check_exact_version("pandas", declared, pd.__version__)

    try:
        import sklearn
    except ImportError as exc:
        raise ServingBundleError("bundle requires scikit-learn at runtime") from exc
    _check_exact_version("scikit_learn", declared, sklearn.__version__)

    try:
        import joblib as _joblib
    except ImportError as exc:  # pragma: no cover — joblib is a hard dep
        raise ServingBundleError("bundle requires joblib at runtime") from exc
    _check_exact_version("joblib", declared, _joblib.__version__)

    if metadata.get("model_type") == "lightgbm":
        if "lightgbm" not in declared or not declared["lightgbm"]:
            raise ServingBundleError("lightgbm bundle must declare lightgbm version")
        try:
            import lightgbm
        except ImportError as exc:
            raise ServingBundleError("lightgbm bundle requires lightgbm at runtime") from exc
        _check_exact_version("lightgbm", declared, lightgbm.__version__)


def _check_exact_version(name: str, declared: dict, runtime: str) -> None:
    expected = declared.get(name)
    if expected != runtime:
        raise ServingBundleError(f"{name} version mismatch: bundle {expected}, runtime {runtime}")


def _validate_checksums(directory: Path) -> None:
    checksum_path = directory / "checksums.json"
    declared = json.loads(checksum_path.read_text(encoding="utf-8"))
    if not isinstance(declared, dict) or not declared:
        raise ServingBundleError("checksums.json must be a non-empty object")

    # Each key must be a safe simple filename with a valid sha256 hex.
    for name, expected in declared.items():
        if not isinstance(name, str) or not name:
            raise ServingBundleError(f"checksums.json entry name is not a string: {name!r}")
        if name == "checksums.json":
            raise ServingBundleError("checksums.json must not declare itself")
        if "/" in name or "\\" in name or ".." in Path(name).parts or Path(name).is_absolute():
            raise ServingBundleError(f"checksums.json entry {name!r} is not a safe filename")
        if len(name) >= 2 and name[1] == ":":
            raise ServingBundleError(
                f"checksums.json entry {name!r} looks like a Windows drive path"
            )
        if not isinstance(expected, str) or not _SHA256_HEX_RE.match(expected):
            raise ServingBundleError(
                f"checksums.json entry {name!r} does not carry a sha256 hex digest"
            )

    declared_keys = set(declared.keys())
    missing_entries = sorted(REQUIRED_BUNDLE_PAYLOAD_FILES - declared_keys)
    if missing_entries:
        raise ServingBundleError(f"checksums.json is missing required entries: {missing_entries}")
    extra_entries = sorted(declared_keys - REQUIRED_BUNDLE_PAYLOAD_FILES)
    if extra_entries:
        raise ServingBundleError(f"checksums.json contains unexpected entries: {extra_entries}")

    for name, expected in declared.items():
        target = directory / name
        if not target.is_file():
            raise ServingBundleError(f"checksums.json references missing file {name!r}")
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != expected:
            raise ServingBundleError(f"checksum mismatch for bundle file {name!r}")


__all__ = [
    "REQUIRED_BUNDLE_FILES",
    "REQUIRED_BUNDLE_PAYLOAD_FILES",
    "ResidualInterval",
    "ServingBundleError",
    "build_feature_schema",
    "build_serving_bundle",
    "compute_residual_interval",
    "load_serving_bundle",
    "validate_runtime_compatibility",
    "validate_serving_bundle_integrity",
]
