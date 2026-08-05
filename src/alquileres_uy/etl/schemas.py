"""Pandera schemas for the four ETL output datasets."""

from __future__ import annotations

import pandera as pa
from pandera import Check, Column, DataFrameSchema, Index

from .models import (
    ALLOWED_CURRENCIES,
    ALLOWED_DEPARTMENTS,
    ALLOWED_OPERATIONS,
    ALLOWED_PROPERTY_TYPES,
    MODEL_READY_FORBIDDEN_COLUMNS,
)


def _string_col(nullable: bool = False, **kwargs: object) -> Column:
    return Column(pa.String, nullable=nullable, **kwargs)


CanonicalListingsSchema = DataFrameSchema(
    columns={
        "source_item_id": _string_col(
            nullable=False,
            checks=[Check.str_length(min_value=1), Check(lambda s: ~s.isna().any())],
            unique=True,
        ),
        "source": _string_col(nullable=False),
        "source_run_id": _string_col(nullable=False),
        "raw_item_path": _string_col(nullable=False),
        "operation": _string_col(
            checks=Check.isin(sorted(ALLOWED_OPERATIONS)),
        ),
        "property_type": _string_col(
            checks=Check.isin(sorted(ALLOWED_PROPERTY_TYPES)),
        ),
        "department": _string_col(
            checks=Check.isin(sorted(ALLOWED_DEPARTMENTS)),
        ),
        "currency_original": _string_col(
            checks=Check.isin(sorted(ALLOWED_CURRENCIES)),
        ),
        "price_usd": Column(pa.Float64, checks=Check.greater_than(0)),
    },
    strict=False,
    coerce=True,
    index=Index(pa.Int64, name=None),
)


ModelReadySchema = DataFrameSchema(
    columns={
        "source_item_id": _string_col(nullable=False, unique=True),
        "property_type": _string_col(
            nullable=False,
            checks=Check.isin(sorted(ALLOWED_PROPERTY_TYPES)),
        ),
        "neighborhood_normalized": _string_col(nullable=False),
        "bedrooms": Column(pa.Int64, nullable=False, checks=Check.greater_than_or_equal_to(0)),
        "total_area_m2": Column(pa.Float64, nullable=False, checks=Check.greater_than(0)),
        "price_usd": Column(pa.Float64, nullable=False, checks=Check.greater_than(0)),
        "date_created": Column(pa.DateTime, nullable=False),
    },
    strict=False,
    coerce=True,
)


RejectedListingsSchema = DataFrameSchema(
    columns={
        "source_run_id": _string_col(nullable=False),
        "raw_item_path": _string_col(nullable=False),
        "rejection_reasons": _string_col(
            nullable=False,
            checks=Check.str_length(min_value=1),
        ),
    },
    strict=False,
    coerce=True,
)


DuplicateCandidatesSchema = DataFrameSchema(
    columns={
        "possible_duplicate_group_id": _string_col(nullable=False),
        "source_item_id": _string_col(nullable=False),
        "member_count": Column(pa.Int64, checks=Check.greater_than_or_equal_to(2)),
    },
    strict=False,
    coerce=True,
)


def check_model_ready_leakage(columns: list[str]) -> None:
    """Raise :class:`ValueError` if any target-derived column is present."""
    leaked = sorted(set(MODEL_READY_FORBIDDEN_COLUMNS) & set(columns))
    if leaked:
        raise ValueError(
            "model_ready must not contain target-derived columns: " + ", ".join(leaked)
        )
