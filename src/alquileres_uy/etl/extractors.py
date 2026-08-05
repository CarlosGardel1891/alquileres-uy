"""Field extraction from raw MercadoLibre item bodies."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any

from .normalization import normalize_key, normalize_text

_NUMBER_RE = re.compile(r"^-?\d+(?:[.,]\d+)?$")
_AREA_UNIT_ALIASES: frozenset[str] = frozenset(
    {"m2", "m²", "sqm", "metro cuadrado", "metros cuadrados"}
)
_EN_DASH = chr(0x2013)  # en dash
_RANGE_MARKERS = ("-", _EN_DASH, " a ", " al ", " to ")
AREA_ATTRIBUTE_IDS: frozenset[str] = frozenset({"TOTAL_AREA", "COVERED_AREA", "SURFACE_TOTAL"})

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

# Per-attribute alias sets. A value_struct or string suffix whose
# normalized unit is not in the attribute's allow-list is rejected as
# ``unsupported_count_unit`` instead of being silently interpreted.
COUNT_ATTRIBUTE_UNIT_ALIASES: dict[str, frozenset[str]] = {
    "BEDROOMS": frozenset({"dormitorio", "dormitorios", "bedroom", "bedrooms"}),
    "ROOMS": frozenset({"ambiente", "ambientes", "room", "rooms"}),
    "FULL_BATHROOMS": frozenset({"bano", "banos", "bathroom", "bathrooms"}),
    "BATHROOMS": frozenset({"bano", "banos", "bathroom", "bathrooms"}),
    "FLOOR": frozenset({"piso", "pisos", "floor"}),
    "PARKING_LOTS": frozenset(
        {"cochera", "cocheras", "garaje", "garajes", "parking space", "parking spaces"}
    ),
}


def normalize_unit(value: str | None) -> str:
    """Return the canonical form of a unit string for comparison."""
    if not isinstance(value, str):
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch) or ch == "²")
    # Preserve the ² character (needed for m²) but collapse combining marks.
    text = re.sub(r"\s+", " ", stripped.lower().strip())
    return text


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


def parse_plain_number(raw: Any) -> tuple[Decimal | None, str | None]:
    """Parse a strict numeric value with no unit — for internal helpers.

    Accepts ints/floats/Decimals, numeric strings, and ``value_struct``
    payloads whose ``unit`` is empty. Anything with a non-empty unit is
    rejected as ``unsupported_count_unit``. Ranges and free-form text
    stay ``invalid_number``/``invalid_range``.
    """
    return parse_count(raw, allowed_units=frozenset())


def parse_count(
    raw: Any,
    *,
    allowed_units: frozenset[str] = frozenset(),
) -> tuple[Decimal | None, str | None]:
    """Parse a count-like attribute.

    ``allowed_units`` is the (normalized) alias set that this attribute
    accepts as a unit. A ``value_struct.unit`` outside that set — or
    any non-empty unit when ``allowed_units`` is empty — returns
    ``(None, "unsupported_count_unit")``. Strings with a non-numeric
    suffix keep the historical behavior (``invalid_number``).
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, None
    if isinstance(raw, bool):
        return None, "invalid_number"
    if isinstance(raw, int | float | Decimal):
        try:
            return Decimal(str(raw)), None
        except InvalidOperation:
            return None, "invalid_number"
    if isinstance(raw, dict):
        number = raw.get("number")
        if number is None:
            return None, "invalid_number"
        unit = raw.get("unit")
        normalized = normalize_unit(unit) if unit is not None else ""
        if normalized and normalized not in allowed_units:
            return None, "unsupported_count_unit"
        try:
            return Decimal(str(number)), None
        except (InvalidOperation, TypeError, ValueError):
            return None, "invalid_number"
    if not isinstance(raw, str):
        return None, "invalid_number"
    text = raw.strip().lower()
    for marker in _RANGE_MARKERS:
        if marker in text and not text.startswith("-"):
            return None, "invalid_range"
    text = text.replace(",", ".")
    if not _NUMBER_RE.match(text):
        return None, "invalid_number"
    try:
        return Decimal(text), None
    except InvalidOperation:
        return None, "invalid_number"


def parse_area(raw: Any) -> tuple[Decimal | None, str | None]:
    """Parse a surface attribute.

    Only ``m²``/``m2``/``sqm``/``metros cuadrados`` are accepted as
    unit suffixes. Any other suffix — recognized as such by the
    presence of a non-numeric tail on the string — returns
    ``(None, "unsupported_area_unit")``. Bare numbers without a
    suffix are still accepted for compatibility with structured
    fields whose semantics is already known to be square meters.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, None
    if isinstance(raw, bool):
        return None, "invalid_number"
    if isinstance(raw, int | float | Decimal):
        try:
            return Decimal(str(raw)), None
        except InvalidOperation:
            return None, "invalid_number"
    if isinstance(raw, dict):
        number = raw.get("number")
        unit = raw.get("unit")
        if number is None:
            return None, "invalid_number"
        if unit is not None and not _is_area_unit(unit):
            return None, "unsupported_area_unit"
        try:
            return Decimal(str(number)), None
        except (InvalidOperation, TypeError, ValueError):
            return None, "invalid_number"
    if not isinstance(raw, str):
        return None, "invalid_number"
    text = raw.strip().lower()
    for marker in _RANGE_MARKERS:
        if marker in text and not text.startswith("-"):
            return None, "invalid_range"

    # Strip a trailing unit suffix if present; anything left that is
    # not numeric must be an unsupported unit.
    match = re.match(r"^(-?\d+(?:[.,]\d+)?)(?:\s*(.*))?$", text)
    if not match:
        return None, "invalid_number"
    number_part = match.group(1)
    suffix = (match.group(2) or "").strip()
    if suffix:
        canonical_suffix = normalize_unit(suffix)
        if canonical_suffix not in _AREA_UNIT_ALIASES:
            return None, "unsupported_area_unit"
    number_part = number_part.replace(",", ".")
    if not _NUMBER_RE.match(number_part):
        return None, "invalid_number"
    try:
        return Decimal(number_part), None
    except InvalidOperation:
        return None, "invalid_number"


def _is_area_unit(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return normalize_unit(value) in _AREA_UNIT_ALIASES


# Backward-compatible alias so callers that only need a plain number
# can keep using the historical name. The alias intentionally maps to
# the strict variant — parsers used for attribute values must go
# through :func:`parse_count` with the right ``allowed_units``.
parse_number = parse_plain_number


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
    """Return ``(operation, property_type, reasons)`` for a single item."""
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
    parser: Callable[[Any], tuple[Any | None, str | None]] = parse_plain_number,
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
