"""Data models shared across the ingestion pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RunStatus(str, Enum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


class QueryStatus(str, Enum):
    PLANNED = "planned"
    COMPLETED = "completed"
    FAILED = "failed"


class CandidateStatus(str, Enum):
    CANDIDATE = "candidate"
    EXCLUDED = "excluded"
    UNKNOWN = "unknown"


class SourceGateDecision(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"


# The project's closed scope for MercadoLibre Uruguay: monthly rentals
# for apartments and houses in Montevideo. A source can only be
# approved when *both* categories have been verified against the live
# site tree. This constant is the single source of truth used by the
# source gate, the approval writer and loader, and the query plan.
REQUIRED_PROPERTY_TYPES: frozenset[str] = frozenset({"apartment", "house"})


@dataclass(frozen=True)
class QuerySegment:
    """A deterministic partition of the search space.

    ``parameters`` holds the raw parameters that will be sent to
    ``/sites/{site_id}/search``. ``segment_key`` is a human-readable label
    for logging and the query manifest.
    """

    segment_key: str
    parameters: dict[str, Any]
    category_id: str | None = None
    property_type: str | None = None
    operation: str | None = None
    location: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    bedrooms: int | None = None
    neighborhood: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "segment_key": self.segment_key,
            "parameters": dict(self.parameters),
            "category_id": self.category_id,
            "property_type": self.property_type,
            "operation": self.operation,
            "location": self.location,
            "price_min": self.price_min,
            "price_max": self.price_max,
            "bedrooms": self.bedrooms,
            "neighborhood": self.neighborhood,
        }


@dataclass
class FieldCoverage:
    """Coverage of a single field across a sample of items."""

    total: int = 0
    present: int = 0

    @property
    def ratio(self) -> float:
        return self.present / self.total if self.total else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {"total": self.total, "present": self.present, "ratio": round(self.ratio, 4)}


@dataclass
class ItemClassification:
    item_id: str
    status: CandidateStatus
    reason: str | None = None


@dataclass
class SourceGateReport:
    decision: SourceGateDecision
    token_used: bool
    sample_size: int
    essential_coverage: dict[str, FieldCoverage] = field(default_factory=dict)
    date_created_coverage: FieldCoverage = field(default_factory=FieldCoverage)
    description_coverage: FieldCoverage = field(default_factory=FieldCoverage)
    operation_detection: str | None = None
    notes: list[str] = field(default_factory=list)
    categories_observed: list[str] = field(default_factory=list)
    available_filters: list[str] = field(default_factory=list)
    reported_total: int | None = None
    verified_category_ids: dict[str, str] = field(default_factory=dict)
    operation_value_coverage: FieldCoverage = field(default_factory=FieldCoverage)
    property_type_value_coverage: FieldCoverage = field(default_factory=FieldCoverage)
    montevideo_coverage: FieldCoverage = field(default_factory=FieldCoverage)
    target_valid_coverage: FieldCoverage = field(default_factory=FieldCoverage)
    classification_reasons: dict[str, int] = field(default_factory=dict)
    category_tree: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "token_used": self.token_used,
            "sample_size": self.sample_size,
            "essential_coverage": {k: v.as_dict() for k, v in self.essential_coverage.items()},
            "date_created_coverage": self.date_created_coverage.as_dict(),
            "description_coverage": self.description_coverage.as_dict(),
            "operation_detection": self.operation_detection,
            "notes": list(self.notes),
            "categories_observed": list(self.categories_observed),
            "available_filters": list(self.available_filters),
            "reported_total": self.reported_total,
            "verified_category_ids": dict(self.verified_category_ids),
            "operation_value_coverage": self.operation_value_coverage.as_dict(),
            "property_type_value_coverage": self.property_type_value_coverage.as_dict(),
            "montevideo_coverage": self.montevideo_coverage.as_dict(),
            "target_valid_coverage": self.target_valid_coverage.as_dict(),
            "classification_reasons": dict(self.classification_reasons),
            "category_tree": dict(self.category_tree),
        }


@dataclass(frozen=True)
class SampleItemClassification:
    """Per-item verdict used to compute the combined-target coverage."""

    item_id: str | None
    operation: str
    property_type: str
    location_valid: bool
    monthly_rental: bool
    allowed_property_type: bool
    valid_for_target: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ApprovedSourceContract:
    """Signed contract emitted by the source gate when it decides APPROVED.

    Loaded before an ingestion run. Guarantees that both the decision and
    the coverage evidence (report_sha256) are internally consistent, and
    exposes the *only* verified category ids the pipeline may use.
    """

    source: str
    site_id: str
    decision: str
    created_at: str
    category_ids: dict[str, str]
    available_filters: list[str]
    operation_filter: dict[str, Any]
    coverage: dict[str, Any]
    report_path: str
    report_sha256: str


@dataclass(frozen=True)
class ItemDiscovery:
    """First-seen metadata for an item within a single run."""

    item_id: str
    query_id: str
    segment_key: str
    position: int
    page_index: int
