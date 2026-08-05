"""Loader and lookup for the neighborhood alias table."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .normalization import normalize_key, normalize_text


class InvalidAliasFile(ValueError):
    """Raised when the neighborhood alias file cannot be trusted."""


@dataclass(frozen=True)
class NeighborhoodAliases:
    """Mapping from normalized alias to canonical display name."""

    aliases: dict[str, str] = field(default_factory=dict)
    version: str = ""
    source: str = ""
    updated_at: str = ""

    def resolve(self, raw: str | None) -> tuple[str | None, bool]:
        """Return ``(canonical_name, is_known)`` for ``raw``."""
        clean = normalize_text(raw)
        if clean is None:
            return None, False
        key = normalize_key(clean)
        if key is None:
            return None, False
        canonical = self.aliases.get(key)
        if canonical:
            return canonical, True
        # Unknown neighborhood: preserve the cleaned name but flag it.
        return clean, False


def load_aliases(path: Path | None) -> NeighborhoodAliases:
    """Load and validate a neighborhood alias JSON file. ``None`` returns empty."""
    if path is None:
        return NeighborhoodAliases()
    path = Path(path)
    if not path.is_file():
        raise InvalidAliasFile(f"neighborhood aliases not found: {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InvalidAliasFile(f"aliases file is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise InvalidAliasFile("aliases file root must be a JSON object")

    metadata = raw.get("metadata") or {}
    aliases_raw = raw.get("aliases") or {}
    if not isinstance(aliases_raw, dict):
        raise InvalidAliasFile("aliases['aliases'] must be an object")

    aliases: dict[str, str] = {}
    for alias, canonical in aliases_raw.items():
        if not isinstance(alias, str) or not isinstance(canonical, str):
            raise InvalidAliasFile("every alias mapping must be string→string")
        key = normalize_key(alias)
        if not key:
            continue
        aliases[key] = canonical.strip()
        # Also index the canonical name itself so exact matches work.
        canonical_key = normalize_key(canonical.strip())
        if canonical_key and canonical_key not in aliases:
            aliases[canonical_key] = canonical.strip()

    return NeighborhoodAliases(
        aliases=aliases,
        version=str(metadata.get("version") or ""),
        source=str(metadata.get("source") or ""),
        updated_at=str(metadata.get("updated_at") or ""),
    )
