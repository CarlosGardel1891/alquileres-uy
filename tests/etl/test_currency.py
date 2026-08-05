from decimal import Decimal

import pytest

from alquileres_uy.etl.currency import (
    InvalidExchangeRate,
    convert_common_expenses,
    convert_price_to_usd,
    load_exchange_rate,
)


def test_load_exchange_rate_example(exchange_rate_path):
    rate = load_exchange_rate(exchange_rate_path)
    assert rate.uyu_per_usd == Decimal("40.0")
    assert rate.base_currency == "USD"


def test_load_rate_rejects_negative(tmp_path):
    p = tmp_path / "r.json"
    p.write_text(
        '{"base_currency":"USD","quote_currency":"UYU","uyu_per_usd":-1,'
        '"effective_date":"2026-01-01","source":"x","data_mode":"fixture",'
        '"retrieved_at":"2026-01-01T00:00:00Z"}'
    )
    with pytest.raises(InvalidExchangeRate):
        load_exchange_rate(p)


def test_load_rate_rejects_zero(tmp_path):
    p = tmp_path / "r.json"
    p.write_text(
        '{"base_currency":"USD","quote_currency":"UYU","uyu_per_usd":0,'
        '"effective_date":"2026-01-01","source":"x","data_mode":"fixture",'
        '"retrieved_at":"2026-01-01T00:00:00Z"}'
    )
    with pytest.raises(InvalidExchangeRate):
        load_exchange_rate(p)


def test_convert_usd_is_identity(exchange_rate):
    price, err = convert_price_to_usd(1000, "USD", exchange_rate)
    assert err is None
    assert price == Decimal("1000")


def test_convert_uyu_divides_by_rate(exchange_rate):
    price, err = convert_price_to_usd(40000, "UYU", exchange_rate)
    assert err is None
    assert price == Decimal("1000")


def test_convert_unsupported_currency(exchange_rate):
    price, err = convert_price_to_usd(1000, "ARS", exchange_rate)
    assert price is None
    assert err == "unsupported_currency"


def test_convert_missing_price(exchange_rate):
    price, err = convert_price_to_usd(None, "USD", exchange_rate)
    assert price is None
    assert err == "missing_price"


def test_common_expenses_missing_stays_null(exchange_rate):
    result = convert_common_expenses(None, None, exchange_rate, listing_currency="USD")
    assert result["common_expenses_reported"] is False
    assert result["common_expenses_usd"] is None


def test_common_expenses_zero_is_reported(exchange_rate):
    result = convert_common_expenses(0, "USD", exchange_rate, listing_currency="USD")
    assert result["common_expenses_reported"] is True
    assert result["common_expenses_usd"] == Decimal(0)


def test_common_expenses_currency_inferred_from_listing(exchange_rate):
    result = convert_common_expenses(5000, None, exchange_rate, listing_currency="UYU")
    assert result["common_expenses_currency_inferred"] is True
    assert result["common_expenses_currency"] == "UYU"
    assert result["common_expenses_usd"] == Decimal("5000") / Decimal("40.0")


def test_common_expenses_unsupported_currency_keeps_listing(exchange_rate):
    result = convert_common_expenses(5000, "ARS", exchange_rate, listing_currency="USD")
    assert result["common_expenses_usd"] is None
    assert result["common_expenses_currency"] == "ARS"
    assert result["common_expenses_reported"] is True
