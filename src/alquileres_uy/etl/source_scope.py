"""Reusable per-item scope classification for the ETL.

Complements the Fase 1 source_gate.classify_sample_item helper by
returning the two orthogonal decisions the ETL needs
(``operation``, ``property_type``) plus the specific rejection reason
code when the item is out of scope. Kept in its own module to avoid a
circular import between ``etl.extractors`` and ``etl.pipeline``.
"""

from __future__ import annotations

from typing import Any

from .normalization import normalize_key

_MONTHLY_RENTAL_VALUES: frozenset[str] = frozenset(
    {"alquiler", "alquiler mensual", "rent", "monthly rent"}
)
_MONTHLY_RENTAL_VALUE_IDS: frozenset[str] = frozenset({"242075"})
_TEMPORARY_TOKENS: tuple[str, ...] = (
    "temporal",
    "temporario",
    "temporada",
    "temporary",
    "vacation",
    "short term",
    "short-term",
)
_SALE_TOKENS: tuple[str, ...] = ("venta", "sale")

_APARTMENT_LABELS: frozenset[str] = frozenset(
    {"apartamento", "apartamentos", "apartment", "apartments"}
)
_HOUSE_LABELS: frozenset[str] = frozenset({"casa", "casas", "house", "houses"})


def _attribute_value_text(attribute: dict[str, Any] | None) -> str | None:
    if attribute is None:
        return None
    value = attribute.get("value_name")
    if isinstance(value, str) and value.strip():
        return value
    return None


def _attribute_value_id(attribute: dict[str, Any] | None) -> str | None:
    if attribute is None:
        return None
    value = attribute.get("value_id")
    if isinstance(value, str) and value.strip():
        return value
    return None


def classify_operation(
    attributes: dict[str, dict[str, Any]],
) -> tuple[str | None, str | None]:
    """Return ``(operation, reason_code)`` for the OPERATION attribute."""
    attribute = attributes.get("OPERATION")
    op_name = _attribute_value_text(attribute)
    op_id = _attribute_value_id(attribute)
    if op_name is None and op_id is None:
        return None, "missing_operation"

    normalized = normalize_key(op_name or "") or ""
    if any(token in normalized for token in _TEMPORARY_TOKENS):
        return None, "temporary_rental"
    if any(token in normalized for token in _SALE_TOKENS):
        return None, "sale"
    if normalized in _MONTHLY_RENTAL_VALUES or (
        op_id is not None and op_id in _MONTHLY_RENTAL_VALUE_IDS
    ):
        return "monthly_rent", None
    return None, "wrong_operation"


def classify_property_type(
    body: dict[str, Any],
    attributes: dict[str, dict[str, Any]],
    verified_category_ids: dict[str, str],
) -> tuple[str | None, str | None]:
    """Return ``(property_type, reason_code)`` combining category + attribute."""
    verified_by_id = {cid: pt for pt, cid in verified_category_ids.items()}
    raw_category = body.get("category_id") if isinstance(body.get("category_id"), str) else None
    pt_from_category = verified_by_id.get(raw_category) if raw_category else None

    attr = attributes.get("PROPERTY_TYPE")
    attr_value = _attribute_value_text(attr)
    attr_norm = normalize_key(attr_value or "") or ""
    pt_from_attribute: str | None = None
    if attr_norm in _APARTMENT_LABELS:
        pt_from_attribute = "apartment"
    elif attr_norm in _HOUSE_LABELS:
        pt_from_attribute = "house"

    if pt_from_category and pt_from_attribute and pt_from_category != pt_from_attribute:
        return None, "property_type_conflict"
    if pt_from_category:
        return pt_from_category, None
    if pt_from_attribute:
        return pt_from_attribute, None
    return None, "wrong_property_type"


def classify_location(body: dict[str, Any]) -> tuple[bool, str | None]:
    """Return ``(is_montevideo, reason_code)`` for the item's location."""
    location = body.get("location") or body.get("address") or {}
    state_name = ""
    if isinstance(location, dict):
        state_field = location.get("state") or location.get("state_name")
        if isinstance(state_field, dict):
            state_name = state_field.get("name") or ""
        elif isinstance(state_field, str):
            state_name = state_field
    key = normalize_key(state_name) or ""
    if not key:
        return False, "missing_location"
    if key == "montevideo":
        return True, None
    return False, "outside_montevideo"
