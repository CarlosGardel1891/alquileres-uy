"""Deterministic query plan for MercadoLibre searches.

The plan expresses the segmentation of the search space into slices that
individually fit under MercadoLibre's ``offset + limit <= 1000`` cap. The
initial plan targets apartments and houses for monthly rent in
Montevideo. Segments whose reported total exceeds
:data:`SAFE_SEGMENT_LIMIT` are split by price bands, and if needed by
bedroom count.

The plan itself is deterministic and network-free; probing reported
totals is the ingestion service's responsibility.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import replace

from .models import QuerySegment

# Category identifiers observed for MercadoLibre Uruguay real estate.
# These are seeds; the source gate re-verifies them against the live
# category tree and records the observed values in the source contract.
CATEGORY_APARTMENT = "MLU1466"
CATEGORY_HOUSE = "MLU1472"

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
    site_id: str = "MLU",
    state: str = DEFAULT_STATE_LABEL,
) -> list[QuerySegment]:
    """Return the seed list of query segments for a new run.

    The seed distinguishes property type and rent operation. Splitting by
    price or bedrooms is done later, once the service knows the reported
    total for each segment.
    """
    segments: list[QuerySegment] = []
    for property_type, category in (
        ("apartment", CATEGORY_APARTMENT),
        ("house", CATEGORY_HOUSE),
    ):
        parameters = {
            "site_id": site_id,
            "category": category,
            "state": state,
            "operation": "rent",
        }
        segments.append(
            QuerySegment(
                segment_key=f"{property_type}|{state}|rent",
                parameters=parameters,
                category_id=category,
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
    """Split ``segment`` into contiguous, non-overlapping price bands.

    Bands are ``[low, high)`` and never leave gaps. Assumes MercadoLibre's
    ``price=low-high`` filter syntax; the last band uses only the lower
    bound to catch any premium listings above the last boundary.
    """
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
    # Trailing open-ended band to avoid dropping listings above the top boundary.
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


def classify_candidate(item: dict[str, object]) -> tuple[str, str | None]:
    """Return a preliminary ``(candidate_status, reason)`` for a raw item.

    Only structured fields are inspected; textual descriptions are ignored
    by design. Deep classification is deferred to the ETL phase.
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

    if category_id not in {CATEGORY_APARTMENT, CATEGORY_HOUSE} and property_type is None:
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
