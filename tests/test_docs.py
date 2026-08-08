"""Fase 14 — project-finalization tests.

These tests validate that the portfolio-level documentation exists,
covers the topics the prompt mandates, and stays in sync with the
codebase (badges, version, licenses, project tree). They intentionally
do NOT touch existing behaviour — every assertion is over static
markdown / LICENSE / generated files.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
README = ROOT / "README.md"
LICENSE_FILE = ROOT / "LICENSE"
CONTRIBUTING = ROOT / "CONTRIBUTING.md"
CHANGELOG = ROOT / "CHANGELOG.md"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing file: {path}"
    return path.read_text(encoding="utf-8")


# ---- README ------------------------------------------------------


def test_readme_has_all_top_level_sections():
    text = _read(README)
    required_headings = [
        "# alquileres-uy",
        "## Problema",
        "## Objetivo",
        "## Arquitectura",
        "## Stack",
        "## Capturas",
        "## Quick Start",
        "## Docker",
        "## Docker Compose",
        "## Variables de entorno",
        "## Entrenamiento",
        "## API",
        "## Frontend",
        "## Observabilidad",
        "## Testing",
        "## CI",
        "## Release",
        "## Roadmap",
        "## Licencia",
    ]
    for heading in required_headings:
        assert heading in text, f"README missing heading: {heading}"


def test_readme_includes_badges():
    text = _read(README)
    for badge in (
        "python-3.12",
        "fastapi-",
        "docker",
        "CI-",
        "license",
        "version-",
    ):
        assert badge.lower() in text.lower(), f"README missing badge: {badge}"


def test_readme_badges_use_shields_io():
    text = _read(README)
    matches = re.findall(r"!\[[^\]]+\]\(https://img\.shields\.io/[^\)]+\)", text)
    assert len(matches) >= 5, "expected at least 5 shields.io badges"


def test_readme_links_to_docs():
    text = _read(README)
    for link in (
        "docs/architecture.md",
        "docs/api.md",
        "docs/portfolio.md",
        "docs/demo.md",
        "docs/deployment.md",
        "docs/operations.md",
        "docs/upgrade.md",
        "docs/project-tree.md",
        "CONTRIBUTING.md",
        "CHANGELOG.md",
        "LICENSE",
    ):
        assert link in text, f"README missing link to {link}"


def test_readme_mentions_current_version():
    import alquileres_uy

    version = alquileres_uy.__version__
    text = _read(README)
    assert version in text, f"README does not mention current version {version}"


def test_readme_documents_env_var_prefix():
    text = _read(README)
    assert "ALQUILERES_API_" in text
    for var in (
        "ALQUILERES_API_MODEL_BUNDLE_PATH",
        "ALQUILERES_API_MAX_CONCURRENT_PREDICTIONS",
        "ALQUILERES_API_PREDICT_TIMEOUT",
    ):
        assert var in text, f"README missing env var {var}"


# ---- architecture.md --------------------------------------------


def test_architecture_doc_exists_and_covers_layers():
    text = _read(DOCS / "architecture.md")
    for section in (
        "Visión general",
        "Flujo de datos",
        "Ingesta",
        "ETL",
        "Entrenamiento",
        "Serving",
        "Frontend",
        "Observabilidad",
    ):
        assert section in text, f"architecture.md missing section: {section}"


def test_architecture_uses_mermaid_diagrams():
    text = _read(DOCS / "architecture.md")
    # At least 4 Mermaid diagrams — one per layer of interest.
    matches = re.findall(r"```mermaid[\s\S]+?```", text)
    assert len(matches) >= 4, f"expected ≥4 mermaid diagrams, got {len(matches)}"


# ---- api.md -----------------------------------------------------


def test_api_doc_covers_every_endpoint():
    text = _read(DOCS / "api.md")
    for endpoint in (
        "GET /health",
        "GET /ready",
        "GET /version",
        "GET /build",
        "GET /metrics",
        "POST /predict",
    ):
        assert endpoint in text, f"api.md missing endpoint: {endpoint}"


def test_api_doc_includes_request_and_response_examples():
    text = _read(DOCS / "api.md")
    assert "Response 200" in text
    # 4xx / 5xx examples are documented.
    for status in ("422", "500", "503"):
        assert status in text
    # JSON blocks for request + response.
    json_blocks = re.findall(r"```json[\s\S]+?```", text)
    assert len(json_blocks) >= 6, f"expected ≥6 JSON blocks, got {len(json_blocks)}"


def test_api_doc_documents_error_envelope():
    text = _read(DOCS / "api.md")
    assert "envelope" in text.lower() or "Envelope" in text
    assert '"error"' in text
    assert '"code"' in text
    assert '"message"' in text


def test_api_doc_lists_documented_error_codes():
    text = _read(DOCS / "api.md")
    for code in ("prediction_timeout", "service_unavailable", "validation_error"):
        assert code in text, f"api.md missing error code {code}"


# ---- portfolio.md -----------------------------------------------


def test_portfolio_doc_exists_and_covers_prompt_bullets():
    text = _read(DOCS / "portfolio.md")
    for section in (
        "problema",
        "decisiones",
        "desafíos",
        "aprendizajes",
        "arquitectura",
        "métricas",
        "tecnologías",
    ):
        assert section in text.lower(), f"portfolio.md missing section: {section}"


def test_portfolio_lists_decisions_and_trade_offs():
    text = _read(DOCS / "portfolio.md")
    for keyword in ("PredictionService", "tune-then-refit", "minimum_api_version"):
        assert keyword in text, f"portfolio.md missing decision: {keyword}"


# ---- demo.md ----------------------------------------------------


def test_demo_doc_exists_and_covers_video_recipe():
    text = _read(DOCS / "demo.md")
    for section in ("Duración", "Preparación", "Guión", "checklist"):
        assert section.lower() in text.lower(), f"demo.md missing section: {section}"
    # Suggests a target duration.
    assert re.search(r"\d+\s*(?:min|minutos?)", text)


def test_demo_doc_recommends_recording_order():
    text = _read(DOCS / "demo.md")
    # Numbered steps.
    assert re.search(r"###\s+\d+\.", text)


# ---- CONTRIBUTING.md --------------------------------------------


def test_contributing_covers_setup_and_workflow():
    text = _read(CONTRIBUTING)
    for section in (
        "Levantar el proyecto",
        "Ramas",
        "Commits",
        "Pull requests",
        "Tests",
        "Estilo",
    ):
        assert section in text, f"CONTRIBUTING missing section: {section}"


def test_contributing_mentions_no_httpx_constraint():
    text = _read(CONTRIBUTING)
    assert "httpx" in text
    assert "TestClient" in text


# ---- LICENSE ----------------------------------------------------


def test_license_is_mit_and_has_copyright_holder():
    text = _read(LICENSE_FILE)
    assert "MIT License" in text
    assert "Copyright (c)" in text
    assert "Martin Castaldi" in text
    # Canonical MIT clauses.
    assert "Permission is hereby granted" in text
    assert 'THE SOFTWARE IS PROVIDED "AS IS"' in text


# ---- CHANGELOG links -------------------------------------------


def test_changelog_still_valid_keep_a_changelog_format():
    text = _read(CHANGELOG)
    assert "# Changelog" in text
    assert "Keep a Changelog" in text
    assert "## [Unreleased]" in text


# ---- project-tree.md -------------------------------------------


def test_project_tree_exists_and_has_expected_shape():
    path = DOCS / "project-tree.md"
    text = _read(path)
    assert "# Project tree" in text
    assert "```" in text
    assert "alquileres-uy/" in text
    # Excluded names appear in the docstring / prose but not in the code fence.
    fence_match = re.search(r"```\n(alquileres-uy/[\s\S]+?)```", text)
    assert fence_match, "no code fence with tree found"
    tree = fence_match.group(1)
    for banned in ("__pycache__", "/.venv/", "/artifacts/", "/data/"):
        assert banned not in tree, f"tree should not include {banned}"


def test_project_tree_generator_script_runs_and_writes_file(tmp_path):
    dest = tmp_path / "tree.md"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "generate_project_tree.py"),
            "--output",
            str(dest),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert dest.is_file()
    generated = dest.read_text(encoding="utf-8")
    assert "# Project tree" in generated
    assert "alquileres-uy/" in generated


def test_project_tree_generator_help_runs():
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "generate_project_tree.py"),
            "--help",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "project" in result.stdout.lower()


# ---- generator internals ---------------------------------------


def test_generator_module_excludes_the_mandated_paths():
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import generate_project_tree
    finally:
        sys.path.pop(0)
    for name in ("__pycache__", ".venv", ".git", "data", "artifacts"):
        assert name in generate_project_tree.EXCLUDED_NAMES, f"missing exclusion: {name}"


@pytest.mark.parametrize(
    "path",
    [
        DOCS / "architecture.md",
        DOCS / "api.md",
        DOCS / "portfolio.md",
        DOCS / "demo.md",
        DOCS / "project-tree.md",
        CONTRIBUTING,
        LICENSE_FILE,
    ],
)
def test_documentation_artifacts_are_non_empty(path):
    text = _read(path)
    assert len(text) > 500, f"{path.name} is suspiciously short"
