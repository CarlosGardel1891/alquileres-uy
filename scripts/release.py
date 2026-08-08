"""Cut a release: validate -> test -> changelog stub -> tag -> suggest next.

Stdlib only. Never pushes. Never touches remote APIs. Every side-effect
is local and reversible by ``git tag -d`` or a ``git reset``.

Steps
-----

1. Refuse if the working tree is dirty (``git status --porcelain``).
2. Refuse if the current branch is not ``main`` unless ``--allow-branch``
   is passed.
3. Run the fast test suite (``pytest -q -m "not torch"``) unless
   ``--skip-tests`` is passed.
4. Confirm ``CHANGELOG.md`` has an entry for the current version.
5. Optionally regenerate ``build_info.json``.
6. Create the annotated tag ``v<version>`` unless ``--no-tag`` is
   passed.
7. Print the suggested next-version bumps (patch / minor / major).

Never pushes — the operator must run ``git push origin main --tags``
themselves.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_SRC))

from alquileres_uy._version import __version__  # noqa: E402 - after path fix

CHANGELOG = _ROOT / "CHANGELOG.md"


class ReleaseError(RuntimeError):
    """Recoverable release-precondition failure."""


def _run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd or _ROOT),
        check=False,
        capture_output=True,
        text=True,
    )


def check_clean_tree() -> None:
    result = _run(["git", "status", "--porcelain"])
    if result.returncode != 0:
        raise ReleaseError(f"git status failed: {result.stderr.strip()}")
    if result.stdout.strip():
        raise ReleaseError(
            "working tree is dirty — commit or stash before releasing:\n" + result.stdout.rstrip()
        )


def check_branch(*, allow_branch: bool) -> str:
    result = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if result.returncode != 0:
        raise ReleaseError(f"git rev-parse failed: {result.stderr.strip()}")
    branch = result.stdout.strip()
    if not allow_branch and branch != "main":
        raise ReleaseError(
            f"refusing to release from branch {branch!r} (pass --allow-branch to override)"
        )
    return branch


def run_tests() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-m", "not torch"],
        cwd=str(_ROOT),
        check=False,
    )
    if result.returncode != 0:
        raise ReleaseError(f"tests failed (pytest exit code {result.returncode})")


def check_changelog(version: str, *, path: Path = CHANGELOG) -> None:
    if not path.is_file():
        raise ReleaseError(f"CHANGELOG.md is missing at {path}")
    text = path.read_text(encoding="utf-8")
    heading = f"## [{version}]"
    if heading not in text:
        raise ReleaseError(
            f"CHANGELOG.md has no section for {version}. "
            f"Add a '## [{version}] — YYYY-MM-DD' entry before releasing."
        )


def existing_tag(version: str) -> bool:
    result = _run(["git", "tag", "-l", f"v{version}"])
    return bool(result.stdout.strip())


def create_tag(version: str, *, message: str | None = None) -> str:
    if existing_tag(version):
        raise ReleaseError(f"tag v{version} already exists — bump _version.py first")
    msg = message or f"Release v{version}"
    result = _run(["git", "tag", "-a", f"v{version}", "-m", msg])
    if result.returncode != 0:
        raise ReleaseError(f"git tag failed: {result.stderr.strip()}")
    return f"v{version}"


_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def suggest_next_versions(version: str) -> dict[str, str]:
    match = _SEMVER_RE.match(version)
    if not match:
        raise ReleaseError(f"cannot bump non-semver version {version!r}")
    major, minor, patch = (int(x) for x in match.groups())
    return {
        "patch": f"{major}.{minor}.{patch + 1}",
        "minor": f"{major}.{minor + 1}.0",
        "major": f"{major + 1}.0.0",
    }


def regenerate_build_info() -> None:
    result = subprocess.run(
        [sys.executable, str(_ROOT / "scripts" / "generate_build_info.py")],
        cwd=str(_ROOT),
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ReleaseError(f"generate_build_info failed: {result.stderr.strip()}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-tests", action="store_true", help="skip the pytest step")
    parser.add_argument("--no-tag", action="store_true", help="do not create the git tag")
    parser.add_argument(
        "--allow-branch",
        action="store_true",
        help="allow releasing from a branch other than main",
    )
    parser.add_argument(
        "--refresh-build-info",
        action="store_true",
        help="regenerate build_info.json before tagging",
    )
    args = parser.parse_args(argv)

    version = __version__
    print(f"[release] version = {version}")

    try:
        check_clean_tree()
        branch = check_branch(allow_branch=args.allow_branch)
        print(f"[release] branch = {branch}")
        check_changelog(version)
        print("[release] CHANGELOG has an entry for this version")
        if not args.skip_tests:
            print("[release] running pytest -q -m 'not torch'")
            run_tests()
            print("[release] tests OK")
        if args.refresh_build_info:
            regenerate_build_info()
            print("[release] build_info.json regenerated")
        if args.no_tag:
            print("[release] --no-tag: skipping tag creation")
        else:
            tag = create_tag(version)
            print(f"[release] created annotated tag {tag} (not pushed)")
    except ReleaseError as exc:
        print(f"[release] ERROR: {exc}", file=sys.stderr)
        return 1

    suggestions = suggest_next_versions(version)
    print("[release] suggested next versions:")
    for kind, next_v in suggestions.items():
        print(f"           {kind:5s} -> {next_v}")
    print("[release] done. Push with:  git push origin main --tags")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
