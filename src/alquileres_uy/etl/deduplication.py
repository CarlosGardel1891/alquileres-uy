"""Deduplication helpers: exact-content hashes and possible-duplicate keys."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

from .normalization import normalize_key

_TOTAL_AREA_BUCKET = Decimal("5")  # 5 m2 buckets
_PRICE_BUCKET = Decimal("50")  # USD 50 buckets


def content_hash(row: dict[str, Any]) -> str | None:
    """Return a stable SHA-256 fingerprint for exact-content duplicates.

    ``None`` when the row lacks enough structured fields to fingerprint
    reliably. Callers must not rely on hashes for near-duplicate detection —
    that is the job of :func:`possible_duplicate_key`.
    """
    parts = {
        "property_type": row.get("property_type"),
        "neighborhood_normalized": row.get("neighborhood_normalized"),
        "bedrooms": _as_number(row.get("bedrooms")),
        "total_area_m2": _as_number(row.get("total_area_m2")),
        "price_usd": _as_number(row.get("price_usd")),
        "title_key": normalize_key(row.get("title")) if row.get("title") else None,
    }
    if not parts["property_type"] or parts["price_usd"] is None:
        return None
    payload = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def possible_duplicate_key(row: dict[str, Any]) -> str | None:
    """Return a conservative bucketed key for cross-agency duplicate candidates."""
    property_type = row.get("property_type")
    neighborhood = row.get("neighborhood_normalized")
    bedrooms = _as_number(row.get("bedrooms"))
    total_area = _as_number(row.get("total_area_m2"))
    price = _as_number(row.get("price_usd"))
    if not all(
        [
            property_type,
            neighborhood,
            bedrooms is not None,
            total_area is not None,
            price is not None,
        ]
    ):
        return None
    total_area_bucket = _bucket(total_area, _TOTAL_AREA_BUCKET)
    price_bucket = _bucket(price, _PRICE_BUCKET)
    return "|".join(
        [
            str(property_type),
            str(neighborhood).lower(),
            str(int(bedrooms)),
            str(total_area_bucket),
            str(price_bucket),
        ]
    )


def _bucket(value: Decimal, step: Decimal) -> int:
    """Return the integer index of the bucket ``value`` falls into."""
    if step == 0:
        return int(value)
    quotient = value / step
    return int(quotient.to_integral_value(rounding="ROUND_FLOOR"))


def _as_number(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None
