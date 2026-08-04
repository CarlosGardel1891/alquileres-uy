"""BFS resolver for the MercadoLibre site category tree.

The site categories endpoint (``/sites/{site_id}/categories``) only
returns the root nodes of the taxonomy. Real leaf categories such as
"Apartamentos" or "Casas" can live several levels deep under an
intermediate node (typically "Inmuebles"). Consuming only the root list
was the historical bug that made the source gate silently miss the
required categories even when the API was fully available.

This module walks the tree iteratively (BFS) starting from the root
endpoint and, for every visited node, calls
``/categories/{category_id}`` to read its ``children_categories``. It
persists each raw response under the gate workdir, tracks visited IDs
to avoid cycles and duplicate work, and stops on defensive limits so a
malformed API never produces an infinite loop.

The final resolution states, per required property type:

- ``verified``: exactly one node matches its normalized alias set;
- ``ambiguous``: multiple candidates matched — the gate must resolve
  this manually, so the resolver refuses to pick one silently;
- ``missing``: no candidate was found within the traversal limits.
"""

from __future__ import annotations

import logging
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .client import MercadoLibreClient
from .errors import IngestionError
from .filesystem import atomic_write_json, sanitize_for_artifact
from .models import REQUIRED_PROPERTY_TYPES

logger = logging.getLogger(__name__)

MAX_CATEGORY_DEPTH = 10
MAX_CATEGORY_NODES = 1000

PROPERTY_TYPE_LABELS: dict[str, frozenset[str]] = {
    "apartment": frozenset({"apartamento", "apartamentos", "apartment", "apartments"}),
    "house": frozenset({"casa", "casas", "house", "houses"}),
}


def normalize_category_name(value: str) -> str:
    """Return a canonical form for exact-match category comparisons.

    Normalizes Unicode to NFKD, strips diacritics, lower-cases, trims
    outer whitespace and collapses internal runs of whitespace to a
    single space. Substring matching is never used downstream — the
    canonical form is compared exactly against a fixed alias set.
    """
    if not isinstance(value, str):
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = stripped.strip().lower()
    return " ".join(lowered.split())


@dataclass(frozen=True)
class CategoryResolution:
    """Outcome of walking the site category tree.

    ``verified_category_ids`` is the safe mapping the source gate will
    use. ``candidates`` lists every match found per property type,
    including the ambiguous ones, so the audit trail keeps them.
    """

    verified_category_ids: dict[str, str]
    candidates: dict[str, list[str]]
    nodes_visited: int
    max_depth_reached: int
    ambiguous_property_types: list[str]
    missing_property_types: list[str]
    limits_exceeded: bool
    notes: list[str]

    def as_dict(self) -> dict[str, Any]:
        required: dict[str, dict[str, Any]] = {}
        for property_type in sorted(REQUIRED_PROPERTY_TYPES):
            if property_type in self.verified_category_ids:
                required[property_type] = {
                    "status": "verified",
                    "category_id": self.verified_category_ids[property_type],
                }
            elif property_type in self.ambiguous_property_types:
                required[property_type] = {
                    "status": "ambiguous",
                    "candidates": list(self.candidates.get(property_type, [])),
                }
            else:
                required[property_type] = {"status": "missing"}
        return {
            "nodes_visited": self.nodes_visited,
            "max_depth_reached": self.max_depth_reached,
            "required_categories": required,
            "ambiguous_matches": {
                pt: list(self.candidates.get(pt, [])) for pt in self.ambiguous_property_types
            },
            "missing_property_types": list(self.missing_property_types),
            "limits_exceeded": self.limits_exceeded,
            "notes": list(self.notes),
        }


@dataclass
class _Node:
    id: str
    name: str
    depth: int


@dataclass
class _WalkState:
    visited: set[str] = field(default_factory=set)
    nodes_visited: int = 0
    max_depth_reached: int = 0
    limits_exceeded: bool = False
    candidates: dict[str, list[str]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    files_written: list[Path] = field(default_factory=list)


def resolve_category_tree(
    client: MercadoLibreClient,
    site_id: str,
    workdir: Path,
    *,
    token: str | None = None,
    max_depth: int = MAX_CATEGORY_DEPTH,
    max_nodes: int = MAX_CATEGORY_NODES,
) -> CategoryResolution:
    """Walk ``/sites/{site_id}/categories`` iteratively and return the resolution."""
    workdir = Path(workdir)
    categories_dir = workdir / "categories"
    categories_dir.mkdir(parents=True, exist_ok=True)
    state = _WalkState()

    try:
        response = client.get_site_categories(site_id)
        root_payload = response.json()
    except IngestionError as exc:
        state.notes.append(f"failed to fetch /sites/{site_id}/categories: {exc}")
        _write_summary(workdir, state)
        return _resolution(state)

    atomic_write_json(
        workdir / "site_categories_root.json",
        sanitize_for_artifact(root_payload, token=token),
    )

    if not isinstance(root_payload, list):
        state.notes.append("site categories root was not a JSON list")
        _write_summary(workdir, state)
        return _resolution(state)

    queue: list[_Node] = [
        _Node(id=str(entry["id"]), name=str(entry.get("name", "")), depth=0)
        for entry in root_payload
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    ]

    while queue:
        node = queue.pop(0)
        if node.id in state.visited:
            continue
        if state.nodes_visited >= max_nodes:
            state.limits_exceeded = True
            state.notes.append(f"category tree walk hit MAX_CATEGORY_NODES={max_nodes}")
            break
        if node.depth > max_depth:
            state.limits_exceeded = True
            state.notes.append(f"category tree walk hit MAX_CATEGORY_DEPTH={max_depth}")
            continue

        state.visited.add(node.id)
        state.nodes_visited += 1
        state.max_depth_reached = max(state.max_depth_reached, node.depth)

        _register_candidate(state, node)

        try:
            detail_response = client.get_category(node.id)
            detail = detail_response.json()
        except IngestionError as exc:
            state.notes.append(f"failed to fetch category {node.id}: {exc}")
            continue

        atomic_write_json(
            categories_dir / f"{node.id}.json",
            sanitize_for_artifact(detail, token=token),
        )

        if not isinstance(detail, dict):
            continue

        children = detail.get("children_categories")
        if not isinstance(children, list):
            continue
        for child in children:
            if not isinstance(child, dict):
                continue
            child_id = child.get("id")
            child_name = child.get("name", "")
            if not isinstance(child_id, str) or child_id in state.visited:
                continue
            queue.append(_Node(id=child_id, name=str(child_name), depth=node.depth + 1))

    resolution = _resolution(state)
    _write_summary(workdir, state, resolution=resolution)
    return resolution


# ---- internals ---------------------------------------------------------


def _register_candidate(state: _WalkState, node: _Node) -> None:
    normalized = normalize_category_name(node.name)
    if not normalized:
        return
    for property_type, aliases in PROPERTY_TYPE_LABELS.items():
        if normalized in aliases:
            bucket = state.candidates.setdefault(property_type, [])
            if node.id not in bucket:
                bucket.append(node.id)


def _resolution(state: _WalkState) -> CategoryResolution:
    verified: dict[str, str] = {}
    ambiguous: list[str] = []
    missing: list[str] = []
    for property_type in sorted(REQUIRED_PROPERTY_TYPES):
        matches = state.candidates.get(property_type, [])
        if len(matches) == 1:
            verified[property_type] = matches[0]
        elif len(matches) > 1:
            ambiguous.append(property_type)
            state.notes.append(f"ambiguous category for {property_type}: {', '.join(matches)}")
        else:
            missing.append(property_type)
    return CategoryResolution(
        verified_category_ids=verified,
        candidates={pt: list(ids) for pt, ids in state.candidates.items()},
        nodes_visited=state.nodes_visited,
        max_depth_reached=state.max_depth_reached,
        ambiguous_property_types=ambiguous,
        missing_property_types=missing,
        limits_exceeded=state.limits_exceeded,
        notes=list(state.notes),
    )


def _write_summary(
    workdir: Path,
    state: _WalkState,
    *,
    resolution: CategoryResolution | None = None,
) -> None:
    if resolution is None:
        resolution = _resolution(state)
    atomic_write_json(workdir / "category_tree_summary.json", resolution.as_dict())


def iter_property_types() -> Iterable[str]:
    """Deterministic iteration order for the required property types."""
    return sorted(REQUIRED_PROPERTY_TYPES)
