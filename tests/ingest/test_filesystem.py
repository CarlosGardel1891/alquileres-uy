"""Tests for atomic filesystem writes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from alquileres_uy.ingest.filesystem import (
    REDACTED,
    append_jsonl,
    atomic_write_bytes,
    atomic_write_json,
    compute_sha256,
    sanitize_for_artifact,
)


def test_atomic_write_json_writes_content_and_returns_sha256(tmp_path: Path) -> None:
    destination = tmp_path / "sub" / "payload.json"
    data = {"hello": "world", "n": 42}

    path, digest = atomic_write_json(destination, data)

    assert path == destination
    assert path.exists()
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk == data
    assert digest == compute_sha256(path.read_bytes())


def test_atomic_write_refuses_to_overwrite_existing_file(tmp_path: Path) -> None:
    destination = tmp_path / "raw.json"
    atomic_write_json(destination, {"a": 1})

    with pytest.raises(FileExistsError):
        atomic_write_json(destination, {"a": 2})


def test_compute_sha256_is_stable() -> None:
    payload = b"the quick brown fox"
    assert compute_sha256(payload) == compute_sha256(payload)
    assert compute_sha256(payload) != compute_sha256(payload + b"!")


def test_atomic_write_bytes_leaves_no_tmp_file(tmp_path: Path) -> None:
    destination = tmp_path / "bytes.bin"
    atomic_write_bytes(destination, b"hello")

    siblings = list(destination.parent.iterdir())
    assert siblings == [destination]


def test_append_jsonl_writes_one_line_per_record(tmp_path: Path) -> None:
    path = tmp_path / "errors.jsonl"
    append_jsonl(path, {"a": 1})
    append_jsonl(path, {"b": 2})

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert [json.loads(line) for line in lines] == [{"a": 1}, {"b": 2}]


# ---- sanitize_for_artifact ------------------------------------------------


def test_sanitize_redacts_authorization_key_regardless_of_case():
    payload = {"Authorization": "Bearer abc", "AUTHORIZATION": "Bearer def"}
    sanitized = sanitize_for_artifact(payload)
    assert sanitized["Authorization"] == REDACTED
    assert sanitized["AUTHORIZATION"] == REDACTED


def test_sanitize_redacts_nested_sensitive_keys_in_dicts_and_lists():
    payload = {
        "outer": {
            "cookie": "session=xyz",
            "safe": "keep",
            "list": [{"access_token": "leak"}, {"note": "ok"}],
        }
    }
    sanitized = sanitize_for_artifact(payload)
    assert sanitized["outer"]["cookie"] == REDACTED
    assert sanitized["outer"]["safe"] == "keep"
    assert sanitized["outer"]["list"][0]["access_token"] == REDACTED
    assert sanitized["outer"]["list"][1]["note"] == "ok"


def test_sanitize_redacts_literal_token_inside_strings():
    payload = {
        "url": "https://api.mercadolibre.com/items?access_token=SECRET",
        "message": "auth failed for token SECRET",
        "nested": ["prefix SECRET suffix"],
    }
    sanitized = sanitize_for_artifact(payload, token="SECRET")
    assert "SECRET" not in sanitized["url"]
    assert "SECRET" not in sanitized["message"]
    assert "SECRET" not in sanitized["nested"][0]


def test_sanitize_leaves_ordinary_payloads_untouched():
    payload = {"id": "MLU123", "results": [{"title": "Casa"}, {"title": "Apto"}]}
    sanitized = sanitize_for_artifact(payload)
    assert sanitized == payload


def test_sanitize_redacts_xauth_and_token_keys():
    payload = {"x-auth-token": "abc", "token": "def"}
    sanitized = sanitize_for_artifact(payload)
    assert sanitized["x-auth-token"] == REDACTED
    assert sanitized["token"] == REDACTED


def test_sanitize_handles_non_container_values():
    assert sanitize_for_artifact("plain") == "plain"
    assert sanitize_for_artifact(42) == 42
    assert sanitize_for_artifact(None) is None
    assert sanitize_for_artifact([1, 2, 3]) == [1, 2, 3]
