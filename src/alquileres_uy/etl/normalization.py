"""Textual normalization helpers used across the ETL."""

from __future__ import annotations

import re
import unicodedata

_MULTI_SPACE = re.compile(r"\s+")
_MULTI_NEWLINE = re.compile(r"(\r?\n)+")


def normalize_text(value: str | None) -> str | None:
    """Sanitize free-form text for storage in the canonical dataset."""
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    cleaned = value.replace("\x00", "")
    cleaned = unicodedata.normalize("NFC", cleaned)
    cleaned = _MULTI_NEWLINE.sub("\n", cleaned)
    cleaned = "\n".join(_MULTI_SPACE.sub(" ", line).strip() for line in cleaned.split("\n"))
    cleaned = cleaned.strip()
    return cleaned or None


def normalize_key(value: str | None) -> str | None:
    """Return a diacritic-free, lowercase, space-collapsed key for comparison."""
    if value is None or not isinstance(value, str):
        return None
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = stripped.lower().strip()
    collapsed = _MULTI_SPACE.sub(" ", lowered)
    return collapsed or None
