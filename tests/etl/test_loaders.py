from alquileres_uy.etl.contracts import load_raw_run
from alquileres_uy.etl.loaders import iter_raw_items

FIXTURES_ROOT = None  # patched via conftest.etl_fixture_run


def test_iter_raw_items_yields_expected_count(etl_fixture_run):
    run = load_raw_run(
        etl_fixture_run,
        data_mode="fixture",
        fixtures_root=etl_fixture_run.parents[2],
    )
    items = list(iter_raw_items(run))
    # 25 real items plus 2 partial-failure envelopes.
    assert len(items) == 27


def test_iter_raw_items_marks_partial_failures(etl_fixture_run):
    run = load_raw_run(
        etl_fixture_run,
        data_mode="fixture",
        fixtures_root=etl_fixture_run.parents[2],
    )
    items = list(iter_raw_items(run))
    failures = [item for item in items if not item.body]
    assert len(failures) == 2


def test_iter_raw_items_attaches_descriptions(etl_fixture_run):
    run = load_raw_run(
        etl_fixture_run,
        data_mode="fixture",
        fixtures_root=etl_fixture_run.parents[2],
    )
    with_description = [item for item in iter_raw_items(run) if item.description_body is not None]
    # 3 unique item IDs have description files (001, 002, 003); item 001
    # appears twice in the batches (exact-ID duplicate), so 4 envelopes
    # get a description attached.
    assert len(with_description) == 4
    unique_ids = {item.source_item_id for item in with_description}
    assert unique_ids == {"MLU_TEST_001", "MLU_TEST_002", "MLU_TEST_003"}
