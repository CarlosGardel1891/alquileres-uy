"""Unit tests for :func:`parse_area` and its unit gating."""

from __future__ import annotations

from decimal import Decimal

from alquileres_uy.etl.extractors import parse_area, parse_plain_number


def test_parse_area_accepts_m2_string():
    value, err = parse_area("65 m2")
    assert err is None
    assert value == Decimal("65")


def test_parse_area_accepts_m_squared_string():
    value, err = parse_area("65 m²")
    assert err is None


def test_parse_area_accepts_sqm_string():
    value, err = parse_area("65 sqm")
    assert err is None


def test_parse_area_accepts_value_struct_m_squared():
    value, err = parse_area({"number": 65, "unit": "m²"})
    assert err is None
    assert value == Decimal("65")


def test_parse_area_accepts_value_struct_m2():
    value, err = parse_area({"number": 65, "unit": "m2"})
    assert err is None
    assert value == Decimal("65")


def test_parse_area_rejects_value_struct_ft_squared():
    value, err = parse_area({"number": 700, "unit": "ft²"})
    assert value is None
    assert err == "unsupported_area_unit"


def test_parse_area_rejects_sqft_string():
    value, err = parse_area("700 sqft")
    assert value is None
    assert err == "unsupported_area_unit"


def test_parse_area_rejects_unknown_unit_struct():
    value, err = parse_area({"number": 3, "unit": "hectárea"})
    assert value is None
    assert err == "unsupported_area_unit"


def test_parse_area_rejects_range():
    value, err = parse_area("65-70 m2")
    assert value is None
    assert err == "invalid_range"


def test_parse_plain_number_still_accepts_bedrooms_as_integer():
    value, err = parse_plain_number(3)
    assert err is None
    assert value == Decimal("3")


def test_parse_plain_number_still_accepts_struct_without_unit():
    value, err = parse_plain_number({"number": 3, "unit": "habitaciones"})
    # plain_number ignores unit for counts
    assert err is None
    assert value == Decimal("3")


def test_parse_plain_number_rejects_range():
    value, err = parse_plain_number("2-3")
    assert value is None
    assert err == "invalid_range"
