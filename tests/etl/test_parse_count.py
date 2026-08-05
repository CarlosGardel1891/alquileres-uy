"""parse_count and hardened parse_area unit-rejection tests."""

from __future__ import annotations

from decimal import Decimal

from alquileres_uy.etl.extractors import (
    COUNT_ATTRIBUTE_UNIT_ALIASES,
    parse_area,
    parse_count,
)


def test_parse_count_simple_int():
    value, err = parse_count(3)
    assert err is None
    assert value == Decimal("3")


def test_parse_count_struct_without_unit_allowed():
    value, err = parse_count({"number": 3})
    assert err is None
    assert value == Decimal("3")


def test_parse_count_struct_with_allowed_unit_for_bedrooms():
    value, err = parse_count(
        {"number": 3, "unit": "dormitorios"},
        allowed_units=COUNT_ATTRIBUTE_UNIT_ALIASES["BEDROOMS"],
    )
    assert err is None
    assert value == Decimal("3")


def test_parse_count_rejects_kg_for_bedrooms():
    value, err = parse_count(
        {"number": 3, "unit": "kg"},
        allowed_units=COUNT_ATTRIBUTE_UNIT_ALIASES["BEDROOMS"],
    )
    assert value is None
    assert err == "unsupported_count_unit"


def test_parse_count_rejects_m_squared_for_bathrooms():
    value, err = parse_count(
        {"number": 2, "unit": "m²"},
        allowed_units=COUNT_ATTRIBUTE_UNIT_ALIASES["BATHROOMS"],
    )
    assert value is None
    assert err == "unsupported_count_unit"


def test_parse_count_accepts_piso_for_floor():
    value, err = parse_count(
        {"number": 5, "unit": "piso"},
        allowed_units=COUNT_ATTRIBUTE_UNIT_ALIASES["FLOOR"],
    )
    assert err is None
    assert value == Decimal("5")


def test_parse_area_65_m_squared_still_valid():
    value, err = parse_area("65 m²")
    assert err is None


def test_parse_area_65_acres_is_unsupported():
    value, err = parse_area("65 acres")
    assert value is None
    assert err == "unsupported_area_unit"


def test_parse_area_65_yardas_is_unsupported():
    value, err = parse_area("65 yardas")
    assert value is None
    assert err == "unsupported_area_unit"


def test_parse_area_65_bananas_is_unsupported():
    value, err = parse_area("65 bananas")
    assert value is None
    assert err == "unsupported_area_unit"


def test_parse_area_value_struct_unknown_unit_unsupported():
    value, err = parse_area({"number": 65, "unit": "wat"})
    assert value is None
    assert err == "unsupported_area_unit"


def test_parse_area_range_still_invalid_range():
    value, err = parse_area("65-70 m²")
    assert value is None
    assert err == "invalid_range"


def test_parse_area_approximate_still_invalid_number():
    value, err = parse_area("aproximadamente 65 m²")
    assert value is None
    assert err == "invalid_number"


def test_pipeline_unsupported_count_unit_ends_up_in_quality_issues(
    tmp_path, exchange_rate_path, neighborhood_aliases_path
):
    from alquileres_uy.etl.config import EtlConfig
    from alquileres_uy.etl.pipeline import EtlPipeline

    config = EtlConfig(
        input_run_dirs=(_make_run_with_bad_bedroom_unit(tmp_path),),
        exchange_rate_path=exchange_rate_path,
        neighborhood_aliases_path=neighborhood_aliases_path,
        output_dir=tmp_path / "out",
        fixture_mode=True,
    )
    result = EtlPipeline(config).run()
    joined = "|".join(result.canonical["quality_issues"].fillna("").tolist())
    assert "unsupported_count_unit" in joined


def test_strict_flags_unsupported_count_unit(
    tmp_path, exchange_rate_path, neighborhood_aliases_path
):
    import pytest

    from alquileres_uy.etl.config import EtlConfig
    from alquileres_uy.etl.pipeline import EtlPipeline, StrictQualityGateError

    config = EtlConfig(
        input_run_dirs=(_make_run_with_bad_bedroom_unit(tmp_path),),
        exchange_rate_path=exchange_rate_path,
        neighborhood_aliases_path=neighborhood_aliases_path,
        output_dir=tmp_path / "out",
        fixture_mode=True,
        strict=True,
    )
    with pytest.raises(StrictQualityGateError):
        EtlPipeline(config).run()


def _make_run_with_bad_bedroom_unit(tmp_path):
    import hashlib
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "fixtures" / f"etl_bad_unit_{tmp_path.name}"
    root.mkdir(parents=True, exist_ok=True)
    (root / "items").mkdir(exist_ok=True)
    body = {
        "id": "MLU_TEST_KG",
        "title": "Apartamento en Pocitos",
        "category_id": "MLU_TEST_APARTMENT",
        "price": 1000,
        "currency_id": "USD",
        "date_created": "2026-01-01T09:00:00Z",
        "location": {
            "state": {"name": "Montevideo"},
            "city": {"name": "Pocitos"},
            "neighborhood": {"name": "Pocitos"},
        },
        "attributes": [
            {"id": "OPERATION", "value_id": "242075", "value_name": "Alquiler"},
            {"id": "PROPERTY_TYPE", "value_name": "Apartamento"},
            {"id": "BEDROOMS", "value_struct": {"number": 3, "unit": "kg"}},
            {"id": "TOTAL_AREA", "value_name": "50 m2"},
        ],
    }
    batch = root / "items" / "batch_0001.json"
    batch.write_text(json.dumps([{"code": 200, "body": body}]), encoding="utf-8")
    summary = root / "ingestion_summary.json"
    summary.write_text(
        json.dumps(
            {
                "run_id": "r-kg",
                "status": "completed",
                "started_at": "2026-08-04T22:00:00Z",
                "finished_at": "2026-08-04T22:15:00Z",
                "items_downloaded": 1,
                "descriptions_downloaded": 0,
            }
        ),
        encoding="utf-8",
    )
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "r-kg",
                "source": "mercadolibre",
                "status": "completed",
                "started_at": "2026-08-04T22:00:00Z",
                "finished_at": "2026-08-04T22:15:00Z",
                "files": [
                    {
                        "path": "items/batch_0001.json",
                        "kind": "item_batch",
                        "sha256": hashlib.sha256(batch.read_bytes()).hexdigest(),
                    },
                    {
                        "path": "ingestion_summary.json",
                        "kind": "report",
                        "sha256": hashlib.sha256(summary.read_bytes()).hexdigest(),
                    },
                ],
                "summary_path": "ingestion_summary.json",
            }
        ),
        encoding="utf-8",
    )
    return root
