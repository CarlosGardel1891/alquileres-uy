"""Load and expose ``build_info.json`` at runtime.

The JSON file is created by :mod:`scripts.generate_build_info` during
the build (wheel, sdist, Docker image, release workflow). At runtime,
this module resolves and parses it. Callers should not touch the file
directly — go through :func:`get_build_info`.

If the file is missing (e.g. an editable install without a build step)
we synthesise a best-effort payload from :mod:`alquileres_uy._version`
and the current Python interpreter so ``GET /build`` still responds
with a valid envelope. The synthesised payload is marked with
``git_commit == "unknown"`` and ``build_date == "unknown"`` so ops can
tell the difference from a real build.
"""

from __future__ import annotations

import json
import platform
from functools import lru_cache
from importlib.resources import files
from pathlib import Path

from .._version import __version__

_PACKAGE = "alquileres_uy"
_FILENAME = "build_info.json"

_REQUIRED_FIELDS = ("version", "git_commit", "build_date", "python_version", "api_version")


def _fallback() -> dict[str, str]:
    """Return a synthetic build_info payload when the file is missing."""
    return {
        "version": __version__,
        "git_commit": "unknown",
        "build_date": "unknown",
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "api_version": __version__,
    }


def _read_bundled() -> dict[str, str] | None:
    """Read build_info.json shipped inside the package, if present."""
    try:
        resource = files(_PACKAGE).joinpath(_FILENAME)
    except (ModuleNotFoundError, FileNotFoundError):
        return None
    try:
        if not resource.is_file():
            return None
        return json.loads(resource.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None


def _read_from_path(path: Path) -> dict[str, str] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_build_info(*, path: Path | None = None) -> dict[str, str]:
    """Load ``build_info.json`` from ``path`` (or the package resource).

    Missing / malformed files fall back to the synthesised payload so
    the endpoint never 500s just because build metadata was not baked
    into the deployment artifact.
    """
    payload: dict[str, str] | None = _read_from_path(path) if path is not None else _read_bundled()
    if payload is None:
        payload = _fallback()

    # Keep the shape stable: ensure every required field exists.
    fallback = _fallback()
    for field in _REQUIRED_FIELDS:
        payload.setdefault(field, fallback[field])
    return payload


@lru_cache(maxsize=1)
def get_build_info() -> dict[str, str]:
    """Return the process-wide cached build metadata."""
    return load_build_info()


def reset_cache() -> None:
    """Drop the cached payload (test-only)."""
    get_build_info.cache_clear()


__all__ = ["get_build_info", "load_build_info", "reset_cache"]
