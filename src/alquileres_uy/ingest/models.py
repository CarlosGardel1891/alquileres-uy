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
        }
