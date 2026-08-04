"""Tests for :mod:`alquileres_uy.ingest.category_tree`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from alquileres_uy.ingest.category_tree import (
    MAX_CATEGORY_DEPTH,
    MAX_CATEGORY_NODES,
    normalize_category_name,
    resolve_category_tree,
)

from .conftest import FakeResponse


class _TreeClient:
    """Stub client that plays back a canned category tree.

    ``site_root`` is the list returned by ``/sites/MLU/categories``.
    ``details`` maps ``category_id`` to the payload returned by
    ``/categories/{id}`` (including ``children_categories`` when the
    node has descendants).
    """

    def __init__(
        self,
        site_root: list[dict[str, Any]],
        details: dict[str, dict[str, Any]],
    ) -> None:
        self._site_root = site_root
        self._details = details
        self.get_category_calls: list[str] = []
        self.get_site_categories_calls: int = 0

    def get_site_categories(self, site_id: str) -> FakeResponse:
        self.get_site_categories_calls += 1
        return FakeResponse(json_data=self._site_root)

    def get_category(self, category_id: str) -> FakeResponse:
        self.get_category_calls.append(category_id)
        return FakeResponse(
            json_data=self._details.get(category_id, {"id": category_id, "name": category_id})
        )


def test_normalize_lowercases_strips_and_removes_diacritics():
    assert normalize_category_name("  Cásás  ") == "casas"
    assert normalize_category_name("Apartamentos") == "apartamentos"
    assert normalize_category_name("  APARTMENTS ") == "apartments"


def test_normalize_collapses_internal_whitespace():
    assert normalize_category_name("propiedades   y   apartamentos") == (
        "propiedades y apartamentos"
    )


def test_normalize_returns_empty_for_non_string():
    assert normalize_category_name(123) == ""  # type: ignore[arg-type]


def test_substring_does_not_produce_false_match(tmp_path: Path):
    client = _TreeClient(
        site_root=[
            {"id": "MLU_ROOT", "name": "Propiedades y Apartamentos"},
        ],
        details={"MLU_ROOT": {"id": "MLU_ROOT", "name": "Propiedades y Apartamentos"}},
    )
    resolution = resolve_category_tree(client, "MLU", tmp_path)
    # 'propiedades y apartamentos' is not in the alias set for apartment
    assert resolution.verified_category_ids == {}
    assert set(resolution.missing_property_types) == {"apartment", "house"}


def test_apartment_and_house_at_root(tmp_path: Path):
    client = _TreeClient(
        site_root=[
            {"id": "MLU_APT", "name": "Apartamentos"},
            {"id": "MLU_HOUSE", "name": "Casas"},
        ],
        details={
            "MLU_APT": {"id": "MLU_APT", "name": "Apartamentos"},
            "MLU_HOUSE": {"id": "MLU_HOUSE", "name": "Casas"},
        },
    )
    resolution = resolve_category_tree(client, "MLU", tmp_path)
    assert resolution.verified_category_ids == {
        "apartment": "MLU_APT",
        "house": "MLU_HOUSE",
    }
    assert resolution.missing_property_types == []
    assert resolution.ambiguous_property_types == []


def test_apartment_found_at_depth_two(tmp_path: Path):
    client = _TreeClient(
        site_root=[{"id": "MLU_ROOT", "name": "Inmuebles"}],
        details={
            "MLU_ROOT": {
                "id": "MLU_ROOT",
                "name": "Inmuebles",
                "children_categories": [
                    {"id": "MLU_APT", "name": "Apartamentos"},
                    {"id": "MLU_HOUSE", "name": "Casas"},
                ],
            },
            "MLU_APT": {"id": "MLU_APT", "name": "Apartamentos"},
            "MLU_HOUSE": {"id": "MLU_HOUSE", "name": "Casas"},
        },
    )
    resolution = resolve_category_tree(client, "MLU", tmp_path)
    assert resolution.verified_category_ids == {
        "apartment": "MLU_APT",
        "house": "MLU_HOUSE",
    }
    assert resolution.max_depth_reached == 1


def test_house_at_depth_three_via_intermediate_branch(tmp_path: Path):
    client = _TreeClient(
        site_root=[{"id": "MLU_R", "name": "Inmuebles"}],
        details={
            "MLU_R": {
                "id": "MLU_R",
                "name": "Inmuebles",
                "children_categories": [
                    {"id": "MLU_M1", "name": "Residencial"},
                    {"id": "MLU_APT", "name": "Apartamentos"},
                ],
            },
            "MLU_M1": {
                "id": "MLU_M1",
                "name": "Residencial",
                "children_categories": [{"id": "MLU_H1", "name": "Unifamiliares"}],
            },
            "MLU_H1": {
                "id": "MLU_H1",
                "name": "Unifamiliares",
                "children_categories": [{"id": "MLU_HOUSE", "name": "Casas"}],
            },
            "MLU_HOUSE": {"id": "MLU_HOUSE", "name": "Casas"},
            "MLU_APT": {"id": "MLU_APT", "name": "Apartamentos"},
        },
    )
    resolution = resolve_category_tree(client, "MLU", tmp_path)
    assert resolution.verified_category_ids == {
        "apartment": "MLU_APT",
        "house": "MLU_HOUSE",
    }
    assert resolution.max_depth_reached >= 3


def test_visited_set_prevents_duplicate_calls(tmp_path: Path):
    client = _TreeClient(
        site_root=[{"id": "MLU_R", "name": "Inmuebles"}, {"id": "MLU_R", "name": "Duplicado"}],
        details={
            "MLU_R": {"id": "MLU_R", "name": "Inmuebles"},
        },
    )
    resolve_category_tree(client, "MLU", tmp_path)
    assert client.get_category_calls.count("MLU_R") == 1


def test_cycle_between_children_terminates(tmp_path: Path):
    client = _TreeClient(
        site_root=[{"id": "A", "name": "Inmuebles"}],
        details={
            "A": {
                "id": "A",
                "name": "Inmuebles",
                "children_categories": [{"id": "B", "name": "x"}],
            },
            "B": {
                "id": "B",
                "name": "x",
                "children_categories": [{"id": "A", "name": "Inmuebles"}],
            },
        },
    )
    resolution = resolve_category_tree(client, "MLU", tmp_path)
    assert resolution.nodes_visited <= 2
    # A and B each visited once; the cycle A→B→A is broken by the visited set.


def test_max_depth_is_respected(tmp_path: Path):
    # Chain of nodes, each pointing to a deeper child.
    details: dict[str, dict[str, Any]] = {}
    for depth in range(MAX_CATEGORY_DEPTH + 5):
        details[f"N{depth}"] = {
            "id": f"N{depth}",
            "name": f"n{depth}",
            "children_categories": [{"id": f"N{depth + 1}", "name": f"n{depth + 1}"}],
        }
    client = _TreeClient(site_root=[{"id": "N0", "name": "n0"}], details=details)
    resolution = resolve_category_tree(client, "MLU", tmp_path, max_depth=3)
    assert resolution.limits_exceeded is True
    assert resolution.max_depth_reached <= 3


def test_max_nodes_is_respected(tmp_path: Path):
    site_root = [{"id": f"N{i}", "name": f"n{i}"} for i in range(50)]
    details = {f"N{i}": {"id": f"N{i}", "name": f"n{i}"} for i in range(50)}
    client = _TreeClient(site_root=site_root, details=details)
    resolution = resolve_category_tree(client, "MLU", tmp_path, max_nodes=10)
    assert resolution.limits_exceeded is True
    assert resolution.nodes_visited == 10


def test_ambiguous_apartment_forces_two_candidates(tmp_path: Path):
    client = _TreeClient(
        site_root=[
            {"id": "MLU_A1", "name": "Apartamentos"},
            {"id": "MLU_A2", "name": "Apartamento"},
            {"id": "MLU_HOUSE", "name": "Casas"},
        ],
        details={
            "MLU_A1": {"id": "MLU_A1", "name": "Apartamentos"},
            "MLU_A2": {"id": "MLU_A2", "name": "Apartamento"},
            "MLU_HOUSE": {"id": "MLU_HOUSE", "name": "Casas"},
        },
    )
    resolution = resolve_category_tree(client, "MLU", tmp_path)
    assert resolution.ambiguous_property_types == ["apartment"]
    assert set(resolution.candidates["apartment"]) == {"MLU_A1", "MLU_A2"}
    assert "apartment" not in resolution.verified_category_ids


def test_missing_apartment_reports_it(tmp_path: Path):
    client = _TreeClient(
        site_root=[{"id": "MLU_HOUSE", "name": "Casas"}],
        details={"MLU_HOUSE": {"id": "MLU_HOUSE", "name": "Casas"}},
    )
    resolution = resolve_category_tree(client, "MLU", tmp_path)
    assert resolution.missing_property_types == ["apartment"]


def test_missing_house_reports_it(tmp_path: Path):
    client = _TreeClient(
        site_root=[{"id": "MLU_APT", "name": "Apartamentos"}],
        details={"MLU_APT": {"id": "MLU_APT", "name": "Apartamentos"}},
    )
    resolution = resolve_category_tree(client, "MLU", tmp_path)
    assert resolution.missing_property_types == ["house"]


def test_files_are_persisted_per_category(tmp_path: Path):
    client = _TreeClient(
        site_root=[
            {"id": "MLU_APT", "name": "Apartamentos"},
            {"id": "MLU_HOUSE", "name": "Casas"},
        ],
        details={
            "MLU_APT": {"id": "MLU_APT", "name": "Apartamentos"},
            "MLU_HOUSE": {"id": "MLU_HOUSE", "name": "Casas"},
        },
    )
    resolve_category_tree(client, "MLU", tmp_path)
    assert (tmp_path / "site_categories_root.json").is_file()
    assert (tmp_path / "category_tree_summary.json").is_file()
    assert (tmp_path / "categories" / "MLU_APT.json").is_file()
    assert (tmp_path / "categories" / "MLU_HOUSE.json").is_file()


def test_token_never_appears_in_persisted_files(tmp_path: Path):
    token = "very-secret-token"
    client = _TreeClient(
        site_root=[
            {"id": "MLU_APT", "name": "Apartamentos", "note": f"contains {token}"},
        ],
        details={
            "MLU_APT": {
                "id": "MLU_APT",
                "name": "Apartamentos",
                "leaked_authorization": f"Bearer {token}",
            }
        },
    )
    resolve_category_tree(client, "MLU", tmp_path, token=token)
    for path in [
        tmp_path / "site_categories_root.json",
        tmp_path / "categories" / "MLU_APT.json",
    ]:
        text = path.read_text(encoding="utf-8")
        assert token not in text, f"token leaked into {path}"


def test_summary_serializes_expected_fields(tmp_path: Path):
    client = _TreeClient(
        site_root=[
            {"id": "MLU_APT", "name": "Apartamentos"},
            {"id": "MLU_HOUSE", "name": "Casas"},
        ],
        details={
            "MLU_APT": {"id": "MLU_APT", "name": "Apartamentos"},
            "MLU_HOUSE": {"id": "MLU_HOUSE", "name": "Casas"},
        },
    )
    resolve_category_tree(client, "MLU", tmp_path)
    summary = json.loads((tmp_path / "category_tree_summary.json").read_text(encoding="utf-8"))
    assert summary["nodes_visited"] == 2
    assert summary["required_categories"]["apartment"] == {
        "status": "verified",
        "category_id": "MLU_APT",
    }
    assert summary["required_categories"]["house"]["status"] == "verified"
    assert summary["limits_exceeded"] is False


def test_default_limits_are_enforced_but_leave_headroom():
    # Sanity: constants are reasonable defaults.
    assert MAX_CATEGORY_DEPTH >= 3
    assert MAX_CATEGORY_NODES >= 20
