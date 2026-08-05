from alquileres_uy.etl.neighborhoods import load_aliases


def test_load_returns_empty_when_none():
    aliases = load_aliases(None)
    assert aliases.aliases == {}


def test_resolve_known_alias(neighborhood_aliases_path):
    aliases = load_aliases(neighborhood_aliases_path)
    canonical, known = aliases.resolve("Pocitos Nuevo")
    assert canonical == "Pocitos"
    assert known is True


def test_resolve_unknown_preserves_clean_name(neighborhood_aliases_path):
    aliases = load_aliases(neighborhood_aliases_path)
    canonical, known = aliases.resolve("  Villa Nueva  ")
    assert canonical == "Villa Nueva"
    assert known is False


def test_resolve_none_returns_none(neighborhood_aliases_path):
    aliases = load_aliases(neighborhood_aliases_path)
    canonical, known = aliases.resolve(None)
    assert canonical is None
    assert known is False


def test_resolve_case_and_accents(neighborhood_aliases_path):
    aliases = load_aliases(neighborhood_aliases_path)
    canonical, known = aliases.resolve("CORDÓN")
    assert canonical == "Cordón"
    assert known is True
