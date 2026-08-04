"""Tests for atomic filesystem writes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from alquileres_uy.ingest.filesystem import (
    append_jsonl,
    atomic_write_bytes,
    atomic_write_json,
    compute_sha256,
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
