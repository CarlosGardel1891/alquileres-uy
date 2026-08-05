"""Input contract for the training pipeline.

Two independent gates live here:

* :func:`load_training_input` validates an ETL run directory before
  any training happens. It re-hashes ``model_ready.parquet``,
  ``etl_summary.json`` and ``schema.json`` against the lineage,
  checks the summary and schema shapes, and enforces the model-ready
  data contract (positive target, unique ids, tz-aware dates, etc.).
* :func:`load_etl_approval` gates real-mode training. Without an
  ``ETL_PRODUCTION_VALIDATED`` approval whose hashes match the
  loaded run, the pipeline refuses to touch the data.

Both raise :class:`TrainingInputError` with actionable messages so the
CLI can translate them to exit-code 2 without dumping a stack trace.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .config import (
    FORBIDDEN_FEATURE_COLUMNS,
    OPTIONAL_MODEL_READY_COLUMNS,
    REQUIRED_MODEL_READY_COLUMNS,
    SUPPORTED_ETL_SCHEMA_VERSIONS,
    TARGET_COLUMN,
)

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_APPROVED_DECISION: str = "ETL_PRODUCTION_VALIDATED"


class TrainingInputError(ValueError):
    """Raised when the ETL input or the approval payload is invalid."""


@dataclass(frozen=True)
class ETLApproval:
    """A validated ETL production-approval token."""

    status: str
    data_mode: str
    etl_run_id: str
    etl_summary_sha256: str
    lineage_sha256: str
    model_ready_sha256: str
    approved_at: datetime
    approved_by: str


@dataclass(frozen=True)
class TrainingInput:
    """A validated ETL run ready for training."""

    etl_run_dir: Path
    model_ready: pd.DataFrame
    etl_summary: dict[str, Any]
    lineage: dict[str, Any]
    schema: dict[str, Any]
    etl_run_id: str
    data_mode: str
    schema_version: str
    input_hashes: dict[str, str] = field(default_factory=dict)


# ---- ETL run --------------------------------------------------------


def load_training_input(etl_run_dir: Path) -> TrainingInput:
    etl_run_dir = Path(etl_run_dir).resolve()
    if not etl_run_dir.is_dir():
        raise TrainingInputError(f"etl run directory not found: {etl_run_dir}")

    files = {
        "model_ready": etl_run_dir / "model_ready.parquet",
        "etl_summary": etl_run_dir / "etl_summary.json",
        "lineage": etl_run_dir / "lineage.json",
        "schema": etl_run_dir / "schema.json",
    }
    for label, path in files.items():
        if not path.is_file():
            raise TrainingInputError(f"etl run is missing required file: {label} ({path.name})")

    hashes = {label: _sha256(path) for label, path in files.items()}

    summary = _load_json(files["etl_summary"], "etl_summary")
    lineage = _load_json(files["lineage"], "lineage")
    schema = _load_json(files["schema"], "schema")

    etl_run_id, data_mode, schema_version = _validate_summary(summary)
    _validate_lineage(lineage, etl_run_id, data_mode, schema_version, hashes, etl_run_dir)
    _validate_schema(schema, schema_version)
    frame = _validate_model_ready(files["model_ready"], schema)

    return TrainingInput(
        etl_run_dir=etl_run_dir,
        model_ready=frame,
        etl_summary=summary,
        lineage=lineage,
        schema=schema,
        etl_run_id=etl_run_id,
        data_mode=data_mode,
        schema_version=schema_version,
        input_hashes=hashes,
    )


def _validate_summary(summary: dict[str, Any]) -> tuple[str, str, str]:
    if summary.get("status") != "completed":
        raise TrainingInputError(
            f"etl summary status must be 'completed', got {summary.get('status')!r}"
        )
    data_mode = summary.get("data_mode")
    if data_mode not in {"fixture", "real"}:
        raise TrainingInputError(
            f"etl summary data_mode must be 'fixture' or 'real', got {data_mode!r}"
        )
    etl_run_id = summary.get("etl_run_id")
    if not isinstance(etl_run_id, str) or not etl_run_id.strip():
        raise TrainingInputError("etl summary etl_run_id must be a non-empty string")
    schema_version = summary.get("schema_version")
    if schema_version not in SUPPORTED_ETL_SCHEMA_VERSIONS:
        raise TrainingInputError(
            f"etl schema_version {schema_version!r} is not supported "
            f"(expected one of {SUPPORTED_ETL_SCHEMA_VERSIONS})"
        )
    for key in ("input_items", "canonical_items", "model_ready_items"):
        value = summary.get(key)
        if not isinstance(value, int) or value < 0:
            raise TrainingInputError(f"etl summary {key} must be a non-negative int, got {value!r}")
    for key in ("started_at", "finished_at"):
        raw = summary.get(key)
        parsed = _parse_aware(raw)
        if parsed is None:
            raise TrainingInputError(
                f"etl summary {key} must be an ISO-8601 timestamp with timezone"
            )
    return etl_run_id, data_mode, schema_version


def _validate_lineage(
    lineage: dict[str, Any],
    etl_run_id: str,
    data_mode: str,
    schema_version: str,
    hashes: dict[str, str],
    etl_run_dir: Path,
) -> None:
    if lineage.get("etl_run_id") != etl_run_id:
        raise TrainingInputError("lineage etl_run_id does not match etl_summary.etl_run_id")
    if lineage.get("data_mode") != data_mode:
        raise TrainingInputError("lineage data_mode does not match etl_summary.data_mode")
    if lineage.get("etl_schema_version") != schema_version:
        raise TrainingInputError(
            "lineage etl_schema_version does not match etl_summary.schema_version"
        )

    output_files = lineage.get("output_files")
    output_hashes = lineage.get("output_sha256")
    if not isinstance(output_files, dict) or not isinstance(output_hashes, dict):
        raise TrainingInputError("lineage.output_files / output_sha256 must both be objects")
    if output_files.get("model_ready") != "model_ready.parquet":
        raise TrainingInputError(
            "lineage.output_files.model_ready must equal 'model_ready.parquet'"
        )

    for label, expected_hash in (
        ("model_ready", hashes["model_ready"]),
        ("etl_summary", hashes["etl_summary"]),
        ("schema", hashes["schema"]),
    ):
        declared = output_hashes.get(label)
        if not isinstance(declared, str) or not _SHA256_RE.match(declared):
            raise TrainingInputError(
                f"lineage.output_sha256.{label} is missing or not a sha256 digest"
            )
        if declared.lower() != expected_hash.lower():
            raise TrainingInputError(
                f"lineage.output_sha256.{label} does not match the actual file "
                f"(declared {declared[:12]}…, actual {expected_hash[:12]}…)"
            )

    # Path safety on every declared output path.
    for label, relative in output_files.items():
        if not isinstance(relative, str) or not relative:
            raise TrainingInputError(f"lineage.output_files.{label} must be a non-empty string")
        candidate = Path(relative.replace("\\", "/"))
        if candidate.is_absolute() or ".." in candidate.parts:
            raise TrainingInputError(
                f"lineage.output_files.{label} escapes the etl run: {relative!r}"
            )
        resolved = (etl_run_dir / candidate).resolve()
        if not resolved.is_relative_to(etl_run_dir):
            raise TrainingInputError(f"lineage.output_files.{label} resolves outside the etl run")


def _validate_schema(schema: dict[str, Any], schema_version: str) -> None:
    if schema.get("schema_version") != schema_version:
        raise TrainingInputError("schema.json schema_version disagrees with etl_summary")
    required = schema.get("model_ready_required")
    if not isinstance(required, list) or not required:
        raise TrainingInputError("schema.json model_ready_required must be a non-empty list")
    missing = [c for c in REQUIRED_MODEL_READY_COLUMNS if c not in required]
    if missing:
        raise TrainingInputError(f"schema.json is missing required model-ready columns: {missing}")
    forbidden = schema.get("model_ready_forbidden", [])
    if not isinstance(forbidden, list):
        raise TrainingInputError("schema.json model_ready_forbidden must be a list")
    # `FORBIDDEN_FEATURE_COLUMNS` is the feature blocklist used at
    # training time (includes the target and identifiers). We do NOT
    # cross-check it against the ETL schema's required list — the
    # data model needs `source_item_id`, `date_created` and
    # `price_usd` to exist even though none of them become features.


def _validate_model_ready(path: Path, schema: dict[str, Any]) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    missing = [c for c in REQUIRED_MODEL_READY_COLUMNS if c not in frame.columns]
    if missing:
        raise TrainingInputError(f"model_ready.parquet is missing required columns: {missing}")

    forbidden_present = [c for c in schema.get("model_ready_forbidden", []) if c in frame.columns]
    if forbidden_present:
        raise TrainingInputError(
            f"model_ready.parquet contains forbidden columns: {forbidden_present}"
        )

    # source_item_id: real string instances (no int/bool/bytes/etc.),
    # non-empty when trimmed, unique across rows.
    _require_string_column(frame["source_item_id"], "source_item_id")
    if frame["source_item_id"].duplicated().any():
        raise TrainingInputError("source_item_id must be unique in model_ready.parquet")

    # property_type must be a real string with one of the allowed values.
    _require_string_column(frame["property_type"], "property_type")
    invalid_types = set(frame["property_type"].unique()) - {"apartment", "house"}
    if invalid_types:
        raise TrainingInputError(
            f"property_type contains unknown categories: {sorted(invalid_types)}"
        )

    # neighborhood_normalized must also be a real, non-empty string.
    _require_string_column(frame["neighborhood_normalized"], "neighborhood_normalized")

    # bedrooms: numeric, finite, no negatives, no nulls.
    _require_finite_non_negative(frame["bedrooms"], "bedrooms", allow_null=False)

    # bathrooms is optional at the parquet level. When present, values may
    # be null but any non-null value must be a real finite non-negative
    # number. When absent, downstream code injects an all-NaN column so
    # the classical imputer and the PyTorch median can operate on it.
    if "bathrooms" in frame.columns:
        _require_finite_non_negative(frame["bathrooms"], "bathrooms", allow_null=True)
    else:
        frame = frame.copy()
        frame["bathrooms"] = pd.array([pd.NA] * len(frame), dtype="Float64")

    # total_area_m2 / price_usd: strictly positive, finite.
    for column in ("total_area_m2", TARGET_COLUMN):
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.isnull().any():
            raise TrainingInputError(f"{column} must be numeric with no nulls")
        if not values.apply(lambda x: math.isfinite(float(x))).all():
            raise TrainingInputError(f"{column} contains non-finite values (NaN or Infinity)")
        if (values <= 0).any():
            raise TrainingInputError(f"{column} must be strictly greater than zero")

    # date_created: timezone-aware, normalized to UTC.
    dates = frame["date_created"]
    if dates.isnull().any():
        raise TrainingInputError("date_created has null values")
    if not pd.api.types.is_datetime64_any_dtype(dates):
        raise TrainingInputError("date_created must be a datetime column")
    tz = getattr(dates.dtype, "tz", None)
    if tz is None:
        raise TrainingInputError("date_created must be timezone-aware")
    # Normalize to UTC for downstream comparisons; pandas keeps the tz.
    if str(tz) != "UTC":
        frame = frame.copy()
        frame["date_created"] = dates.dt.tz_convert(UTC)

    for column in OPTIONAL_MODEL_READY_COLUMNS:
        if column in frame.columns:
            pass  # already validated above when relevant

    return frame


# ---- Approval --------------------------------------------------------


def load_etl_approval(path: Path, training_input: TrainingInput) -> ETLApproval:
    if not path.is_file():
        raise TrainingInputError(f"etl approval file not found: {path}")
    payload = _load_json(path, "etl approval")
    approval = _build_approval(payload)

    if training_input.data_mode != "real":
        raise TrainingInputError(
            "etl approval requires a real ETL run (data_mode='real'); refusing to mix modes"
        )
    if approval.etl_run_id != training_input.etl_run_id:
        raise TrainingInputError("approval etl_run_id does not match the loaded etl run")
    for label, actual in (
        ("etl_summary_sha256", training_input.input_hashes["etl_summary"]),
        ("lineage_sha256", training_input.input_hashes["lineage"]),
        ("model_ready_sha256", training_input.input_hashes["model_ready"]),
    ):
        expected = getattr(approval, label)
        if expected.lower() != actual.lower():
            raise TrainingInputError(
                f"approval {label} does not match the actual file "
                f"({expected[:12]}… vs {actual[:12]}…)"
            )
    return approval


def _build_approval(payload: dict[str, Any]) -> ETLApproval:
    if payload.get("status") != _APPROVED_DECISION:
        raise TrainingInputError(
            f"etl approval status must be {_APPROVED_DECISION!r}, got {payload.get('status')!r}"
        )
    if payload.get("data_mode") != "real":
        raise TrainingInputError("etl approval data_mode must be 'real'")
    for key in ("etl_run_id", "approved_by"):
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise TrainingInputError(f"etl approval {key} must be a non-empty string")
    for key in ("etl_summary_sha256", "lineage_sha256", "model_ready_sha256"):
        value = payload.get(key)
        if not isinstance(value, str) or not _SHA256_RE.match(value):
            raise TrainingInputError(f"etl approval {key} must be 64 hex chars")
    approved_at = _parse_aware(payload.get("approved_at"))
    if approved_at is None:
        raise TrainingInputError("etl approval approved_at must be an ISO-8601 timestamp with tz")
    return ETLApproval(
        status=payload["status"],
        data_mode=payload["data_mode"],
        etl_run_id=payload["etl_run_id"],
        etl_summary_sha256=payload["etl_summary_sha256"],
        lineage_sha256=payload["lineage_sha256"],
        model_ready_sha256=payload["model_ready_sha256"],
        approved_at=approved_at,
        approved_by=payload["approved_by"],
    )


# ---- leakage guard ---------------------------------------------------


def check_training_leakage(feature_columns: list[str] | tuple[str, ...]) -> None:
    """Raise if any prohibited column has leaked into the feature list."""
    prohibited = set(FORBIDDEN_FEATURE_COLUMNS) & set(feature_columns)
    if prohibited:
        raise TrainingInputError(
            f"leakage guard: feature list contains forbidden columns: {sorted(prohibited)}"
        )


# ---- helpers --------------------------------------------------------


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TrainingInputError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise TrainingInputError(f"{label} root must be a JSON object")
    return data


def _require_string_column(series: pd.Series, name: str) -> None:
    """Enforce that every value in ``series`` is a real, non-empty string."""
    for value in series.tolist():
        if not isinstance(value, str):
            raise TrainingInputError(
                f"{name} must contain string values; got {type(value).__name__}"
            )
        if not value.strip():
            raise TrainingInputError(f"{name} must not be empty or whitespace-only")


def _require_finite_non_negative(series: pd.Series, name: str, *, allow_null: bool) -> None:
    """Enforce that ``series`` is numeric-castable, finite, and ≥ 0."""
    for raw in series.tolist():
        if raw is None or (isinstance(raw, float) and math.isnan(raw)) or raw is pd.NA:
            if allow_null:
                continue
            raise TrainingInputError(f"{name} must be numeric with no null values")
        if isinstance(raw, bool):  # bool is an int subclass — reject explicitly.
            raise TrainingInputError(f"{name} must be numeric; got bool")
        try:
            as_float = float(raw)
        except (TypeError, ValueError) as exc:
            raise TrainingInputError(
                f"{name} must contain finite numeric values; got {raw!r}"
            ) from exc
        if not math.isfinite(as_float):
            raise TrainingInputError(f"{name} contains non-finite values (NaN or Infinity)")
        if as_float < 0:
            raise TrainingInputError(f"{name} must be non-negative")


def _parse_aware(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


__all__ = [
    "ETLApproval",
    "TrainingInput",
    "TrainingInputError",
    "check_training_leakage",
    "load_etl_approval",
    "load_training_input",
]
