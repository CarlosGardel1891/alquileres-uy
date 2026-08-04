"""Field extraction from raw MercadoLibre item bodies."""

from __future__ import annotations

import re
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any

from .normalization import normalize_key, normalize_text

_NUMBER_RE = re.compile(r"^-?\d+(?:[.,]\d+)?$")
_UNIT_TOKENS = frozenset({"m2", "m²", "sqm"})
_EN_DASH = chr(0x2013)  # en dash
_RANGE_MARKERS = ("-", _EN_DASH, " a ", " al ", " to ")

ATTRIBUTE_MAP: dict[str, str] = {
    "BEDROOMS": "bedrooms",
    "ROOMS": "rooms_total",
    "FULL_BATHROOMS": "bathrooms",
    "BATHROOMS": "bathrooms",
    "TOTAL_AREA": "total_area_m2",
    "COVERED_AREA": "covered_area_m2",
    "FLOOR": "floor",
    "PARKING_LOTS": "parking_spaces",
    "COMMON_EXPENSES": "common_expenses_original",
}

BOOLEAN_ATTRIBUTES: dict[str, str] = {
    "HAS_GARAGE": "garage",
    "HAS_TERRACE": "terrace",
    "FURNISHED": "furnished",
    "IS_FURNISHED": "furnished",
    "IS_NEW_BUILD": "new_build",
    "IS_NEW": "new_build",
}


def index_attributes(item: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return an ``id → attribute`` dict indexed by ``attributes[].id``."""
    result: dict[str, dict[str, Any]] = {}
    attributes = item.get("attributes")
    if not isinstance(attributes, list):
        return result
    for entry in attributes:
        if not isinstance(entry, dict):
            continue
        attribute_id = entry.get("id")
        if isinstance(attribute_id, str) and attribute_id and attribute_id not in result:
            result[attribute_id] = entry
    return result


def attribute_value(attribute: dict[str, Any] | None) -> Any:
    """Return the best available value for an attribute, or ``None``."""
    if attribute is None:
        return None
    for key in ("value_struct", "value_name", "value_id"):
        value = attribute.get(key)
        if value not in (None, "", []):
            return value
    return None


def parse_number(raw: Any) -> tuple[Decimal | None, str | None]:
    """Return ``(decimal, error_code_or_None)`` for a numeric attribute value.

    Handles ints, floats, decimals, strings like ``"65"``, ``"65.5"``,
    ``"65,5"``, ``"65 m²"``, ``"65 m2"``, and MercadoLibre-style
    ``value_struct = {"number": ..., "unit": "..."}`` payloads. Rejects
    ranges (``"65-70"``) and free-form strings like ``"aprox 65"``.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, None
    if isinstance(raw, bool):  # bool is int subclass; ignore
        return None, "invalid_number"
    if isinstance(raw, int | float | Decimal):
        try:
            value = Decimal(str(raw))
        except InvalidOperation:
            return None, "invalid_number"
        return value, None
    if isinstance(raw, dict):
        number = raw.get("number")
        if number is None:
            return None, "invalid_number"
        try:
            value = Decimal(str(number))
        except (InvalidOperation, TypeError, ValueError):
            return None, "invalid_number"
        return value, None
    if not isinstance(raw, str):
        return None, "invalid_number"

    text = raw.strip().lower()
    for marker in _RANGE_MARKERS:
        if marker in text and not text.startswith("-"):
            return None, "invalid_range"
    for token in _UNIT_TOKENS:
        if text.endswith(token):
            text = text[: -len(token)].strip()
            break
    text = text.replace(",", ".")
    if not _NUMBER_RE.match(text):
        return None, "invalid_number"
    try:
        return Decimal(text), None
    except InvalidOperation:
        return None, "invalid_number"


def parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    key = normalize_key(str(value)) if value is not None else None
    if key in {"si", "sí", "yes", "true", "1"}:
        return True
    if key in {"no", "false", "0"}:
        return False
    return None


def extract_scope(
    body: dict[str, Any],
    verified_category_ids: dict[str, str],
) -> tuple[str | None, str | None, list[str]]:
    """Return ``(operation, property_type, reasons)`` for a single item.

    ``operation`` is either ``"monthly_rent"`` or ``None``. ``property_type``
    is one of ``"apartment"``, ``"house"`` or ``None``. ``reasons`` is a
    list of rejection reason codes (empty when the item is in scope).
    """
    from .source_scope import classify_operation, classify_property_type

    reasons: list[str] = []
    attributes = index_attributes(body)
    operation, op_reason = classify_operation(attributes)
    if op_reason:
        reasons.append(op_reason)
    property_type, pt_reason = classify_property_type(body, attributes, verified_category_ids)
    if pt_reason:
        reasons.append(pt_reason)
    return operation, property_type, reasons


def extract_text(body: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            return normalize_text(value)
    return None


def extract_first_matching_attribute(
    attributes: dict[str, dict[str, Any]],
    ids: tuple[str, ...],
    parser: Callable[[Any], tuple[Any | None, str | None]] = parse_number,
) -> tuple[Any | None, str | None]:
    for attribute_id in ids:
        attribute = attributes.get(attribute_id)
        if attribute is None:
            continue
        value, error = parser(attribute_value(attribute))
        if value is not None or error is not None:
            return value, error
    return None, None


def known_attribute_ids() -> frozenset[str]:
    """Return the set of attribute IDs the ETL knows how to map."""
    core = set(ATTRIBUTE_MAP) | set(BOOLEAN_ATTRIBUTES)
    core.update({"OPERATION", "PROPERTY_TYPE", "SURFACE_TOTAL"})
    return frozenset(core)
