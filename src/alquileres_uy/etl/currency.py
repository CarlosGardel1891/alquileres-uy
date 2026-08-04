"""Currency conversion with an explicit, versioned exchange rate."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .models import ALLOWED_CURRENCIES


class InvalidExchangeRate(ValueError):
    """Raised when an exchange rate configuration cannot be trusted."""


@dataclass(frozen=True)
class ExchangeRate:
    """Immutable exchange rate loaded from a JSON configuration file."""

    base_currency: str
    quote_currency: str
    uyu_per_usd: Decimal
    effective_date: date
    source: str
    data_mode: str
    retrieved_at: str


def load_exchange_rate(path: Path) -> ExchangeRate:
    """Read and validate an exchange rate JSON file."""
    path = Path(path)
    if not path.is_file():
        raise InvalidExchangeRate(f"exchange rate file not found: {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InvalidExchangeRate(f"exchange rate file is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise InvalidExchangeRate("exchange rate root must be a JSON object")

    base_currency = raw.get("base_currency")
    quote_currency = raw.get("quote_currency")
    if base_currency != "USD" or quote_currency != "UYU":
        raise InvalidExchangeRate(
            f"exchange rate must convert USD→UYU, got {base_currency}→{quote_currency}"
        )

    rate_value = raw.get("uyu_per_usd")
    try:
        rate = Decimal(str(rate_value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidExchangeRate(f"uyu_per_usd is not numeric: {rate_value!r}") from exc
    if rate <= 0:
        raise InvalidExchangeRate(f"uyu_per_usd must be positive, got {rate}")

    effective_raw = raw.get("effective_date")
    if not isinstance(effective_raw, str):
        raise InvalidExchangeRate("effective_date must be a string in ISO format")
    try:
        effective = date.fromisoformat(effective_raw)
    except ValueError as exc:
        raise InvalidExchangeRate(f"effective_date is invalid: {effective_raw!r}") from exc

    source = raw.get("source")
    if not isinstance(source, str) or not source.strip():
        raise InvalidExchangeRate("exchange rate 'source' field is required")

    data_mode = raw.get("data_mode")
    if data_mode not in {"fixture", "real"}:
        raise InvalidExchangeRate(
            f"exchange rate data_mode must be 'fixture' or 'real', got {data_mode!r}"
        )

    retrieved_at = raw.get("retrieved_at")
    if not isinstance(retrieved_at, str):
        raise InvalidExchangeRate("retrieved_at is required and must be a string")

    return ExchangeRate(
        base_currency=base_currency,
        quote_currency=quote_currency,
        uyu_per_usd=rate,
        effective_date=effective,
        source=source.strip(),
        data_mode=data_mode,
        retrieved_at=retrieved_at,
    )


def convert_price_to_usd(
    amount: float | int | Decimal | None,
    currency: str | None,
    rate: ExchangeRate,
) -> tuple[Decimal | None, str | None]:
    """Return ``(price_usd, error_code)`` for an original price + currency."""
    if amount is None or currency is None:
        return None, "missing_price"
    try:
        original = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        return None, "invalid_price"
    if original <= 0:
        return None, "invalid_price"
    normalized_currency = currency.strip().upper()
    if normalized_currency not in ALLOWED_CURRENCIES:
        return None, "unsupported_currency"
    if normalized_currency == "USD":
        return original, None
    return original / rate.uyu_per_usd, None


def convert_common_expenses(
    amount: float | int | Decimal | None,
    currency: str | None,
    rate: ExchangeRate,
    listing_currency: str | None,
) -> dict[str, Any]:
    """Return the normalized common expenses columns for a single listing.

    Missing → ``reported=False`` and every derived field null.
    Zero → ``reported=True`` with ``0`` values (never confused with missing).
    Missing currency → inferred from ``listing_currency``, flagged with
    ``currency_inferred=True``. Unsupported currency → the listing itself
    survives, but common_expenses_usd stays null and an issue is
    surfaced by the caller.
    """
    if amount is None:
        return {
            "common_expenses_original": None,
            "common_expenses_currency": None,
            "common_expenses_usd": None,
            "common_expenses_reported": False,
            "common_expenses_currency_inferred": False,
        }
    try:
        original = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        return {
            "common_expenses_original": None,
            "common_expenses_currency": None,
            "common_expenses_usd": None,
            "common_expenses_reported": True,
            "common_expenses_currency_inferred": False,
        }

    if original == 0:
        return {
            "common_expenses_original": Decimal(0),
            "common_expenses_currency": (currency or listing_currency or "").strip().upper()
            or None,
            "common_expenses_usd": Decimal(0),
            "common_expenses_reported": True,
            "common_expenses_currency_inferred": currency is None,
        }

    inferred = False
    effective_currency = currency
    if effective_currency is None or not str(effective_currency).strip():
        effective_currency = listing_currency
        inferred = True
    if effective_currency is None:
        return {
            "common_expenses_original": original,
            "common_expenses_currency": None,
            "common_expenses_usd": None,
            "common_expenses_reported": True,
            "common_expenses_currency_inferred": inferred,
        }

    normalized = effective_currency.strip().upper()
    if normalized not in ALLOWED_CURRENCIES:
        return {
            "common_expenses_original": original,
            "common_expenses_currency": normalized,
            "common_expenses_usd": None,
            "common_expenses_reported": True,
            "common_expenses_currency_inferred": inferred,
        }
    usd = original if normalized == "USD" else original / rate.uyu_per_usd
    return {
        "common_expenses_original": original,
        "common_expenses_currency": normalized,
        "common_expenses_usd": usd,
        "common_expenses_reported": True,
        "common_expenses_currency_inferred": inferred,
    }
