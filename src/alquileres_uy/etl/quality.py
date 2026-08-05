"""Data quality report assembly."""

from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd


def build_quality_report(
    *,
    canonical: pd.DataFrame,
    model_ready: pd.DataFrame,
    rejected: pd.DataFrame,
    duplicate_candidates: pd.DataFrame,
    input_items: int,
    parsed_items: int,
    unmapped_attribute_counts: dict[str, int],
    area_inconsistencies: int,
    invalid_dates: int,
    common_expenses_missing: int,
    data_mode: str,
) -> dict[str, Any]:
    """Return the payload for ``data_quality_report.json``."""
    rejections_by_reason: Counter[str] = Counter()
    if not rejected.empty and "rejection_reasons" in rejected.columns:
        for reasons in rejected["rejection_reasons"].dropna():
            for reason in str(reasons).split("|"):
                reason = reason.strip()
                if reason:
                    rejections_by_reason[reason] += 1

    report: dict[str, Any] = {
        "data_mode": data_mode,
        "input_items": input_items,
        "parsed_items": parsed_items,
        "canonical_items": int(len(canonical)),
        "model_ready_items": int(len(model_ready)),
        "rejected_items": int(len(rejected)),
        "rejections_by_reason": dict(rejections_by_reason),
        "missingness_by_field": _missingness(canonical),
        "currency_distribution": _distribution(canonical, "currency_original"),
        "property_type_distribution": _distribution(canonical, "property_type"),
        "neighborhood_distribution": _distribution(canonical, "neighborhood_normalized"),
        "operation_distribution": _distribution(canonical, "operation"),
        "exact_id_duplicates": _exact_id_duplicates(canonical),
        "exact_content_groups": _exact_content_groups(canonical),
        "possible_duplicate_groups": int(len(duplicate_candidates)),
        "invalid_dates": invalid_dates,
        "unmapped_attributes": dict(unmapped_attribute_counts),
        "area_inconsistencies": area_inconsistencies,
        "common_expenses_missing": common_expenses_missing,
    }
    if data_mode == "fixture":
        report["warning"] = (
            "These metrics are produced from synthetic fixtures and are not project results."
        )
    return report


def _missingness(df: pd.DataFrame) -> dict[str, int]:
    if df.empty:
        return {}
    return {column: int(df[column].isna().sum()) for column in df.columns}


def _distribution(df: pd.DataFrame, column: str) -> dict[str, int]:
    if df.empty or column not in df.columns:
        return {}
    counts = df[column].fillna("__missing__").value_counts()
    return {str(index): int(value) for index, value in counts.items()}


def _exact_id_duplicates(df: pd.DataFrame) -> int:
    if df.empty or "source_item_id" not in df.columns:
        return 0
    return int(df["source_item_id"].duplicated(keep=False).sum())


def _exact_content_groups(df: pd.DataFrame) -> int:
    if df.empty or "exact_content_hash" not in df.columns:
        return 0
    non_null = df["exact_content_hash"].dropna()
    if non_null.empty:
        return 0
    counts = non_null.value_counts()
    return int((counts > 1).sum())
