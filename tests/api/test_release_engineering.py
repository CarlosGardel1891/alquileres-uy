"""Fase 10 release-engineering tests.

Covers every concern the prompt lists as validation targets:

* Single source of truth for the version (``_version.__version__``).
* CHANGELOG has a Keep-a-Changelog entry for the current version.
* ``build_info.json`` generator produces a well-formed payload.
* ``GET /build`` returns the baked-in metadata.
* ``scripts/release.py`` validates preconditions and refuses on error.
* Dockerfile carries the OCI labels and the version build-arg.
* ``release.yml`` workflow exists and fires on tags.
* Operational docs exist and cover the mandated topics.

Same no-httpx constraint as previous phases: a tiny ASGI harness
drives the app end-to-end. Every git / subprocess side-effect is
patched or scoped to a temporary directory.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI

from alquileres_uy import __version__ as PKG_VERSION
from alquileres_uy._version import __version__ as _VERSION_MODULE_VERSION
from alquileres_uy.api import build_info as build_info_module
from alquileres_uy.api.app import create_app
from alquileres_uy.api.config import ApiSettings

ROOT = Path(__file__).resolve().parents[2]
CHANGELOG = ROOT / "CHANGELOG.md"
PYPROJECT = ROOT / "pyproject.toml"
DOCKERFILE = ROOT / "Dockerfile"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
DOCS = ROOT / "docs"


# ---- minimal ASGI harness -----------------------------------------


async def _asgi_call(
    app: FastAPI,
    method: str,
    path: str,
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
    body: bytes = b"",
) -> dict:
    result: dict = {"headers": {}, "body": b""}
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers or [],
        "server": ("testserver", 80),
        "client": ("testclient", 12345),
        "app": app,
    }
    sent = [False]

    async def _receive():
        if not sent[0]:
            sent[0] = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def _send(message):
        if message["type"] == "http.response.start":
            result["status"] = message["status"]
            result["headers"] = {k.decode(): v.decode() for k, v in message.get("headers", [])}
        elif message["type"] == "http.response.body":
            result["body"] += message.get("body", b"")

    @asynccontextmanager
    async def _lifespan_ctx():
        async with app.router.lifespan_context(app):
            yield

    async with _lifespan_ctx():
        try:
            await app(scope, _receive, _send)
        except Exception:
            if "status" not in result:
                raise
    return result


# ---- version single source of truth ------------------------------


def test_version_is_valid_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", PKG_VERSION)


def test_package_version_matches_version_module():
    assert PKG_VERSION == _VERSION_MODULE_VERSION


def test_api_settings_default_version_matches_package():
    assert ApiSettings().APP_VERSION == PKG_VERSION


def test_pyproject_uses_dynamic_version_from_version_module():
    text = PYPROJECT.read_text(encoding="utf-8")
    assert 'dynamic = ["version"]' in text
    assert "alquileres_uy._version.__version__" in text
    # No hard-coded `version = "..."` line lingering in the [project] table.
    assert not re.search(r'^\s*version\s*=\s*"\d', text, flags=re.MULTILINE)


def test_installed_metadata_matches_version_module():
    """``importlib.metadata`` sees the same version once the wheel is installed.

    Editable installs won't necessarily refresh metadata across a bump,
    so this test only enforces equality when metadata is available at
    all — otherwise it is a soft skip.
    """
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:  # pragma: no cover
        pytest.skip("importlib.metadata unavailable")
    try:
        meta_version = version("alquileres-uy")
    except PackageNotFoundError:
        pytest.skip("alquileres-uy not installed as a distribution")
    assert meta_version == PKG_VERSION


# ---- CHANGELOG ---------------------------------------------------


def test_changelog_exists_and_lists_current_version():
    assert CHANGELOG.is_file()
    text = CHANGELOG.read_text(encoding="utf-8")
    assert "# Changelog" in text
    assert "Keep a Changelog" in text
    assert f"## [{PKG_VERSION}]" in text


def test_changelog_covers_previous_phases():
    text = CHANGELOG.read_text(encoding="utf-8")
    # Every previously-shipped phase must show up as a heading.
    for phase in ("0.9.0", "0.8.0", "0.7.0", "0.6.0", "0.5.0", "0.4.0", "0.3.0", "0.2.0", "0.1.0"):
        assert f"## [{phase}]" in text, f"missing entry for {phase}"


def test_changelog_has_unreleased_placeholder():
    text = CHANGELOG.read_text(encoding="utf-8")
    assert "## [Unreleased]" in text


# ---- build_info.json --------------------------------------------


REQUIRED_BUILD_INFO_FIELDS = (
    "version",
    "git_commit",
    "build_date",
    "python_version",
    "platform",
    "api_version",
)


def test_generate_build_info_produces_all_fields(tmp_path, monkeypatch):
    from scripts import generate_build_info

    destination = tmp_path / "build_info.json"
    generate_build_info.write_build_info(destination)

    payload = json.loads(destination.read_text(encoding="utf-8"))
    for field in REQUIRED_BUILD_INFO_FIELDS:
        assert field in payload
    assert payload["version"] == PKG_VERSION
    assert payload["api_version"] == PKG_VERSION
    # git_commit either resolves to a hex prefix or reports "unknown".
    assert payload["git_commit"] == "unknown" or re.fullmatch(r"[0-9a-f]+", payload["git_commit"])


def test_generate_build_info_iso_date_format(tmp_path):
    from scripts import generate_build_info

    destination = tmp_path / "build_info.json"
    generate_build_info.write_build_info(destination)

    payload = json.loads(destination.read_text(encoding="utf-8"))
    # ISO 8601 UTC to the second.
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", payload["build_date"])


def test_generate_build_info_git_unknown_when_git_missing(tmp_path, monkeypatch):
    from scripts import generate_build_info

    def _fake_run(*args, **kwargs):
        raise FileNotFoundError("git not installed")

    monkeypatch.setattr(generate_build_info.subprocess, "run", _fake_run)
    payload = generate_build_info.build_info(repo_root=tmp_path)
    assert payload["git_commit"] == "unknown"


def test_bundled_build_info_file_exists_and_is_valid():
    bundled = ROOT / "src" / "alquileres_uy" / "build_info.json"
    assert bundled.is_file(), "run `python scripts/generate_build_info.py`"
    payload = json.loads(bundled.read_text(encoding="utf-8"))
    assert payload["version"] == PKG_VERSION


def test_build_info_loader_falls_back_when_missing(tmp_path, monkeypatch):
    build_info_module.reset_cache()
    payload = build_info_module.load_build_info(path=tmp_path / "nope.json")
    for field in ("version", "git_commit", "build_date", "python_version", "api_version"):
        assert field in payload
    assert payload["version"] == PKG_VERSION
    assert payload["git_commit"] == "unknown"


def test_build_info_loader_returns_file_contents(tmp_path):
    build_info_module.reset_cache()
    path = tmp_path / "build_info.json"
    path.write_text(
        json.dumps(
            {
                "version": "1.2.3",
                "git_commit": "abcdef",
                "build_date": "2026-08-08T12:00:00+00:00",
                "python_version": "3.12.1",
                "platform": "Linux",
                "api_version": "1.2.3",
            }
        ),
        encoding="utf-8",
    )
    payload = build_info_module.load_build_info(path=path)
    assert payload["version"] == "1.2.3"
    assert payload["git_commit"] == "abcdef"


# ---- GET /build endpoint ----------------------------------------


def test_build_endpoint_returns_build_info(api_env):
    build_info_module.reset_cache()
    app = create_app()
    result = asyncio.run(_asgi_call(app, "GET", "/build"))
    assert result["status"] == 200
    payload = json.loads(result["body"])
    for field in ("version", "git_commit", "build_date", "python_version", "api_version"):
        assert field in payload
    assert payload["version"] == PKG_VERSION
    assert payload["api_version"] == PKG_VERSION


def test_build_endpoint_shape_stable_even_without_bundled_file(api_env, monkeypatch):
    build_info_module.reset_cache()
    monkeypatch.setattr(build_info_module, "_read_bundled", lambda: None)
    app = create_app()
    result = asyncio.run(_asgi_call(app, "GET", "/build"))
    assert result["status"] == 200
    payload = json.loads(result["body"])
    # Shape does not change when the file is missing — every field is present.
    for field in ("version", "git_commit", "build_date", "python_version", "api_version"):
        assert field in payload


# ---- scripts/release.py -----------------------------------------


def test_release_script_suggest_next_versions():
    from scripts import release

    assert release.suggest_next_versions("0.10.0") == {
        "patch": "0.10.1",
        "minor": "0.11.0",
        "major": "1.0.0",
    }


def test_release_script_refuses_non_semver():
    from scripts import release

    with pytest.raises(release.ReleaseError):
        release.suggest_next_versions("not-semver")


def test_release_script_refuses_dirty_tree(monkeypatch):
    from scripts import release

    def _fake_run(cmd, *, cwd=None):
        return subprocess.CompletedProcess(cmd, 0, stdout="?? junk.txt\n", stderr="")

    monkeypatch.setattr(release, "_run", _fake_run)
    with pytest.raises(release.ReleaseError, match="dirty"):
        release.check_clean_tree()


def test_release_script_accepts_clean_tree(monkeypatch):
    from scripts import release

    def _fake_run(cmd, *, cwd=None):
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(release, "_run", _fake_run)
    release.check_clean_tree()  # no raise


def test_release_script_refuses_non_main_branch(monkeypatch):
    from scripts import release

    def _fake_run(cmd, *, cwd=None):
        return subprocess.CompletedProcess(cmd, 0, stdout="feature/other\n", stderr="")

    monkeypatch.setattr(release, "_run", _fake_run)
    with pytest.raises(release.ReleaseError, match="branch"):
        release.check_branch(allow_branch=False)


def test_release_script_allows_non_main_branch_with_override(monkeypatch):
    from scripts import release

    def _fake_run(cmd, *, cwd=None):
        return subprocess.CompletedProcess(cmd, 0, stdout="feature/x\n", stderr="")

    monkeypatch.setattr(release, "_run", _fake_run)
    assert release.check_branch(allow_branch=True) == "feature/x"


def test_release_script_check_changelog(tmp_path):
    from scripts import release

    path = tmp_path / "CHANGELOG.md"
    path.write_text("# Changelog\n\n## [1.2.3] — 2026-01-01\n- something\n", encoding="utf-8")
    release.check_changelog("1.2.3", path=path)
    with pytest.raises(release.ReleaseError, match="no section"):
        release.check_changelog("9.9.9", path=path)


def test_release_script_check_changelog_missing_file(tmp_path):
    from scripts import release

    with pytest.raises(release.ReleaseError, match="missing"):
        release.check_changelog("1.0.0", path=tmp_path / "nope.md")


def test_release_script_main_reports_error_on_dirty_tree(monkeypatch, capsys):
    from scripts import release

    def _fake_run(cmd, *, cwd=None):
        if cmd[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=" M file\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="main\n", stderr="")

    monkeypatch.setattr(release, "_run", _fake_run)
    exit_code = release.main(["--skip-tests", "--no-tag"])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "dirty" in captured.err.lower()


def test_release_script_main_happy_path(monkeypatch, capsys, tmp_path):
    from scripts import release

    fake_changelog = tmp_path / "CHANGELOG.md"
    fake_changelog.write_text(
        f"# Changelog\n\n## [{PKG_VERSION}] — 2026-08-08\n- initial\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(release, "CHANGELOG", fake_changelog)

    calls = []

    def _fake_run(cmd, *, cwd=None):
        calls.append(cmd)
        if cmd[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="main\n", stderr="")
        if cmd[:2] == ["git", "tag"] and cmd[2:3] == ["-l"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:2] == ["git", "tag"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(release, "_run", _fake_run)

    exit_code = release.main(["--skip-tests"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"v{PKG_VERSION}" in captured.out
    assert "suggested next versions" in captured.out


def test_release_script_tag_creation_refuses_existing_tag(monkeypatch):
    from scripts import release

    def _fake_run(cmd, *, cwd=None):
        if cmd[:3] == ["git", "tag", "-l"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="v0.10.0\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(release, "_run", _fake_run)
    with pytest.raises(release.ReleaseError, match="already exists"):
        release.create_tag("0.10.0")


# ---- Dockerfile OCI labels --------------------------------------


def test_dockerfile_declares_app_version_arg():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(r"^ARG\s+APP_VERSION=", text, flags=re.MULTILINE)


def test_dockerfile_declares_all_oci_labels():
    text = DOCKERFILE.read_text(encoding="utf-8")
    for label in (
        "org.opencontainers.image.version",
        "org.opencontainers.image.source",
        "org.opencontainers.image.description",
        "org.opencontainers.image.licenses",
    ):
        assert label in text, f"Dockerfile missing OCI label {label}"


def test_dockerfile_version_label_uses_build_arg():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert 'org.opencontainers.image.version="${APP_VERSION}"' in text


def test_dockerfile_generates_build_info_in_image():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "scripts/generate_build_info.py" in text


# ---- release.yml workflow ---------------------------------------


def test_release_workflow_exists_and_fires_on_v_tags():
    assert RELEASE_WORKFLOW.is_file()
    text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    # Fires on tag push matching v*.
    assert re.search(r"^on:\s*\n\s*push:\s*\n\s*tags:", text, flags=re.MULTILINE)
    assert '- "v*"' in text


def test_release_workflow_builds_wheel_sdist_docker_and_creates_release():
    text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    assert "python -m build" in text
    assert "docker/build-push-action" in text
    assert "softprops/action-gh-release" in text
    assert "APP_VERSION=" in text
    assert "push: false" in text  # do not publish images


def test_release_workflow_extracts_notes_from_changelog():
    text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    assert "CHANGELOG.md" in text
    assert "release_notes.md" in text


# ---- ci.yml release-check job -----------------------------------


def test_ci_workflow_has_release_check_job():
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    assert re.search(r"^\s{2}release-check:", text, flags=re.MULTILINE)
    # The release-check job must exercise every validation the prompt lists.
    for keyword in (
        "CHANGELOG",
        "generate_build_info",
        "python -m build",
        "docker/build-push-action",
        "org.opencontainers.image.version",
    ):
        assert keyword in text, f"release-check job missing {keyword}"


def test_ci_workflow_keeps_all_previous_jobs():
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    for job in ("quality-and-classical", "pytorch-cpu", "docker-build", "release-check"):
        assert re.search(
            rf"^\s{{2}}{re.escape(job)}:", text, flags=re.MULTILINE
        ), f"CI missing job {job}"


# ---- operational docs -------------------------------------------


@pytest.mark.parametrize(
    "filename,required_keywords",
    [
        (
            "deployment.md",
            (
                "Environment variables",
                "Docker",
                "Startup sequence",
                "Shutdown sequence",
                "/health",
                "/ready",
                "/metrics",
                "ALQUILERES_API_",
            ),
        ),
        (
            "operations.md",
            (
                "Logs",
                "Prometheus",
                "warmup",
                "Timeouts",
                "Benchmark",
                "Smoke",
            ),
        ),
        (
            "upgrade.md",
            (
                "bundle",
                "compatibility",
                "Rollback",
                "Versioning",
            ),
        ),
    ],
)
def test_operational_docs_cover_required_topics(filename, required_keywords):
    path = DOCS / filename
    assert path.is_file(), f"missing operational doc {filename}"
    text = path.read_text(encoding="utf-8")
    for keyword in required_keywords:
        assert keyword in text, f"{filename} missing keyword {keyword!r}"


# ---- smoke: release script + generate_build_info as CLI ---------


def test_release_script_cli_help_runs():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "release.py"), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "release" in result.stdout.lower()


def test_generate_build_info_cli_writes_file(tmp_path):
    dest = tmp_path / "bi.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "generate_build_info.py"),
            "--output",
            str(dest),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    payload = json.loads(dest.read_text(encoding="utf-8"))
    assert payload["version"] == PKG_VERSION
