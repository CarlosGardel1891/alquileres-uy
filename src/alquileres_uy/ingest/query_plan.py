"""Deterministic query plan for MercadoLibre searches.

The plan expresses the segmentation of the search space into slices that
individually fit under MercadoLibre's ``offset + limit <= 1000`` cap. It
depends entirely on the :class:`ApprovedSourceContract` produced by the
source gate, so the pipeline never uses category IDs that have not been
verified against a real API response.

The plan itself is deterministic and network-free; probing reported
totals is the ingestion service's responsibility.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import replace

from .models import ApprovedSourceContract, QuerySegment

DEFAULT_STATE_LABEL = "Montevideo"

SAFE_SEGMENT_LIMIT = 900  # keep a margin below MELI's 1000-result cap
DEFAULT_PRICE_BOUNDARIES: tuple[int, ...] = (
    0,
    500,
    800,
    1200,
    1800,
    2500,
    4000,
    100_000,
)
DEFAULT_BEDROOM_BUCKETS: tuple[int | None, ...] = (1, 2, 3, 4, None)


def build_initial_plan(
    contract: ApprovedSourceContract,
    state: str = DEFAULT_STATE_LABEL,
) -> list[QuerySegment]:
    """Return the seed list of query segments for a new run.

    The seed is built from ``contract.category_ids``. If the mapping is
    empty the pipeline cannot proceed, so a :class:`ValueError` is
    raised — callers must never construct a plan against unverified
    categories.
    """
    if not contract.category_ids:
        raise ValueError("cannot build query plan: approved contract has no verified categories")
    segments: list[QuerySegment] = []
    for property_type, category_id in sorted(contract.category_ids.items()):
        if not category_id:
            raise ValueError(f"cannot build query plan: category id for {property_type} is empty")
        parameters = {
            "site_id": contract.site_id,
            "category": category_id,
            "state": state,
            "operation": "rent",
        }
        segments.append(
            QuerySegment(
                segment_key=f"{property_type}|{state}|rent",
                parameters=parameters,
                category_id=category_id,
                property_type=property_type,
                operation="rent",
                location=state,
            )
        )
    return segments


def split_by_price(
    segment: QuerySegment,
    boundaries: Sequence[int] = DEFAULT_PRICE_BOUNDARIES,
) -> list[QuerySegment]:
    """Split ``segment`` into contiguous, non-overlapping price bands."""
    ordered = sorted(set(boundaries))
    if len(ordered) < 2:
        raise ValueError("need at least two boundaries to build price bands")

    slices: list[QuerySegment] = []
    for index in range(len(ordered) - 1):
        low = ordered[index]
        high = ordered[index + 1]
        params = dict(segment.parameters)
        params["price"] = f"{low}-{high}"
        slices.append(
            replace(
                segment,
                segment_key=f"{segment.segment_key}|price:{low}-{high}",
                parameters=params,
                price_min=float(low),
                price_max=float(high),
            )
        )
    tail_low = ordered[-1]
    tail_params = dict(segment.parameters)
    tail_params["price"] = f"{tail_low}-*"
    slices.append(
        replace(
            segment,
            segment_key=f"{segment.segment_key}|price:{tail_low}-*",
            parameters=tail_params,
            price_min=float(tail_low),
            price_max=None,
        )
    )
    return slices


def split_by_bedrooms(
    segment: QuerySegment,
    buckets: Sequence[int | None] = DEFAULT_BEDROOM_BUCKETS,
) -> list[QuerySegment]:
    """Split ``segment`` by bedroom bucket. ``None`` means "5 or more"."""
    slices: list[QuerySegment] = []
    for bucket in buckets:
        params = dict(segment.parameters)
        if bucket is None:
            params["BEDROOMS"] = "5-*"
            key_suffix = "bedrooms:5plus"
            bedrooms_value: int | None = None
        else:
            params["BEDROOMS"] = str(bucket)
            key_suffix = f"bedrooms:{bucket}"
            bedrooms_value = bucket
        slices.append(
            replace(
                segment,
                segment_key=f"{segment.segment_key}|{key_suffix}",
                parameters=params,
                bedrooms=bedrooms_value,
            )
        )
    return slices


def plan_hash(segments: Iterable[QuerySegment]) -> str:
    """Return a deterministic SHA-256 of the plan segments."""
    payload = json.dumps(
        [s.as_dict() for s in segments],
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def page_fingerprint(item_ids: Iterable[str]) -> str:
    """Return the deterministic SHA-256 fingerprint of a page's IDs.

    Two pages that surface the same set of IDs (regardless of intra-page
    ordering) produce the same fingerprint. Used to detect a search
    endpoint that keeps returning the same page for different offsets.
    """
    ordered = sorted(item_ids)
    payload = json.dumps(ordered, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def classify_candidate(
    item: dict[str, object],
    contract: ApprovedSourceContract,
) -> tuple[str, str | None]:
    """Return a preliminary ``(candidate_status, reason)`` for a raw item.

    The property-type check consults ``contract.category_ids`` — only
    values that the source gate actually verified against MercadoLibre
    are treated as valid. If the item lacks both a matching category and
    a structured ``PROPERTY_TYPE`` attribute, it is marked ``unknown``.
    """
    category_id = item.get("category_id")
    location = item.get("address") or item.get("location") or {}
    attributes = item.get("attributes") or []

    operation = _attribute_value(attributes, "OPERATION")
    property_type = _attribute_value(attributes, "PROPERTY_TYPE")
    state = None
    if isinstance(location, dict):
        state_field = location.get("state")
        if isinstance(state_field, dict):
            state = state_field.get("name")
        elif isinstance(state_field, str):
            state = state_field

    if operation is None:
        return ("unknown", "missing_operation")
    normalized_operation = operation.lower()
    if "venta" in normalized_operation or "sale" in normalized_operation:
        return ("excluded", "sale")
    if "temporal" in normalized_operation or "temporary" in normalized_operation:
        return ("excluded", "temporary_rental")

    if state is None:
        return ("unknown", "missing_location")
    if "montevideo" not in state.lower():
        return ("excluded", "outside_montevideo")

    approved_category_ids = set(contract.category_ids.values())
    matches_category = category_id in approved_category_ids
    has_property_type_attribute = bool(property_type)
    if not matches_category and not has_property_type_attribute:
        return ("unknown", "wrong_property_type")

    return ("candidate", None)


def _attribute_value(attributes: object, attribute_id: str) -> str | None:
    if not isinstance(attributes, list):
        return None
    for attribute in attributes:
        if not isinstance(attribute, dict):
            continue
        if attribute.get("id") != attribute_id:
            continue
        for key in ("value_name", "value_id"):
            value = attribute.get(key)
            if isinstance(value, str) and value:
                return value
    return None
