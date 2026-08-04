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


def _write_pair(
    workdir: Path,
    *,
    approval_overrides: dict | None = None,
    coverage_body: dict | None = None,
) -> tuple[Path, Path]:
    coverage_body = coverage_body if coverage_body is not None else {"decision": "APPROVED"}
    coverage_path, coverage_sha = atomic_write_json(workdir / "coverage.json", coverage_body)
    approval = {
        "source": "mercadolibre",
        "site_id": "MLU",
        "decision": "APPROVED",
        "created_at": "2026-08-04T17:00:00Z",
        "category_ids": {"apartment": "MLU1743", "house": "MLU1466"},
        "available_filters": ["OPERATION"],
        "operation_filter": {"mode": "attribute"},
        "essential_coverage": {},
        "source_gate_report_path": "coverage.json",
        "source_gate_report_sha256": coverage_sha,
    }
    if approval_overrides:
        approval.update(approval_overrides)
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
    assert contract.category_ids == {"apartment": "MLU1743", "house": "MLU1466"}
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
    coverage_path, coverage_sha = atomic_write_json(tmp_path / "coverage.json", {"x": 1})
    report = SourceGateReport(
        decision=SourceGateDecision.APPROVED,
        token_used=False,
        sample_size=20,
        essential_coverage={"price": FieldCoverage(20, 20)},
        date_created_coverage=FieldCoverage(20, 20),
        verified_category_ids={"apartment": "MLU1743", "house": "MLU1466"},
        available_filters=["OPERATION"],
        operation_detection="category+attribute",
    )
    approval_path = write_approval(
        tmp_path,
        report=report,
        coverage_path=coverage_path,
        coverage_sha256=coverage_sha,
    )

    contract = load_approved_contract(approval_path)
    assert contract.category_ids == {"apartment": "MLU1743", "house": "MLU1466"}
    assert contract.report_sha256 == coverage_sha
