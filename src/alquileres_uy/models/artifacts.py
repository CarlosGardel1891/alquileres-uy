"""Atomic artifact publisher for training runs.

Manages the ``<training-run-dir>.tmp`` → ``<training-run-dir>`` rename
and computes hashes for every file the pipeline drops in. Also owns
the JSON writers so timestamps land as ISO-8601 UTC and files are
always LF-terminated for deterministic hashing.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class ArtifactError(RuntimeError):
    """Raised on atomic-publish failures."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, default=_default)
    path.write_bytes((text + "\n").encode("utf-8"))
    return path


def _default(value: object) -> object:
    from datetime import datetime

    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"cannot JSON-serialize {type(value).__name__}")


def iter_files(directory: Path) -> Iterator[Path]:
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            yield path


def artifact_size(directory: Path) -> int:
    return sum(p.stat().st_size for p in iter_files(directory))


@contextmanager
def atomic_run_directory(final_dir: Path) -> Iterator[Path]:
    final_dir = Path(final_dir).resolve()
    if final_dir.exists():
        raise ArtifactError(
            f"training run directory already exists — refusing to overwrite: {final_dir}"
        )
    tmp_dir = (
        final_dir.with_suffix(final_dir.suffix + ".tmp")
        if final_dir.suffix
        else final_dir.parent / (final_dir.name + ".tmp")
    )
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=False)
    try:
        yield tmp_dir
    except BaseException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    else:
        try:
            tmp_dir.rename(final_dir)
        except OSError as exc:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise ArtifactError(f"failed to rename {tmp_dir} → {final_dir}: {exc}") from exc


__all__ = [
    "ArtifactError",
    "artifact_size",
    "atomic_run_directory",
    "iter_files",
    "sha256_file",
    "write_json",
]
