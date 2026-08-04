"""Tests for token loading and log redaction."""

from __future__ import annotations

from alquileres_uy.ingest.auth import (
    ACCESS_TOKEN_ENV_VAR,
    load_access_token,
    redact_headers,
    redact_url,
)


def test_load_access_token_returns_none_when_env_missing(monkeypatch):
    monkeypatch.delenv(ACCESS_TOKEN_ENV_VAR, raising=False)
    assert load_access_token() is None


def test_load_access_token_strips_whitespace(monkeypatch):
    monkeypatch.setenv(ACCESS_TOKEN_ENV_VAR, "  abc  ")
    assert load_access_token() == "abc"


def test_load_access_token_treats_blank_as_missing(monkeypatch):
    monkeypatch.setenv(ACCESS_TOKEN_ENV_VAR, "   ")
    assert load_access_token() is None


def test_redact_headers_masks_authorization():
    redacted = redact_headers({"Authorization": "Bearer secret", "User-Agent": "ua"})
    assert redacted["Authorization"].startswith("***")
    assert redacted["User-Agent"] == "ua"


def test_redact_headers_masks_cookie_and_other_secrets():
    redacted = redact_headers({"Cookie": "session=xyz", "X-Auth-Token": "abc"})
    assert "xyz" not in redacted["Cookie"]
    assert "abc" not in redacted["X-Auth-Token"]


def test_redact_url_removes_access_token_query_param():
    url = "https://api.mercadolibre.com/items?ids=MLU1&access_token=abcdef"
    redacted = redact_url(url)
    assert "abcdef" not in redacted
    assert "ids=MLU1" in redacted
