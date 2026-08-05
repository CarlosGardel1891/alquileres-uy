from decimal import Decimal

from alquileres_uy.etl.extractors import (
    attribute_value,
    index_attributes,
    parse_bool,
    parse_number,
)


def test_index_attributes_prefers_first_occurrence():
    idx = index_attributes(
        {
            "attributes": [
                {"id": "BEDROOMS", "value_name": "2"},
                {"id": "BEDROOMS", "value_name": "3"},
            ]
        }
    )
    assert idx["BEDROOMS"]["value_name"] == "2"


def test_index_attributes_handles_missing():
    assert index_attributes({}) == {}


def test_attribute_value_prioritizes_struct():
    attr = {"value_struct": {"number": 65, "unit": "m²"}, "value_name": "otro"}
    assert attribute_value(attr) == {"number": 65, "unit": "m²"}


def test_attribute_value_fallback_to_value_name():
    attr = {"value_name": "Alquiler"}
    assert attribute_value(attr) == "Alquiler"


def test_attribute_value_fallback_to_value_id():
    attr = {"value_id": "242075"}
    assert attribute_value(attr) == "242075"


def test_parse_number_int():
    value, err = parse_number(65)
    assert err is None
    assert value == Decimal("65")


def test_parse_number_decimal():
    value, err = parse_number("65.5")
    assert err is None
    assert value == Decimal("65.5")


def test_parse_number_comma_decimal():
    value, err = parse_number("65,5")
    assert err is None
    assert value == Decimal("65.5")


def test_parse_area_with_unit_m2():
    from alquileres_uy.etl.extractors import parse_area

    value, err = parse_area("65 m2")
    assert err is None
    assert value == Decimal("65")


def test_parse_area_with_unit_m_squared():
    from alquileres_uy.etl.extractors import parse_area

    value, err = parse_area("65 m²")
    assert err is None
    assert value == Decimal("65")


def test_parse_number_struct_rejects_unit_for_plain_parser():
    # parse_number is the strict plain-number alias; any non-empty
    # unit is unsupported_count_unit.
    value, err = parse_number({"number": 65, "unit": "m²"})
    assert value is None
    assert err == "unsupported_count_unit"


def test_parse_number_struct_accepts_no_unit():
    value, err = parse_number({"number": 65})
    assert err is None
    assert value == Decimal("65")


def test_parse_number_rejects_range():
    value, err = parse_number("65-70")
    assert value is None
    assert err == "invalid_range"


def test_parse_number_rejects_words():
    value, err = parse_number("sesenta y cinco")
    assert value is None
    assert err == "invalid_number"


def test_parse_number_ignores_empty_string():
    value, err = parse_number("")
    assert value is None
    assert err is None


def test_parse_bool_recognizes_common_forms():
    assert parse_bool("Sí") is True
    assert parse_bool("No") is False
    assert parse_bool(True) is True
    assert parse_bool("maybe") is None
