"""Atomic file writes and content hashing for raw response storage.

Raw responses are written to a temporary sibling file and then renamed into
place with :func:`os.replace`, which is atomic on POSIX and Windows for
regular files on the same volume. A SHA-256 digest of the exact bytes on
disk is returned so the caller can persist it in the audit log.

Once written, callers must treat the file as immutable.

The :func:`sanitize_for_artifact` helper strips any sensitive value from
a payload before it is persisted. It redacts a fixed set of case-
insensitive keys (``authorization``, ``access_token``, ``token``,
``cookie``, ``x-auth-token``) *and*, when a specific token string is
passed in, replaces every literal occurrence of that token inside
strings, URLs and error messages.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REDACTED = "***REDACTED***"
SENSITIVE_KEYS: frozenset[str] = frozenset(
    {"authorization", "access_token", "token", "cookie", "x-auth-token"}
)


def compute_sha256(payload: bytes) -> str:
    """Return the hexadecimal SHA-256 digest of ``payload``."""
    return hashlib.sha256(payload).hexdigest()


def atomic_write_bytes(destination: Path, payload: bytes) -> tuple[Path, str]:
    """Write ``payload`` to ``destination`` atomically.

    Returns the final path and the SHA-256 of the bytes actually written.
    Refuses to overwrite an existing file to preserve the immutability
    invariant of raw responses.
    """
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(f"raw file already exists: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = destination.with_name(destination.name + ".tmp")
    with open(tmp_path, "wb") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, destination)
    return destination, compute_sha256(payload)


def atomic_write_json(destination: Path, data: Any) -> tuple[Path, str]:
    """Serialize ``data`` as UTF-8 JSON and write it atomically."""
    payload = json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    return atomic_write_bytes(destination, payload)


def sanitize_for_artifact(value: Any, token: str | None = None) -> Any:
    """Return ``value`` with sensitive keys redacted, recursively.

    - Mapping entries whose *key* (case-insensitive) is in
      :data:`SENSITIVE_KEYS` have their value replaced by ``"***REDACTED***"``,
      no matter what the value's type is.
    - Strings that contain the exact ``token`` (when provided) have every
      occurrence replaced by ``"***REDACTED***"``. This catches leaks in
      URLs, query strings, error messages and free-form text.
    - Lists and tuples are sanitized element by element.
    - Non-container values are returned unchanged.
    """
    token = token or None

    def _walk(node: Any) -> Any:
        if isinstance(node, Mapping):
            sanitized: dict[str, Any] = {}
            for key, sub in node.items():
                if isinstance(key, str) and key.lower() in SENSITIVE_KEYS:
                    sanitized[key] = REDACTED
                else:
                    sanitized[key] = _walk(sub)
            return sanitized
        if isinstance(node, list | tuple):
            return [_walk(item) for item in node]
        if isinstance(node, str):
            if token and token in node:
                return node.replace(token, REDACTED)
            return node
        return node

    return _walk(value)


def append_jsonl(destination: Path, record: dict[str, Any]) -> None:
    """Append a single JSON object as a line to ``destination``.

    Used for the ``errors.jsonl`` stream where multiple entries accumulate.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    with open(destination, "a", encoding="utf-8") as fh:
        fh.write(line)
        fh.flush()
