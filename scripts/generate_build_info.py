"""Emit ``src/alquileres_uy/build_info.json`` from the current build.

The endpoint ``GET /build`` reads this file at runtime, so the file is
authoritative. All values are derived from the environment; nothing is
hard-coded.

Usage::

    python scripts/generate_build_info.py

or overriding the destination::

    python scripts/generate_build_info.py --output build_info.json

The script is stdlib-only so it can run inside the Docker build layer
without pulling requirements.

Fields
------

* ``version``            — the package version from
                           :mod:`alquileres_uy._version`.
* ``git_commit``         — short SHA reported by ``git rev-parse``.
                           Falls back to ``"unknown"`` if git is
                           unavailable (source tarball, container
                           without ``.git``, etc.).
* ``build_date``         — ISO-8601 UTC timestamp captured at run time.
* ``python_version``     — ``python_version()`` result at build time.
* ``platform``           — ``platform.platform()`` at build time.
* ``api_version``        — same as ``version``; kept as a distinct
                           field so an operator can eyeball parity
                           with the ``/version`` endpoint.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure the src layout is importable when running from a checkout.
_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:  # pragma: no cover - trivial import shim
    sys.path.insert(0, str(_SRC))

from alquileres_uy._version import __version__  # noqa: E402 - after path fix

DEFAULT_OUTPUT = _SRC / "alquileres_uy" / "build_info.json"


def _git_commit(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--short=12", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ):
        return "unknown"
    return completed.stdout.strip() or "unknown"


def build_info(*, repo_root: Path | None = None, now: datetime | None = None) -> dict[str, str]:
    """Compute the build metadata dict without touching disk."""
    root = repo_root or _ROOT
    ts = now or datetime.now(tz=UTC)
    return {
        "version": __version__,
        "git_commit": _git_commit(root),
        "build_date": ts.replace(microsecond=0).isoformat(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "api_version": __version__,
    }


def write_build_info(destination: Path, *, info: dict[str, str] | None = None) -> Path:
    """Serialize ``info`` to ``destination`` and return the path."""
    payload = info if info is not None else build_info()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="destination file (default: %(default)s)",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="also echo the JSON payload to stdout",
    )
    args = parser.parse_args(argv)

    info = build_info()
    destination = write_build_info(args.output, info=info)
    if args.print:
        print(json.dumps(info, indent=2, sort_keys=True))
    print(f"wrote {destination}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
