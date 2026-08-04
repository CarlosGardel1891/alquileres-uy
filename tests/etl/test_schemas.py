import pandas as pd
import pandera as pa
import pytest

from alquileres_uy.etl.schemas import (
    CanonicalListingsSchema,
    DuplicateCandidatesSchema,
    ModelReadySchema,
    RejectedListingsSchema,
    check_model_ready_leakage,
)


def _canonical(**overrides):
    row = {
        "source_item_id": "MLU_TEST_001",
        "source": "mercadolibre",
        "source_run_id": "run1",
        "raw_item_path": "run1/items/batch_0001.json",
        "operation": "monthly_rent",
        "property_type": "apartment",
        "department": "Montevideo",
        "currency_original": "USD",
        "price_usd": 1200.0,
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_canonical_schema_accepts_valid_row():
    CanonicalListingsSchema.validate(_canonical(), lazy=True)


def test_canonical_schema_rejects_negative_price():
    with pytest.raises(pa.errors.SchemaErrors):
        CanonicalListingsSchema.validate(_canonical(price_usd=-1), lazy=True)


def test_canonical_schema_rejects_duplicate_ids():
    df = pd.concat([_canonical(), _canonical()], ignore_index=True)
    with pytest.raises(pa.errors.SchemaErrors):
        CanonicalListingsSchema.validate(df, lazy=True)


def test_model_ready_rejects_missing_required():
    df = pd.DataFrame(
        [
            {
                "source_item_id": "MLU_TEST_001",
                "property_type": "apartment",
                "neighborhood_normalized": "Pocitos",
                "bedrooms": 2,
                "total_area_m2": 50.0,
                "price_usd": 1200.0,
                "date_created": None,
            }
        ]
    )
    with pytest.raises(pa.errors.SchemaErrors):
        ModelReadySchema.validate(df, lazy=True)


def test_rejected_requires_reasons():
    df = pd.DataFrame(
        [
            {
                "source_run_id": "r1",
                "raw_item_path": "r1/items/x.json",
                "rejection_reasons": "",
            }
        ]
    )
    with pytest.raises(pa.errors.SchemaErrors):
        RejectedListingsSchema.validate(df, lazy=True)


def test_duplicate_candidates_require_at_least_two_members():
    df = pd.DataFrame(
        [
            {
                "possible_duplicate_group_id": "group",
                "source_item_id": "MLU_TEST_001",
                "member_count": 1,
            }
        ]
    )
    with pytest.raises(pa.errors.SchemaErrors):
        DuplicateCandidatesSchema.validate(df, lazy=True)


def test_check_model_ready_leakage_blocks_price_per_m2():
    with pytest.raises(ValueError, match="target-derived"):
        check_model_ready_leakage(["source_item_id", "price_per_m2"])


def test_check_model_ready_leakage_blocks_total_monthly_cost():
    with pytest.raises(ValueError):
        check_model_ready_leakage(["source_item_id", "total_monthly_cost_usd"])


def test_check_model_ready_leakage_allows_clean_columns():
    check_model_ready_leakage(
        ["source_item_id", "property_type", "bedrooms", "total_area_m2", "price_usd"]
    )
