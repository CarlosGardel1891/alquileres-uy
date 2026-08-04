"""Data models and canonical column list for the ETL pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

ETL_SCHEMA_VERSION = "1.0.0"

DATA_MODE_FIXTURE = "fixture"
DATA_MODE_REAL = "real"

ALLOWED_OPERATIONS = frozenset({"monthly_rent"})
ALLOWED_PROPERTY_TYPES = frozenset({"apartment", "house"})
ALLOWED_DEPARTMENTS = frozenset({"Montevideo"})
ALLOWED_CURRENCIES = frozenset({"USD", "UYU"})

CANONICAL_COLUMN_ORDER: tuple[str, ...] = (
    "schema_version",
    "data_mode",
    "source",
    "source_run_id",
    "source_item_id",
    "raw_item_path",
    "raw_description_path",
    "listing_url",
    "title",
    "description",
    "description_reported",
    "date_created",
    "last_updated",
    "operation",
    "property_type",
    "department",
    "city",
    "neighborhood_raw",
    "neighborhood_normalized",
    "neighborhood_known",
    "latitude",
    "longitude",
    "price_original",
    "currency_original",
    "price_usd",
    "common_expenses_original",
    "common_expenses_currency",
    "common_expenses_usd",
    "common_expenses_reported",
    "common_expenses_currency_inferred",
    "total_monthly_cost_usd",
    "bedrooms",
    "rooms_total",
    "bathrooms",
    "total_area_m2",
    "covered_area_m2",
    "total_area_derived_from_covered",
    "floor",
    "parking_spaces",
    "garage",
    "furnished",
    "terrace",
    "new_build",
    "first_seen_at",
    "last_seen_at",
    "observations_count",
    "possible_duplicate_group_id",
    "exact_content_hash",
    "quality_issues",
    "etl_processed_at",
    "exchange_rate_uyu_per_usd",
    "exchange_rate_date",
    "exchange_rate_source",
)

MODEL_READY_REQUIRED_COLUMNS: tuple[str, ...] = (
    "source_item_id",
    "property_type",
    "neighborhood_normalized",
    "bedrooms",
    "total_area_m2",
    "price_usd",
    "date_created",
)

MODEL_READY_FORBIDDEN_COLUMNS: tuple[str, ...] = (
    "price_per_m2",
    "price_bucket",
    "total_monthly_cost_usd",
)

REJECTED_COLUMN_ORDER: tuple[str, ...] = (
    "source_item_id",
    "source_run_id",
    "raw_item_path",
    "rejection_reasons",
    "raw_category_id",
    "raw_currency",
    "raw_price",
    "raw_operation",
    "raw_property_type",
)

DUPLICATE_CANDIDATE_COLUMN_ORDER: tuple[str, ...] = (
    "possible_duplicate_group_id",
    "source_item_id",
    "property_type",
    "neighborhood_normalized",
    "bedrooms",
    "total_area_m2_bucket",
    "price_usd_bucket",
    "member_count",
)


@dataclass(frozen=True)
class ExtractedItem:
    """Intermediate typed representation between raw JSON and DataFrame."""

    source_item_id: str | None
    raw_item_path: str
    raw_description_path: str | None
    source_run_id: str
    body: dict[str, Any]
    description_body: dict[str, Any] | None
    first_seen_at: datetime | None
    last_seen_at: datetime | None


@dataclass(frozen=True)
class RowRejection:
    source_item_id: str | None
    source_run_id: str
    raw_item_path: str
    reasons: tuple[str, ...]
    raw_category_id: str | None
    raw_currency: str | None
    raw_price: float | None
    raw_operation: str | None
    raw_property_type: str | None


@dataclass
class QualityIssue:
    """A non-blocking quality note attached to a canonical row."""

    field: str
    code: str
    detail: str | None = None

    def as_dict(self) -> dict[str, str]:
        return {"field": self.field, "code": self.code, "detail": self.detail or ""}


@dataclass
class CanonicalRow:
    """Row-level container built by the extractor before DataFrame assembly."""

    columns: dict[str, Any] = field(default_factory=dict)
    quality_issues: list[QualityIssue] = field(default_factory=list)

    def set(self, name: str, value: Any) -> None:
        self.columns[name] = value

    def add_issue(self, field_name: str, code: str, detail: str | None = None) -> None:
        self.quality_issues.append(QualityIssue(field_name, code, detail))
