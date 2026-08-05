import pandas as pd

from alquileres_uy.etl.quality import build_quality_report


def test_quality_report_marks_fixture_mode():
    empty = pd.DataFrame()
    report = build_quality_report(
        canonical=empty,
        model_ready=empty,
        rejected=empty,
        duplicate_candidates=empty,
        input_items=0,
        parsed_items=0,
        unmapped_attribute_counts={},
        area_inconsistencies=0,
        invalid_dates=0,
        common_expenses_missing=0,
        data_mode="fixture",
    )
    assert report["data_mode"] == "fixture"
    assert "warning" in report


def test_quality_report_counts_rejections():
    rejected = pd.DataFrame(
        [
            {"rejection_reasons": "sale"},
            {"rejection_reasons": "sale|outside_montevideo"},
            {"rejection_reasons": "temporary_rental"},
        ]
    )
    report = build_quality_report(
        canonical=pd.DataFrame(),
        model_ready=pd.DataFrame(),
        rejected=rejected,
        duplicate_candidates=pd.DataFrame(),
        input_items=0,
        parsed_items=0,
        unmapped_attribute_counts={"UNKNOWN_ATTR": 1},
        area_inconsistencies=0,
        invalid_dates=0,
        common_expenses_missing=0,
        data_mode="fixture",
    )
    assert report["rejections_by_reason"]["sale"] == 2
    assert report["rejections_by_reason"]["outside_montevideo"] == 1
    assert report["unmapped_attributes"]["UNKNOWN_ATTR"] == 1
