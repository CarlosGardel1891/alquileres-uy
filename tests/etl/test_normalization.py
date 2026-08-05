from alquileres_uy.etl.normalization import normalize_key, normalize_text


def test_normalize_text_returns_none_for_none():
    assert normalize_text(None) is None


def test_normalize_text_removes_null_bytes_and_collapses_spaces():
    assert normalize_text("hola\x00  mundo  ") == "hola mundo"


def test_normalize_text_collapses_repeated_newlines():
    assert normalize_text("linea1\n\n\nlinea2") == "linea1\nlinea2"


def test_normalize_text_preserves_case_and_punctuation():
    assert normalize_text("Apartamento en Pocitos, Piso 5.") == "Apartamento en Pocitos, Piso 5."


def test_normalize_key_lowercases_and_strips_diacritics():
    assert normalize_key("  Cásás  ") == "casas"


def test_normalize_key_collapses_internal_whitespace():
    assert normalize_key("Punta   Carretas") == "punta carretas"


def test_normalize_key_returns_none_for_empty():
    assert normalize_key("") is None
    assert normalize_key(None) is None
