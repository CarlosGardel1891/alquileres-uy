"""Validation of a raw ingestion run before the ETL touches it.

The manifest is the **authoritative inventory** for a run: only the
files it declares are ever processed, and every declared file must
exist, resolve inside the run directory, and match the SHA-256 the
manifest records for it. Extra JSON files under ``items/`` or
``descriptions/`` that are not declared cause the whole run to be
rejected — silently processing them would let a rogue writer smuggle
data into the pipeline.

Timestamps (``started_at`` / ``finished_at``) are required and must
be ISO-8601 with an explicit timezone. The ETL never assumes a
timezone and never falls back to :func:`datetime.now`; a manifest
without valid timestamps is invalid.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

KNOWN_FILE_KINDS: frozenset[str] = frozenset(
    {"item_batch", "description", "search_page", "error_log", "report"}
)
PROCESSED_KINDS: frozenset[str] = frozenset({"item_batch", "description"})
KIND_TO_DIRECTORY: dict[str, str] = {
    "item_batch": "items",
    "description": "descriptions",
}


class RawRunValidationError(ValueError):
    """Raised when a raw run directory violates the ETL input contract."""


@dataclass(frozen=True)
class RawRunContract:
    """The subset of a raw run the ETL depends on, once validated."""

    run_id: str
    source: str
    status: str
    started_at: datetime
    finished_at: datetime
    run_directory: Path
    manifest_path: Path
    summary_path: Path
    item_batch_paths: tuple[Path, ...]
    description_paths: tuple[Path, ...]
    data_mode: str


def load_raw_run(
    run_directory: Path,
    *,
    data_mode: str,
    fixtures_root: Path | None,
) -> RawRunContract:
    """Validate a raw run directory and return its :class:`RawRunContract`."""
    run_directory = Path(run_directory).resolve()
    if not run_directory.is_dir():
        raise RawRunValidationError(f"raw run directory not found: {run_directory}")

    _check_mode_placement(run_directory, data_mode, fixtures_root)

    manifest_path = run_directory / "manifest.json"
    summary_path = run_directory / "ingestion_summary.json"
    for path, label in ((manifest_path, "manifest"), (summary_path, "summary")):
        if not path.is_file():
            raise RawRunValidationError(f"missing {label}.json in {run_directory}")

    manifest = _load_json(manifest_path)
    summary = _load_json(summary_path)

    source = manifest.get("source")
    if source != "mercadolibre":
        raise RawRunValidationError(f"manifest source must be 'mercadolibre', got {source!r}")
    status = manifest.get("status")
    if status != "completed":
        raise RawRunValidationError(f"manifest status must be 'completed', got {status!r}")

    started_at = _require_aware_iso(manifest, "started_at")
    finished_at = _require_aware_iso(manifest, "finished_at")
    if finished_at < started_at:
        raise RawRunValidationError(
            f"finished_at ({finished_at.isoformat()}) is earlier than "
            f"started_at ({started_at.isoformat()})"
        )

    _validate_summary(summary, manifest, summary_path)

    files_entries = manifest.get("files")
    if not isinstance(files_entries, list) or not files_entries:
        raise RawRunValidationError(
            "manifest.files must be a non-empty list of {path, kind, sha256}"
        )

    item_batches, description_paths = _validate_manifest_files(files_entries, run_directory)

    if not item_batches:
        raise RawRunValidationError("manifest.files must include at least one item_batch")

    _reject_undeclared_files(run_directory, declared=set(item_batches + description_paths))

    return RawRunContract(
        run_id=str(manifest.get("run_id") or run_directory.name),
        source=source,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        run_directory=run_directory,
        manifest_path=manifest_path,
        summary_path=summary_path,
        item_batch_paths=tuple(item_batches),
        description_paths=tuple(description_paths),
        data_mode=data_mode,
    )


# ---- internals ---------------------------------------------------------


def _check_mode_placement(run_directory: Path, data_mode: str, fixtures_root: Path | None) -> None:
    resolved_fixtures = fixtures_root.resolve() if fixtures_root is not None else None
    inside_fixtures = resolved_fixtures is not None and run_directory.is_relative_to(
        resolved_fixtures
    )
    if data_mode == "real" and inside_fixtures:
        raise RawRunValidationError(
            "real mode refuses to ingest a fixture directory; "
            "point --input-run-dir at a real run"
        )
    if data_mode == "fixture" and resolved_fixtures is not None and not inside_fixtures:
        raise RawRunValidationError(
            "fixture mode requires the input run to live under tests/fixtures/"
        )


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RawRunValidationError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RawRunValidationError(f"{path} root must be a JSON object")
    return data


def _require_aware_iso(manifest: dict[str, Any], key: str) -> datetime:
    value = manifest.get(key)
    if not isinstance(value, str) or not value:
        raise RawRunValidationError(f"manifest.{key} is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RawRunValidationError(f"manifest.{key} is not ISO-8601: {value!r}") from exc
    if parsed.tzinfo is None:
        raise RawRunValidationError(f"manifest.{key} must include a timezone offset, got {value!r}")
    return parsed.astimezone(UTC)


def _validate_summary(
    summary: dict[str, Any], manifest: dict[str, Any], summary_path: Path
) -> None:
    summary_run_id = summary.get("run_id")
    manifest_run_id = manifest.get("run_id")
    if (
        isinstance(summary_run_id, str)
        and isinstance(manifest_run_id, str)
        and summary_run_id != manifest_run_id
    ):
        raise RawRunValidationError(
            f"summary run_id {summary_run_id!r} does not match manifest run_id "
            f"{manifest_run_id!r}"
        )


def _validate_manifest_files(
    entries: list[Any],
    run_directory: Path,
) -> tuple[list[Path], list[Path]]:
    item_batches: list[Path] = []
    description_paths: list[Path] = []
    seen_paths: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise RawRunValidationError(
                "each manifest.files entry must be an object with path/kind/sha256"
            )
        raw_path = entry.get("path")
        kind = entry.get("kind")
        sha = entry.get("sha256")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise RawRunValidationError("manifest.files entry has empty or missing path")
        if not isinstance(kind, str) or kind not in KNOWN_FILE_KINDS:
            raise RawRunValidationError(f"manifest.files unknown kind: {kind!r}")
        if not isinstance(sha, str) or not sha.strip():
            raise RawRunValidationError(f"manifest.files entry {raw_path!r} is missing sha256")

        candidate = Path(raw_path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise RawRunValidationError(
                f"manifest.files path is not allowed to escape the run: {raw_path!r}"
            )
        resolved = (run_directory / candidate).resolve()
        if not resolved.is_relative_to(run_directory):
            raise RawRunValidationError(
                f"manifest.files path resolves outside the run: {raw_path!r}"
            )
        logical = str(resolved.relative_to(run_directory)).replace("\\", "/")
        if logical in seen_paths:
            raise RawRunValidationError(f"manifest.files declares {logical!r} twice")
        seen_paths.add(logical)

        if kind not in PROCESSED_KINDS:
            # Presence is validated for auditing but the ETL will not read it.
            if not resolved.is_file():
                raise RawRunValidationError(f"manifest.files declares missing file: {raw_path!r}")
            continue

        expected_dir = KIND_TO_DIRECTORY[kind]
        if not logical.startswith(expected_dir + "/"):
            raise RawRunValidationError(
                f"manifest.files {kind!r} path must live under {expected_dir}/, "
                f"got {raw_path!r}"
            )
        if not resolved.is_file():
            raise RawRunValidationError(f"manifest.files declares missing file: {raw_path!r}")
        actual_hash = hashlib.sha256(resolved.read_bytes()).hexdigest()
        if actual_hash != sha.strip():
            raise RawRunValidationError(
                f"manifest.files sha256 mismatch for {raw_path!r} "
                f"(expected {sha}, got {actual_hash})"
            )
        try:
            json.loads(resolved.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RawRunValidationError(
                f"manifest.files declares a non-JSON file: {raw_path!r}"
            ) from exc

        if kind == "item_batch":
            item_batches.append(resolved)
        else:
            description_paths.append(resolved)

    return sorted(item_batches), sorted(description_paths)


def _reject_undeclared_files(run_directory: Path, *, declared: set[Path]) -> None:
    for subdir_name in ("items", "descriptions"):
        subdir = run_directory / subdir_name
        if not subdir.is_dir():
            continue
        for candidate in subdir.glob("*.json"):
            resolved = candidate.resolve()
            if resolved not in declared:
                logical = str(resolved.relative_to(run_directory)).replace("\\", "/")
                raise RawRunValidationError(
                    f"file {logical!r} exists in the run but is not declared in manifest.files"
                )
