"""Tests for approval loading and integrity enforcement."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from alquileres_uy.ingest.approval import (
    APPROVAL_FILENAME,
    load_approved_contract,
    write_approval,
)
from alquileres_uy.ingest.errors import (
    SourceGateApprovalIntegrityError,
    SourceGateApprovalInvalid,
    SourceGateApprovalMissing,
)
from alquileres_uy.ingest.filesystem import atomic_write_json, compute_sha256
from alquileres_uy.ingest.models import (
    FieldCoverage,
    SourceGateDecision,
    SourceGateReport,
)

DEFAULT_CATEGORIES = {"apartment": "MLU_TEST_APARTMENT", "house": "MLU_TEST_HOUSE"}
DEFAULT_FILTERS = ["OPERATION", "PROPERTY_TYPE"]
DEFAULT_OPERATION_MODE = "attribute+category"

ESSENTIAL_FIELDS = (
    "price",
    "currency",
    "location",
    "property_type",
    "operation",
    "bedrooms",
    "surface",
)


def _valid_coverage(**overrides) -> dict:
    """Return a coverage payload that would legitimately have produced APPROVED."""
    coverage = {
        "decision": "APPROVED",
        "sample_size": 20,
        "essential_coverage": {
            field_name: {"total": 20, "present": 20, "ratio": 1.0}
            for field_name in ESSENTIAL_FIELDS
        },
        "date_created_coverage": {"total": 20, "present": 20, "ratio": 1.0},
        "description_coverage": {"total": 20, "present": 18, "ratio": 0.9},
        "verified_category_ids": dict(DEFAULT_CATEGORIES),
        "available_filters": list(DEFAULT_FILTERS),
        "operation_detection": DEFAULT_OPERATION_MODE,
        "operation_value_coverage": {"total": 20, "present": 19, "ratio": 0.95},
        "property_type_value_coverage": {"total": 20, "present": 20, "ratio": 1.0},
        "montevideo_coverage": {"total": 20, "present": 20, "ratio": 1.0},
        "target_valid_coverage": {"total": 20, "present": 18, "ratio": 0.9},
        "classification_reasons": {},
        "category_tree": {},
    }
    coverage.update(overrides)
    return coverage


def _valid_approval(coverage_sha: str, **overrides) -> dict:
    approval = {
        "source": "mercadolibre",
        "site_id": "MLU",
        "decision": "APPROVED",
        "created_at": "2026-08-04T17:00:00Z",
        "category_ids": dict(DEFAULT_CATEGORIES),
        "available_filters": list(DEFAULT_FILTERS),
        "operation_filter": {"mode": DEFAULT_OPERATION_MODE},
        "sample_size": 20,
        "source_gate_report_path": "coverage.json",
        "source_gate_report_sha256": coverage_sha,
    }
    approval.update(overrides)
    return approval


def _write_pair(
    workdir: Path,
    *,
    approval_overrides: dict | None = None,
    coverage_overrides: dict | None = None,
    coverage_body: dict | None = None,
) -> tuple[Path, Path]:
    """Write a matching pair (coverage.json, approval.json). Overrides are per-file."""
    if coverage_body is None:
        coverage_body = _valid_coverage(**(coverage_overrides or {}))
    coverage_path, coverage_sha = atomic_write_json(workdir / "coverage.json", coverage_body)
    approval = _valid_approval(coverage_sha, **(approval_overrides or {}))
    approval_path, _ = atomic_write_json(workdir / APPROVAL_FILENAME, approval)
    return approval_path, coverage_path


def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(SourceGateApprovalMissing):
        load_approved_contract(tmp_path / "nope.json")


def test_load_invalid_json_raises(tmp_path: Path) -> None:
    path = tmp_path / APPROVAL_FILENAME
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(SourceGateApprovalInvalid):
        load_approved_contract(path)


def test_load_rejects_decision_other_than_approved(tmp_path: Path) -> None:
    approval_path, _ = _write_pair(tmp_path, approval_overrides={"decision": "INCONCLUSIVE"})
    with pytest.raises(SourceGateApprovalInvalid, match="APPROVED"):
        load_approved_contract(approval_path)


def test_load_rejects_wrong_source(tmp_path: Path) -> None:
    approval_path, _ = _write_pair(tmp_path, approval_overrides={"source": "other"})
    with pytest.raises(SourceGateApprovalInvalid, match="source"):
        load_approved_contract(approval_path)


def test_load_rejects_wrong_site_id(tmp_path: Path) -> None:
    approval_path, _ = _write_pair(tmp_path, approval_overrides={"site_id": "MLA"})
    with pytest.raises(SourceGateApprovalInvalid, match="site_id"):
        load_approved_contract(approval_path)


def test_load_rejects_empty_category_ids(tmp_path: Path) -> None:
    approval_path, _ = _write_pair(tmp_path, approval_overrides={"category_ids": {}})
    with pytest.raises(SourceGateApprovalInvalid, match="categories"):
        load_approved_contract(approval_path)


def test_load_rejects_empty_category_id_value(tmp_path: Path) -> None:
    approval_path, _ = _write_pair(
        tmp_path,
        approval_overrides={"category_ids": {"apartment": "", "house": "MLU1466"}},
    )
    with pytest.raises(SourceGateApprovalInvalid, match="empty"):
        load_approved_contract(approval_path)


def test_load_rejects_partial_contract_only_house(tmp_path: Path) -> None:
    approval_path, _ = _write_pair(
        tmp_path, approval_overrides={"category_ids": {"house": "MLU1466"}}
    )
    with pytest.raises(SourceGateApprovalInvalid, match="apartment"):
        load_approved_contract(approval_path)


def test_load_rejects_partial_contract_only_apartment(tmp_path: Path) -> None:
    approval_path, _ = _write_pair(
        tmp_path, approval_overrides={"category_ids": {"apartment": "MLU1743"}}
    )
    with pytest.raises(SourceGateApprovalInvalid, match="house"):
        load_approved_contract(approval_path)


def test_load_error_message_names_the_missing_categories(tmp_path: Path) -> None:
    approval_path, _ = _write_pair(
        tmp_path, approval_overrides={"category_ids": {"garaje": "MLU9999"}}
    )
    with pytest.raises(SourceGateApprovalInvalid) as info:
        load_approved_contract(approval_path)
    assert "apartment" in str(info.value)
    assert "house" in str(info.value)


def test_load_rejects_missing_coverage_file(tmp_path: Path) -> None:
    approval_path, coverage_path = _write_pair(tmp_path)
    coverage_path.unlink()
    with pytest.raises(SourceGateApprovalIntegrityError):
        load_approved_contract(approval_path)


def test_load_rejects_tampered_coverage_file(tmp_path: Path) -> None:
    approval_path, coverage_path = _write_pair(tmp_path)
    coverage_path.write_bytes(coverage_path.read_bytes() + b"\n")
    with pytest.raises(SourceGateApprovalIntegrityError):
        load_approved_contract(approval_path)


def test_load_returns_contract_when_everything_matches(tmp_path: Path) -> None:
    approval_path, coverage_path = _write_pair(tmp_path)
    contract = load_approved_contract(approval_path)

    assert contract.source == "mercadolibre"
    assert contract.site_id == "MLU"
    assert contract.decision == "APPROVED"
    assert contract.category_ids == dict(DEFAULT_CATEGORIES)
    assert contract.report_sha256 == compute_sha256(coverage_path.read_bytes())


def test_load_never_returns_a_token_field(tmp_path: Path) -> None:
    approval_path, _ = _write_pair(tmp_path)
    payload = json.loads(approval_path.read_text(encoding="utf-8"))
    assert "access_token" not in payload
    assert "authorization" not in payload
    assert "MELI_ACCESS_TOKEN" not in payload


def test_write_approval_refuses_non_approved(tmp_path: Path) -> None:
    coverage_path, coverage_sha = atomic_write_json(tmp_path / "coverage.json", {"x": 1})
    report = SourceGateReport(
        decision=SourceGateDecision.INCONCLUSIVE,
        token_used=False,
        sample_size=0,
    )
    with pytest.raises(ValueError, match="APPROVED"):
        write_approval(
            tmp_path,
            report=report,
            coverage_path=coverage_path,
            coverage_sha256=coverage_sha,
        )


def test_write_approval_requires_verified_category_ids(tmp_path: Path) -> None:
    coverage_path, coverage_sha = atomic_write_json(tmp_path / "coverage.json", {"x": 1})
    report = SourceGateReport(
        decision=SourceGateDecision.APPROVED,
        token_used=False,
        sample_size=20,
        essential_coverage={},
        date_created_coverage=FieldCoverage(20, 20),
        verified_category_ids={},
    )
    with pytest.raises(ValueError, match="verified category"):
        write_approval(
            tmp_path,
            report=report,
            coverage_path=coverage_path,
            coverage_sha256=coverage_sha,
        )


def test_write_approval_rejects_report_with_only_one_category(tmp_path: Path) -> None:
    coverage_path, coverage_sha = atomic_write_json(tmp_path / "coverage.json", {"x": 1})
    report = SourceGateReport(
        decision=SourceGateDecision.APPROVED,
        token_used=False,
        sample_size=20,
        essential_coverage={},
        date_created_coverage=FieldCoverage(20, 20),
        verified_category_ids={"apartment": "MLU1743"},  # missing house
    )
    with pytest.raises(ValueError, match="house"):
        write_approval(
            tmp_path,
            report=report,
            coverage_path=coverage_path,
            coverage_sha256=coverage_sha,
        )


def test_write_approval_success(tmp_path: Path) -> None:
    coverage_body = _valid_coverage()
    coverage_path, coverage_sha = atomic_write_json(tmp_path / "coverage.json", coverage_body)
    report = SourceGateReport(
        decision=SourceGateDecision.APPROVED,
        token_used=False,
        sample_size=20,
        essential_coverage={field_name: FieldCoverage(20, 20) for field_name in ESSENTIAL_FIELDS},
        date_created_coverage=FieldCoverage(20, 20),
        verified_category_ids=dict(DEFAULT_CATEGORIES),
        available_filters=list(DEFAULT_FILTERS),
        operation_detection=DEFAULT_OPERATION_MODE,
        target_valid_coverage=FieldCoverage(20, 18),
    )
    approval_path = write_approval(
        tmp_path,
        report=report,
        coverage_path=coverage_path,
        coverage_sha256=coverage_sha,
    )

    contract = load_approved_contract(approval_path)
    assert contract.category_ids == dict(DEFAULT_CATEGORIES)
    assert contract.report_sha256 == coverage_sha


# ---- semantic bind between approval and coverage ----------------------


def test_load_rejects_when_category_ids_differ_between_approval_and_coverage(tmp_path: Path):
    approval_path, _ = _write_pair(
        tmp_path,
        approval_overrides={
            "category_ids": {"apartment": "MLU_TEST_APARTMENT", "house": "MLU_DIFFERENT"}
        },
    )
    with pytest.raises(SourceGateApprovalInvalid, match="category_ids"):
        load_approved_contract(approval_path)


def test_load_rejects_extra_category_in_approval(tmp_path: Path):
    approval_path, _ = _write_pair(
        tmp_path,
        approval_overrides={
            "category_ids": {
                **DEFAULT_CATEGORIES,
                "garage": "MLU_TEST_GARAGE",
            }
        },
    )
    with pytest.raises(SourceGateApprovalInvalid, match="extra"):
        load_approved_contract(approval_path)


def test_load_rejects_extra_category_in_coverage(tmp_path: Path):
    approval_path, _ = _write_pair(
        tmp_path,
        coverage_overrides={
            "verified_category_ids": {
                **DEFAULT_CATEGORIES,
                "garage": "MLU_TEST_GARAGE",
            }
        },
    )
    with pytest.raises(SourceGateApprovalInvalid, match="verified_category_ids"):
        load_approved_contract(approval_path)


def test_load_rejects_when_available_filters_differ(tmp_path: Path):
    approval_path, _ = _write_pair(
        tmp_path,
        approval_overrides={"available_filters": ["OPERATION"]},
        coverage_overrides={"available_filters": ["OPERATION", "PROPERTY_TYPE"]},
    )
    with pytest.raises(SourceGateApprovalInvalid, match="available_filters"):
        load_approved_contract(approval_path)


def test_load_rejects_when_operation_filter_mode_differs(tmp_path: Path):
    approval_path, _ = _write_pair(
        tmp_path,
        approval_overrides={"operation_filter": {"mode": "text-only"}},
    )
    with pytest.raises(SourceGateApprovalInvalid, match="operation_filter"):
        load_approved_contract(approval_path)


def test_load_rejects_when_sample_size_differs(tmp_path: Path):
    approval_path, _ = _write_pair(
        tmp_path,
        approval_overrides={"sample_size": 19},
    )
    with pytest.raises(SourceGateApprovalInvalid, match="sample_size"):
        load_approved_contract(approval_path)


def test_load_rejects_coverage_decision_inconclusive(tmp_path: Path):
    approval_path, _ = _write_pair(tmp_path, coverage_overrides={"decision": "INCONCLUSIVE"})
    with pytest.raises(SourceGateApprovalInvalid, match="coverage report decision"):
        load_approved_contract(approval_path)


def test_load_rejects_coverage_decision_rejected(tmp_path: Path):
    approval_path, _ = _write_pair(tmp_path, coverage_overrides={"decision": "REJECTED"})
    with pytest.raises(SourceGateApprovalInvalid, match="coverage report decision"):
        load_approved_contract(approval_path)


def test_load_rejects_coverage_with_target_below_threshold(tmp_path: Path):
    approval_path, _ = _write_pair(
        tmp_path,
        coverage_overrides={"target_valid_coverage": {"total": 20, "present": 15, "ratio": 0.75}},
    )
    with pytest.raises(SourceGateApprovalInvalid, match="target_valid_coverage"):
        load_approved_contract(approval_path)


def test_load_rejects_coverage_missing_target_valid(tmp_path: Path):
    body = _valid_coverage()
    body.pop("target_valid_coverage")
    approval_path, _ = _write_pair(tmp_path, coverage_body=body)
    with pytest.raises(SourceGateApprovalInvalid, match="target_valid_coverage"):
        load_approved_contract(approval_path)


def test_load_rejects_coverage_with_essential_field_below_threshold(tmp_path: Path):
    body = _valid_coverage()
    body["essential_coverage"]["price"] = {"total": 20, "present": 15, "ratio": 0.75}
    approval_path, _ = _write_pair(tmp_path, coverage_body=body)
    with pytest.raises(SourceGateApprovalInvalid, match="essential"):
        load_approved_contract(approval_path)


# ---- path traversal defense ------------------------------------------


def test_load_rejects_absolute_report_path(tmp_path: Path):
    approval_path, _ = _write_pair(
        tmp_path,
        approval_overrides={"source_gate_report_path": "/etc/passwd"},
    )
    with pytest.raises(SourceGateApprovalIntegrityError):
        load_approved_contract(approval_path)


def test_load_rejects_report_path_with_dotdot(tmp_path: Path):
    approval_path, _ = _write_pair(
        tmp_path,
        approval_overrides={"source_gate_report_path": "../coverage.json"},
    )
    with pytest.raises(SourceGateApprovalIntegrityError, match="escape"):
        load_approved_contract(approval_path)


def test_load_rejects_windows_absolute_path(tmp_path: Path):
    approval_path, _ = _write_pair(
        tmp_path,
        approval_overrides={"source_gate_report_path": "C:/otro/coverage.json"},
    )
    with pytest.raises(SourceGateApprovalIntegrityError):
        load_approved_contract(approval_path)


# ---- contract built from coverage ------------------------------------


def test_contract_values_are_taken_from_coverage_not_from_approval(tmp_path: Path):
    # The loader forbids category_ids that disagree with the coverage,
    # so we only vary a field the loader does not cross-check: created_at.
    approval_path, _ = _write_pair(
        tmp_path,
        approval_overrides={"created_at": "2026-08-04T18:00:00Z"},
    )
    contract = load_approved_contract(approval_path)
    assert contract.available_filters == sorted(DEFAULT_FILTERS)
    assert contract.category_ids == dict(DEFAULT_CATEGORIES)
    assert contract.operation_filter == {"mode": DEFAULT_OPERATION_MODE}


def test_manipulating_only_the_approval_breaks_the_check(tmp_path: Path):
    """A tampered approval that keeps the coverage hash valid is still rejected."""
    approval_path, coverage_path = _write_pair(tmp_path)
    # Overwrite the approval's category_ids without touching coverage.
    body = json.loads(approval_path.read_text(encoding="utf-8"))
    body["category_ids"] = {
        "apartment": "MLU_TAMPERED",
        "house": "MLU_TEST_HOUSE",
    }
    approval_path.unlink()
    approval_path.write_text(json.dumps(body), encoding="utf-8")
    # Coverage sha256 still matches (coverage untouched), but the
    # semantic comparison must fail.
    with pytest.raises(SourceGateApprovalInvalid, match="category_ids"):
        load_approved_contract(approval_path)


def test_manipulating_the_coverage_breaks_the_hash(tmp_path: Path):
    approval_path, coverage_path = _write_pair(tmp_path)
    coverage_path.write_bytes(coverage_path.read_bytes() + b"\n")
    with pytest.raises(SourceGateApprovalIntegrityError):
        load_approved_contract(approval_path)
