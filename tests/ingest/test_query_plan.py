"""Tests for the deterministic query plan and preliminary classification."""

from __future__ import annotations

import itertools

import pytest

from alquileres_uy.ingest import query_plan
from alquileres_uy.ingest.query_plan import (
    build_initial_plan,
    classify_candidate,
    page_fingerprint,
    plan_hash,
    split_by_bedrooms,
    split_by_price,
)

from .conftest import approved_contract


def test_build_initial_plan_uses_categories_from_contract():
    contract = approved_contract(category_ids={"apartment": "MLU1743", "house": "MLU1466"})
    segments = build_initial_plan(contract)

    property_types = sorted(segment.property_type for segment in segments)
    categories = {segment.property_type: segment.category_id for segment in segments}
    assert property_types == ["apartment", "house"]
    assert categories["apartment"] == "MLU1743"
    assert categories["house"] == "MLU1466"
    for segment in segments:
        assert segment.parameters["state"] == "Montevideo"
        assert segment.parameters["operation"] == "rent"


def test_build_initial_plan_raises_when_contract_has_no_categories():
    contract = approved_contract(category_ids={})
    with pytest.raises(ValueError, match="verified categories"):
        build_initial_plan(contract)


def test_build_initial_plan_raises_when_category_id_is_empty():
    contract = approved_contract(category_ids={"apartment": ""})
    with pytest.raises(ValueError, match="category id for"):
        build_initial_plan(contract)


def test_query_plan_module_has_no_hardcoded_category_constants():
    for banned in ("CATEGORY_APARTMENT", "CATEGORY_HOUSE"):
        assert not hasattr(
            query_plan, banned
        ), f"{banned} must be removed — categories must come from the approved contract"


def test_split_by_price_produces_contiguous_bands_without_gaps():
    contract = approved_contract()
    seed = build_initial_plan(contract)[0]
    slices = split_by_price(seed)

    assert len(slices) >= 2
    boundaries = [s.price_min for s in slices]
    assert boundaries == sorted(boundaries)
    for previous, current in itertools.pairwise(slices):
        assert previous.price_max is None or previous.price_max == current.price_min


def test_split_by_bedrooms_covers_expected_buckets():
    contract = approved_contract()
    seed = build_initial_plan(contract)[0]
    slices = split_by_bedrooms(seed)

    bedroom_values = [s.bedrooms for s in slices]
    assert 1 in bedroom_values
    assert None in bedroom_values


def test_plan_hash_is_deterministic():
    contract = approved_contract()
    a = build_initial_plan(contract)
    b = build_initial_plan(contract)
    assert plan_hash(a) == plan_hash(b)


def test_page_fingerprint_is_independent_of_input_order():
    assert page_fingerprint(["MLU3", "MLU1", "MLU2"]) == page_fingerprint(["MLU1", "MLU2", "MLU3"])


def test_page_fingerprint_differs_between_different_id_sets():
    a = page_fingerprint(["MLU1", "MLU2", "MLU3"])
    b = page_fingerprint(["MLU1", "MLU2", "MLU4"])
    assert a != b


def test_classify_candidate_returns_candidate_when_category_matches_contract():
    contract = approved_contract(category_ids={"apartment": "MLU1743"})
    item = {
        "category_id": "MLU1743",
        "location": {"state": {"name": "Montevideo"}},
        "attributes": [
            {"id": "OPERATION", "value_name": "Alquiler"},
        ],
    }
    status, reason = classify_candidate(item, contract)
    assert status == "candidate"
    assert reason is None


def test_classify_candidate_accepts_property_type_attribute_even_without_category_match():
    contract = approved_contract(category_ids={"apartment": "MLU9999"})
    item = {
        "category_id": "MLU_UNRELATED",
        "location": {"state": {"name": "Montevideo"}},
        "attributes": [
            {"id": "OPERATION", "value_name": "Alquiler"},
            {"id": "PROPERTY_TYPE", "value_name": "Apartamento"},
        ],
    }
    status, reason = classify_candidate(item, contract)
    assert status == "candidate"
    assert reason is None


def test_classify_candidate_marks_unknown_when_neither_category_nor_property_type_present():
    contract = approved_contract(category_ids={"apartment": "MLU9999"})
    item = {
        "category_id": "MLU_UNRELATED",
        "location": {"state": {"name": "Montevideo"}},
        "attributes": [
            {"id": "OPERATION", "value_name": "Alquiler"},
        ],
    }
    status, reason = classify_candidate(item, contract)
    assert status == "unknown"
    assert reason == "wrong_property_type"


def test_classify_candidate_excludes_sales():
    contract = approved_contract()
    item = {
        "category_id": "MLU1743",
        "location": {"state": {"name": "Montevideo"}},
        "attributes": [{"id": "OPERATION", "value_name": "Venta"}],
    }
    status, reason = classify_candidate(item, contract)
    assert status == "excluded"
    assert reason == "sale"


def test_classify_candidate_excludes_temporary_rentals():
    contract = approved_contract()
    item = {
        "category_id": "MLU1743",
        "location": {"state": {"name": "Montevideo"}},
        "attributes": [{"id": "OPERATION", "value_name": "Alquiler temporal"}],
    }
    status, reason = classify_candidate(item, contract)
    assert status == "excluded"
    assert reason == "temporary_rental"


def test_classify_candidate_excludes_outside_montevideo():
    contract = approved_contract()
    item = {
        "category_id": "MLU1743",
        "location": {"state": {"name": "Canelones"}},
        "attributes": [{"id": "OPERATION", "value_name": "Alquiler"}],
    }
    status, reason = classify_candidate(item, contract)
    assert status == "excluded"
    assert reason == "outside_montevideo"


def test_classify_candidate_flags_missing_operation_as_unknown():
    contract = approved_contract()
    item = {
        "category_id": "MLU1743",
        "location": {"state": {"name": "Montevideo"}},
        "attributes": [],
    }
    status, reason = classify_candidate(item, contract)
    assert status == "unknown"
    assert reason == "missing_operation"
