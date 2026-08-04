"""Loader and integrity checker for the source gate approval artifact.

The ingestion pipeline refuses to run without a valid
``source_gate_approval.json`` produced by an APPROVED source gate. This
module is the single point that turns that file into an
:class:`ApprovedSourceContract` and enforces its invariants:

- the file exists;
- ``decision`` is ``APPROVED``;
- ``source`` and ``site_id`` match the pipeline's target;
- ``category_ids`` maps at least one property type to a non-empty ID;
- the referenced ``coverage.json`` exists and its SHA-256 matches the
  hash stored in the approval.

Any deviation raises a specific exception so the CLI can distinguish
missing/invalid/integrity failures and produce a clean exit code 2
without any network I/O or database writes.
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


def load_approved_contract(path: Path) -> ApprovedSourceContract:
    """Read and validate an approval file, returning the sealed contract."""
    path = Path(path)
    if not path.is_file():
        raise SourceGateApprovalMissing(f"source gate approval not found: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SourceGateApprovalInvalid(f"approval is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SourceGateApprovalInvalid("approval root must be a JSON object")

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

    category_ids = data.get("category_ids")
    if not isinstance(category_ids, dict) or not category_ids:
        raise SourceGateApprovalInvalid("approval has no verified categories under 'category_ids'")
    validated_categories: dict[str, str] = {}
    for property_type, category_id in category_ids.items():
        if not isinstance(category_id, str) or not category_id.strip():
            raise SourceGateApprovalInvalid(f"approval category id for {property_type!r} is empty")
        validated_categories[str(property_type)] = category_id.strip()

    missing = sorted(REQUIRED_PROPERTY_TYPES - validated_categories.keys())
    if missing:
        raise SourceGateApprovalInvalid(
            f"approval is missing required categories: {', '.join(missing)}"
        )

    report_name = data.get("source_gate_report_path")
    expected_hash = data.get("source_gate_report_sha256")
    if not isinstance(report_name, str) or not isinstance(expected_hash, str):
        raise SourceGateApprovalInvalid(
            "approval is missing source_gate_report_path or source_gate_report_sha256"
        )

    report_path = (path.parent / report_name).resolve()
    if not report_path.is_file():
        raise SourceGateApprovalIntegrityError(
            f"coverage report referenced by approval does not exist: {report_path}"
        )
    actual_hash = compute_sha256(report_path.read_bytes())
    if actual_hash != expected_hash:
        raise SourceGateApprovalIntegrityError(
            "coverage report SHA-256 does not match approval "
            f"(expected {expected_hash}, got {actual_hash})"
        )

    return ApprovedSourceContract(
        source=source,
        site_id=site_id,
        decision=decision,
        created_at=str(data.get("created_at", "")),
        category_ids=validated_categories,
        available_filters=list(data.get("available_filters") or []),
        operation_filter=dict(data.get("operation_filter") or {}),
        coverage=dict(data.get("essential_coverage") or {}),
        report_path=str(report_path),
        report_sha256=expected_hash,
    )


def write_approval(
    workdir: Path,
    *,
    report: SourceGateReport,
    coverage_path: Path,
    coverage_sha256: str,
) -> Path:
    """Emit ``source_gate_approval.json`` next to the coverage report.

    Only called by the source gate when the decision is ``APPROVED``.
    Never writes a token or any authorization header. Reference to the
    coverage file is stored as a *relative* path so the approval remains
    valid when the run folder is moved.
    """
    if report.decision is not SourceGateDecision.APPROVED:
        raise ValueError("write_approval must only be called for APPROVED source gate decisions")
    if not report.verified_category_ids:
        raise ValueError("cannot write approval without verified category ids")
    missing = sorted(REQUIRED_PROPERTY_TYPES - report.verified_category_ids.keys())
    if missing:
        raise ValueError(
            "cannot write approval: missing required property categories: " f"{', '.join(missing)}"
        )

    payload: dict[str, Any] = {
        "source": EXPECTED_SOURCE,
        "site_id": EXPECTED_SITE_ID,
        "decision": SourceGateDecision.APPROVED.value,
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "category_ids": dict(report.verified_category_ids),
        "available_filters": list(report.available_filters),
        "operation_filter": {
            "mode": report.operation_detection,
        },
        "sample_size": report.sample_size,
        "essential_coverage": {k: v.as_dict() for k, v in report.essential_coverage.items()},
        "date_created_coverage": report.date_created_coverage.as_dict(),
        "source_gate_report_path": Path(coverage_path).name,
        "source_gate_report_sha256": coverage_sha256,
    }
    approval_path, _ = atomic_write_json(Path(workdir) / APPROVAL_FILENAME, payload)
    return approval_path
