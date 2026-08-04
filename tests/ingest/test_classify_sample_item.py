"""Tests for :func:`source_gate.classify_sample_item`.

These tests exercise the per-item classifier used by the source gate to
compute the combined-target coverage (monthly rental *and* allowed
property type *and* Montevideo). The classifier is a pure function so
it is tested independently of the gate flow.
"""

from __future__ import annotations

from alquileres_uy.ingest.source_gate import classify_sample_item

VERIFIED = {"apartment": "MLU_TEST_APARTMENT", "house": "MLU_TEST_HOUSE"}


def _item(**overrides):
    base = {
        "id": "MLUx",
        "category_id": "MLU_TEST_APARTMENT",
        "location": {"state": {"name": "Montevideo"}},
        "attributes": [
            {"id": "OPERATION", "value_name": "Alquiler", "value_id": "242075"},
            {"id": "PROPERTY_TYPE", "value_name": "Apartamento"},
        ],
    }
    base.update(overrides)
    return base


def test_monthly_rental_apartment_in_montevideo_is_valid():
    cls = classify_sample_item(_item(), VERIFIED)
    assert cls.monthly_rental is True
    assert cls.allowed_property_type is True
    assert cls.location_valid is True
    assert cls.valid_for_target is True
    assert cls.reasons == ()


def test_sale_is_rejected():
    cls = classify_sample_item(
        _item(
            attributes=[
                {"id": "OPERATION", "value_name": "Venta"},
                {"id": "PROPERTY_TYPE", "value_name": "Apartamento"},
            ]
        ),
        VERIFIED,
    )
    assert cls.monthly_rental is False
    assert cls.valid_for_target is False
    assert "sale" in cls.reasons


def test_temporary_rental_is_rejected():
    cls = classify_sample_item(
        _item(
            attributes=[
                {"id": "OPERATION", "value_name": "Alquiler temporal"},
                {"id": "PROPERTY_TYPE", "value_name": "Apartamento"},
            ]
        ),
        VERIFIED,
    )
    assert cls.monthly_rental is False
    assert cls.valid_for_target is False
    assert "temporary_rental" in cls.reasons


def test_missing_operation_is_flagged():
    cls = classify_sample_item(
        _item(attributes=[{"id": "PROPERTY_TYPE", "value_name": "Apartamento"}]),
        VERIFIED,
    )
    assert cls.monthly_rental is False
    assert "missing_operation" in cls.reasons


def test_unknown_operation_is_flagged():
    cls = classify_sample_item(
        _item(attributes=[{"id": "OPERATION", "value_name": "Permuta"}]),
        VERIFIED,
    )
    assert cls.monthly_rental is False
    assert "unknown_operation" in cls.reasons


def test_apartment_by_verified_category():
    cls = classify_sample_item(_item(category_id="MLU_TEST_APARTMENT"), VERIFIED)
    assert cls.property_type == "apartment"
    assert cls.allowed_property_type is True


def test_house_by_verified_category():
    cls = classify_sample_item(
        _item(
            category_id="MLU_TEST_HOUSE",
            attributes=[
                {"id": "OPERATION", "value_name": "Alquiler"},
                {"id": "PROPERTY_TYPE", "value_name": "Casa"},
            ],
        ),
        VERIFIED,
    )
    assert cls.property_type == "house"
    assert cls.allowed_property_type is True


def test_property_type_not_allowed_when_neither_source_matches():
    cls = classify_sample_item(
        _item(
            category_id="MLU_TEST_OTHER",
            attributes=[
                {"id": "OPERATION", "value_name": "Alquiler"},
                {"id": "PROPERTY_TYPE", "value_name": "Terreno"},
            ],
        ),
        VERIFIED,
    )
    assert cls.allowed_property_type is False
    assert cls.valid_for_target is False


def test_property_type_conflict_between_category_and_attribute():
    # Category says "house" but the structured attribute says "Apartamento".
    cls = classify_sample_item(
        _item(
            category_id="MLU_TEST_HOUSE",
            attributes=[
                {"id": "OPERATION", "value_name": "Alquiler"},
                {"id": "PROPERTY_TYPE", "value_name": "Apartamento"},
            ],
        ),
        VERIFIED,
    )
    assert "property_type_conflict" in cls.reasons
    assert cls.allowed_property_type is False
    assert cls.valid_for_target is False


def test_location_outside_montevideo_is_rejected():
    cls = classify_sample_item(_item(location={"state": {"name": "Canelones"}}), VERIFIED)
    assert cls.location_valid is False
    assert "outside_montevideo" in cls.reasons
    assert cls.valid_for_target is False


def test_missing_location_is_rejected():
    cls = classify_sample_item(_item(location={}), VERIFIED)
    assert cls.location_valid is False
    assert "missing_location" in cls.reasons


def test_title_alone_does_not_compensate_a_sale_operation():
    cls = classify_sample_item(
        _item(
            title="ALQUILER LUMINOSO",
            attributes=[
                {"id": "OPERATION", "value_name": "Venta"},
                {"id": "PROPERTY_TYPE", "value_name": "Apartamento"},
            ],
        ),
        VERIFIED,
    )
    assert cls.monthly_rental is False
    assert cls.valid_for_target is False


def test_target_valid_requires_all_three_conditions():
    # Rental + apartment but Canelones.
    cls = classify_sample_item(_item(location={"state": {"name": "Canelones"}}), VERIFIED)
    assert cls.monthly_rental is True
    assert cls.allowed_property_type is True
    assert cls.location_valid is False
    assert cls.valid_for_target is False


def test_operation_value_id_alone_can_confirm_monthly_rental():
    cls = classify_sample_item(
        _item(
            attributes=[
                {"id": "OPERATION", "value_id": "242075"},
                {"id": "PROPERTY_TYPE", "value_name": "Apartamento"},
            ]
        ),
        VERIFIED,
    )
    assert cls.monthly_rental is True
