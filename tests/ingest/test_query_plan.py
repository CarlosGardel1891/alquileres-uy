"""Tests for the deterministic query plan and preliminary classification."""

from __future__ import annotations

import itertools

from alquileres_uy.ingest.query_plan import (
    CATEGORY_APARTMENT,
    build_initial_plan,
    classify_candidate,
    plan_hash,
    split_by_bedrooms,
    split_by_price,
)


def test_build_initial_plan_has_apartment_and_house_segments():
    segments = build_initial_plan()
    property_types = sorted(segment.property_type for segment in segments)
    assert property_types == ["apartment", "house"]
    for segment in segments:
        assert segment.parameters["state"] == "Montevideo"
        assert segment.parameters["operation"] == "rent"


def test_split_by_price_produces_contiguous_bands_without_gaps():
    seed = build_initial_plan()[0]
    slices = split_by_price(seed)

    assert len(slices) >= 2
    boundaries = [s.price_min for s in slices]
    assert boundaries == sorted(boundaries)
    for previous, current in itertools.pairwise(slices):
        assert previous.price_max is None or previous.price_max == current.price_min


def test_split_by_bedrooms_covers_expected_buckets():
    seed = build_initial_plan()[0]
    slices = split_by_bedrooms(seed)

    bedroom_values = [s.bedrooms for s in slices]
    assert 1 in bedroom_values
    assert None in bedroom_values


def test_plan_hash_is_deterministic():
    a = build_initial_plan()
    b = build_initial_plan()
    assert plan_hash(a) == plan_hash(b)


def test_classify_candidate_for_montevideo_rental_returns_candidate():
    item = {
        "category_id": CATEGORY_APARTMENT,
        "location": {"state": {"name": "Montevideo"}},
        "attributes": [
            {"id": "OPERATION", "value_name": "Alquiler"},
            {"id": "PROPERTY_TYPE", "value_name": "Apartamento"},
        ],
    }
    status, reason = classify_candidate(item)
    assert status == "candidate"
    assert reason is None


def test_classify_candidate_excludes_sales():
    item = {
        "category_id": CATEGORY_APARTMENT,
        "location": {"state": {"name": "Montevideo"}},
        "attributes": [
            {"id": "OPERATION", "value_name": "Venta"},
        ],
    }
    status, reason = classify_candidate(item)
    assert status == "excluded"
    assert reason == "sale"


def test_classify_candidate_excludes_temporary_rentals():
    item = {
        "category_id": CATEGORY_APARTMENT,
        "location": {"state": {"name": "Montevideo"}},
        "attributes": [
            {"id": "OPERATION", "value_name": "Alquiler temporal"},
        ],
    }
    status, reason = classify_candidate(item)
    assert status == "excluded"
    assert reason == "temporary_rental"


def test_classify_candidate_excludes_locations_outside_montevideo():
    item = {
        "category_id": CATEGORY_APARTMENT,
        "location": {"state": {"name": "Canelones"}},
        "attributes": [{"id": "OPERATION", "value_name": "Alquiler"}],
    }
    status, reason = classify_candidate(item)
    assert status == "excluded"
    assert reason == "outside_montevideo"


def test_classify_candidate_flags_missing_operation_as_unknown():
    item = {
        "category_id": CATEGORY_APARTMENT,
        "location": {"state": {"name": "Montevideo"}},
        "attributes": [],
    }
    status, reason = classify_candidate(item)
    assert status == "unknown"
    assert reason == "missing_operation"
