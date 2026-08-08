"""Generate ``docs/project-tree.md`` from the current repository layout.

Stdlib-only. Writes an ASCII tree that skips build / vendor / data
directories so the output is stable across environments. The list of
excluded names comes from the Fase 14 prompt.

Usage
-----

    python scripts/generate_project_tree.py                 # write default
    python scripts/generate_project_tree.py --output foo.md # custom path
    python scripts/generate_project_tree.py --print         # echo to stdout too
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

EXCLUDED_NAMES = {
    "__pycache__",
    ".venv",
    ".git",
    "data",
    "artifacts",
    "build",
    "dist",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "node_modules",
    ".idea",
    ".vscode",
    ".claude",
    "site",
    "htmlcov",
}

EXCLUDED_TOP_LEVEL = {
    "prompt.txt",  # unversioned by convention (see CONTRIBUTING)
}

EXCLUDED_SUFFIXES = (
    ".egg-info",
    ".egg",
)


def _is_excluded(entry: Path, *, is_top_level: bool = False) -> bool:
    if entry.name in EXCLUDED_NAMES:
        return True
    if is_top_level and entry.name in EXCLUDED_TOP_LEVEL:
        return True
    return any(entry.name.endswith(suffix) for suffix in EXCLUDED_SUFFIXES)


def _iter_children(directory: Path, *, is_top_level: bool = False) -> list[Path]:
    children = [p for p in directory.iterdir() if not _is_excluded(p, is_top_level=is_top_level)]
    children.sort(key=lambda p: (not p.is_dir(), p.name.lower()))
    return children


def render_tree(root: Path, *, max_depth: int | None = None) -> str:
    """Return the ASCII tree rooted at ``root``."""
    lines: list[str] = [f"{root.name}/"]

    def walk(directory: Path, prefix: str, depth: int) -> None:
        if max_depth is not None and depth >= max_depth:
            return
        children = _iter_children(directory, is_top_level=(depth == 0))
        for idx, child in enumerate(children):
            connector = "└── " if idx == len(children) - 1 else "├── "
            marker = "/" if child.is_dir() else ""
            lines.append(f"{prefix}{connector}{child.name}{marker}")
            if child.is_dir():
                extension = "    " if idx == len(children) - 1 else "│   "
                walk(child, prefix + extension, depth + 1)

    walk(root, "", 0)
    return "\n".join(lines)


DEFAULT_OUTPUT = _ROOT / "docs" / "project-tree.md"


def build_markdown(*, root: Path, tree: str, now: datetime | None = None) -> str:
    ts = (now or datetime.now(tz=UTC)).replace(microsecond=0).isoformat()
    excluded = ", ".join(sorted(EXCLUDED_NAMES))
    return (
        "# Project tree\n\n"
        f"Snapshot del árbol del repositorio en `{root.name}/` — generado por\n"
        "`scripts/generate_project_tree.py`.\n\n"
        "El script excluye directorios de build, cache, virtualenv, datos crudos\n"
        "y artefactos porque no forman parte del código versionado:\n\n"
        f"    {excluded}\n\n"
        "Para regenerarlo:\n\n"
        "```bash\n"
        "python scripts/generate_project_tree.py\n"
        "```\n\n"
        f"Última actualización: `{ts}`.\n\n"
        "```\n"
        f"{tree}\n"
        "```\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="destination file (default: %(default)s)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=_ROOT,
        help="root directory to render (default: repository root)",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="optional recursion depth cap for the tree",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="echo the markdown to stdout in addition to writing the file",
    )
    args = parser.parse_args(argv)

    tree = render_tree(args.root, max_depth=args.max_depth)
    markdown = build_markdown(root=args.root, tree=tree)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown, encoding="utf-8")
    if args.print:
        sys.stdout.write(markdown)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
