"""Loader and integrity checker for the source gate approval artifact.

The ingestion pipeline refuses to run without a valid
``source_gate_approval.json`` produced by an APPROVED source gate. The
approval acts as a *pointer* to the ``coverage.json`` report — the real
source of truth for the approved contract. Loading the approval means:

1. the approval file exists and is well-formed JSON;
2. its ``decision`` is ``APPROVED``;
3. its ``source`` and ``site_id`` match the pipeline's target;
4. its ``category_ids`` contain **exactly** the required property types
   (``apartment`` and ``house``), with no extras;
5. its ``source_gate_report_path`` resolves inside the approval's
   directory (no path traversal);
6. that path exists and its SHA-256 matches ``source_gate_report_sha256``;
7. the referenced ``coverage.json`` is a JSON object whose own
   ``decision`` is ``APPROVED``;
8. every semantic field the approval also carries
   (``category_ids``, ``available_filters``, ``operation_filter.mode``,
   ``sample_size``) matches the coverage report exactly;
9. the coverage's own thresholds (sample_size, essential fields,
   date_created, target-valid) actually pass;
10. the constructed :class:`ApprovedSourceContract` takes its values
    from the coverage report, never from the approval file.

Any deviation raises a specific exception so the CLI can distinguish
missing/invalid/integrity failures and exit cleanly with code 2 without
any network I/O or database writes.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .errors import (
    SourceGateApprovalIntegrityError,
    SourceGateApprovalInvalid,
    SourceGateApprovalMissing,
)
from .filesystem import atomic_write_json, compute_sha256
from .models import (
    REQUIRED_PROPERTY_TYPES,
    ApprovedSourceContract,
    SourceGateDecision,
    SourceGateReport,
)

APPROVAL_FILENAME = "source_gate_approval.json"
EXPECTED_SOURCE = "mercadolibre"
EXPECTED_SITE_ID = "MLU"
SAMPLE_SIZE_REQUIRED = 20
MIN_ESSENTIAL_HITS_REQUIRED = 16
MIN_DATE_HITS_REQUIRED = 16
MIN_TARGET_HITS_REQUIRED = 16
ESSENTIAL_FIELDS_REQUIRED: tuple[str, ...] = (
    "price",
    "currency",
    "location",
    "property_type",
    "operation",
    "bedrooms",
    "surface",
)


def load_approved_contract(path: Path) -> ApprovedSourceContract:
    """Read and validate an approval file, returning the sealed contract."""
    path = Path(path)
    if not path.is_file():
        raise SourceGateApprovalMissing(f"source gate approval not found: {path}")

    approval_data = _read_json(path, invalid_message=f"approval is not valid JSON in {path}")

    _validate_basic_approval_shape(approval_data)
    approval_categories = _validate_and_extract_categories(approval_data)

    report_name = approval_data.get("source_gate_report_path")
    expected_hash = approval_data.get("source_gate_report_sha256")
    if not isinstance(report_name, str) or not isinstance(expected_hash, str):
        raise SourceGateApprovalInvalid(
            "approval is missing source_gate_report_path or source_gate_report_sha256"
        )

    approval_dir = path.parent.resolve()
    coverage_path = _resolve_report_path(approval_dir, report_name)
    if not coverage_path.is_file():
        raise SourceGateApprovalIntegrityError(
            f"coverage report referenced by approval does not exist: {coverage_path}"
        )

    actual_hash = compute_sha256(coverage_path.read_bytes())
    if actual_hash != expected_hash:
        raise SourceGateApprovalIntegrityError(
            "coverage report SHA-256 does not match approval "
            f"(expected {expected_hash}, got {actual_hash})"
        )

    coverage_data = _read_json(
        coverage_path,
        invalid_message=f"coverage report is not valid JSON in {coverage_path}",
    )
    _validate_coverage_report(
        coverage_data, approval=approval_data, approval_categories=approval_categories
    )

    return ApprovedSourceContract(
        source=approval_data["source"],
        site_id=approval_data["site_id"],
        decision=approval_data["decision"],
        created_at=str(approval_data.get("created_at", "")),
        # Contract values are always taken from the coverage report — the
        # approval only *confirms* them.
        category_ids={
            pt: coverage_data["verified_category_ids"][pt] for pt in sorted(REQUIRED_PROPERTY_TYPES)
        },
        available_filters=sorted(coverage_data.get("available_filters") or []),
        operation_filter={"mode": coverage_data.get("operation_detection")},
        coverage=dict(coverage_data.get("essential_coverage") or {}),
        report_path=str(coverage_path),
        report_sha256=expected_hash,
    )


def write_approval(
    workdir: Path,
    *,
    report: SourceGateReport,
    coverage_path: Path,
    coverage_sha256: str,
) -> Path:
    """Emit ``source_gate_approval.json`` next to the coverage report."""
    if report.decision is not SourceGateDecision.APPROVED:
        raise ValueError("write_approval must only be called for APPROVED source gate decisions")
    if not report.verified_category_ids:
        raise ValueError("cannot write approval without verified category ids")
    missing = sorted(REQUIRED_PROPERTY_TYPES - report.verified_category_ids.keys())
    if missing:
        raise ValueError(
            "cannot write approval: missing required property categories: " f"{', '.join(missing)}"
        )
    extras = sorted(report.verified_category_ids.keys() - REQUIRED_PROPERTY_TYPES)
    if extras:
        raise ValueError(
            "cannot write approval: extra property categories are not allowed: "
            f"{', '.join(extras)}"
        )

    payload: dict[str, Any] = {
        "source": EXPECTED_SOURCE,
        "site_id": EXPECTED_SITE_ID,
        "decision": SourceGateDecision.APPROVED.value,
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "category_ids": {
            pt: report.verified_category_ids[pt] for pt in sorted(REQUIRED_PROPERTY_TYPES)
        },
        "available_filters": sorted(report.available_filters),
        "operation_filter": {"mode": report.operation_detection},
        "sample_size": report.sample_size,
        "essential_coverage": {k: v.as_dict() for k, v in report.essential_coverage.items()},
        "date_created_coverage": report.date_created_coverage.as_dict(),
        "target_valid_coverage": report.target_valid_coverage.as_dict(),
        "source_gate_report_path": Path(coverage_path).name,
        "source_gate_report_sha256": coverage_sha256,
    }
    approval_path, _ = atomic_write_json(Path(workdir) / APPROVAL_FILENAME, payload)
    return approval_path


# ---- internals ---------------------------------------------------------


def _read_json(path: Path, *, invalid_message: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SourceGateApprovalInvalid(invalid_message + f": {exc}") from exc
    if not isinstance(data, dict):
        raise SourceGateApprovalInvalid(invalid_message + ": root must be a JSON object")
    return data


def _validate_basic_approval_shape(data: dict[str, Any]) -> None:
    decision = data.get("decision")
    if decision != SourceGateDecision.APPROVED.value:
        raise SourceGateApprovalInvalid(f"approval decision must be APPROVED, got {decision!r}")

    source = data.get("source")
    if source != EXPECTED_SOURCE:
        raise SourceGateApprovalInvalid(
            f"approval source must be {EXPECTED_SOURCE!r}, got {source!r}"
        )

    site_id = data.get("site_id")
    if site_id != EXPECTED_SITE_ID:
        raise SourceGateApprovalInvalid(
            f"approval site_id must be {EXPECTED_SITE_ID!r}, got {site_id!r}"
        )


def _validate_and_extract_categories(data: dict[str, Any]) -> dict[str, str]:
    raw = data.get("category_ids")
    if not isinstance(raw, dict) or not raw:
        raise SourceGateApprovalInvalid("approval has no verified categories under 'category_ids'")
    validated: dict[str, str] = {}
    for property_type, category_id in raw.items():
        if not isinstance(category_id, str) or not category_id.strip():
            raise SourceGateApprovalInvalid(f"approval category id for {property_type!r} is empty")
        validated[str(property_type)] = category_id.strip()

    missing = sorted(REQUIRED_PROPERTY_TYPES - validated.keys())
    if missing:
        raise SourceGateApprovalInvalid(
            f"approval is missing required categories: {', '.join(missing)}"
        )
    extras = sorted(validated.keys() - REQUIRED_PROPERTY_TYPES)
    if extras:
        raise SourceGateApprovalInvalid(
            f"approval contains extra property categories: {', '.join(extras)}"
        )
    return validated


def _resolve_report_path(approval_dir: Path, report_name: str) -> Path:
    candidate = Path(report_name)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise SourceGateApprovalIntegrityError(
            f"approval report path is not allowed to escape its directory: {report_name!r}"
        )
    resolved = (approval_dir / candidate).resolve()
    if not resolved.is_relative_to(approval_dir):
        raise SourceGateApprovalIntegrityError(
            f"approval report path resolves outside its directory: {report_name!r}"
        )
    return resolved


def _validate_coverage_report(
    coverage: dict[str, Any],
    *,
    approval: dict[str, Any],
    approval_categories: dict[str, str],
) -> None:
    if coverage.get("decision") != SourceGateDecision.APPROVED.value:
        raise SourceGateApprovalInvalid(
            "coverage report decision must be APPROVED, " f"got {coverage.get('decision')!r}"
        )

    coverage_categories = coverage.get("verified_category_ids")
    if not isinstance(coverage_categories, dict) or not coverage_categories:
        raise SourceGateApprovalInvalid("coverage report has no verified_category_ids")
    if set(coverage_categories.keys()) != set(REQUIRED_PROPERTY_TYPES):
        raise SourceGateApprovalInvalid(
            "coverage verified_category_ids keys must be exactly "
            f"{sorted(REQUIRED_PROPERTY_TYPES)}, got {sorted(coverage_categories.keys())}"
        )
    if coverage_categories != approval_categories:
        raise SourceGateApprovalInvalid(
            "approval category_ids do not match coverage verified_category_ids"
        )

    approval_filters = sorted(approval.get("available_filters") or [])
    coverage_filters = sorted(coverage.get("available_filters") or [])
    if approval_filters != coverage_filters:
        raise SourceGateApprovalInvalid(
            "approval available_filters do not match coverage available_filters"
        )

    approval_mode = _dig(approval, "operation_filter", "mode")
    coverage_mode = coverage.get("operation_detection")
    if approval_mode != coverage_mode:
        raise SourceGateApprovalInvalid(
            "approval operation_filter.mode does not match coverage operation_detection"
        )

    if approval.get("sample_size") != coverage.get("sample_size"):
        raise SourceGateApprovalInvalid("approval sample_size does not match coverage sample_size")

    _validate_coverage_thresholds(coverage)


def _dig(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _validate_coverage_thresholds(coverage: dict[str, Any]) -> None:
    if coverage.get("sample_size") != SAMPLE_SIZE_REQUIRED:
        raise SourceGateApprovalInvalid(
            f"coverage sample_size must be {SAMPLE_SIZE_REQUIRED}, "
            f"got {coverage.get('sample_size')}"
        )

    essential = coverage.get("essential_coverage")
    if not isinstance(essential, dict):
        raise SourceGateApprovalInvalid("coverage essential_coverage must be an object")
    for field_name in ESSENTIAL_FIELDS_REQUIRED:
        entry = essential.get(field_name)
        if not isinstance(entry, dict) or entry.get("present", -1) < MIN_ESSENTIAL_HITS_REQUIRED:
            raise SourceGateApprovalInvalid(
                f"coverage essential field {field_name!r} below "
                f"{MIN_ESSENTIAL_HITS_REQUIRED} of {SAMPLE_SIZE_REQUIRED}"
            )

    date_cov = coverage.get("date_created_coverage")
    if not isinstance(date_cov, dict) or date_cov.get("present", -1) < MIN_DATE_HITS_REQUIRED:
        raise SourceGateApprovalInvalid(
            f"coverage date_created_coverage below {MIN_DATE_HITS_REQUIRED} of "
            f"{SAMPLE_SIZE_REQUIRED}"
        )

    target = coverage.get("target_valid_coverage")
    if not isinstance(target, dict):
        raise SourceGateApprovalInvalid("coverage is missing target_valid_coverage")
    if target.get("present", -1) < MIN_TARGET_HITS_REQUIRED:
        raise SourceGateApprovalInvalid(
            f"coverage target_valid_coverage below {MIN_TARGET_HITS_REQUIRED} of "
            f"{SAMPLE_SIZE_REQUIRED}"
        )
