from alquileres_uy.etl.deduplication import content_hash, possible_duplicate_key


def _row(**overrides):
    base = {
        "property_type": "apartment",
        "neighborhood_normalized": "Pocitos",
        "bedrooms": 2,
        "total_area_m2": 60,
        "price_usd": 1200,
        "title": "Apartamento en Pocitos",
    }
    base.update(overrides)
    return base


def test_content_hash_is_stable():
    assert content_hash(_row()) == content_hash(_row())


def test_content_hash_changes_with_price():
    assert content_hash(_row()) != content_hash(_row(price_usd=1300))


def test_content_hash_none_without_price():
    assert content_hash(_row(price_usd=None)) is None


def test_possible_duplicate_key_buckets_similar_listings():
    a = possible_duplicate_key(_row(price_usd=1200, total_area_m2=60))
    b = possible_duplicate_key(_row(price_usd=1230, total_area_m2=62))
    assert a == b


def test_possible_duplicate_key_differs_when_bucket_changes():
    a = possible_duplicate_key(_row(price_usd=1200))
    b = possible_duplicate_key(_row(price_usd=2200))
    assert a != b


def test_possible_duplicate_key_none_when_missing_data():
    assert possible_duplicate_key(_row(bedrooms=None)) is None
