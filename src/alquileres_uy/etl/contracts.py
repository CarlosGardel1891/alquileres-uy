"""Validation of a raw ingestion run before the ETL touches it.

The manifest is the **authoritative inventory** for a run. Every file
it declares — item batches, descriptions, the ingestion summary
itself, any search page or error log kept for audit — must exist
inside the run directory, resolve without traversal, and match the
SHA-256 the manifest records for it. Files that live in ``items/`` or
``descriptions/`` and are not declared cause the whole run to be
rejected: silently processing them would let a rogue writer smuggle
data into the pipeline.

``ingestion_summary.json`` is not just any file. The manifest must
declare it with ``kind = "report"`` and its ``manifest.summary_path``
must exactly match the declared ``report`` entry's logical path — not
just its basename. The summary itself is cross-checked against the
manifest inventory: ``items_downloaded`` must equal the count of
``code == 200`` envelopes across every declared item batch, and
``descriptions_downloaded`` must equal the count of declared
``description`` entries. The summary's ``started_at`` /
``finished_at`` are required (with an explicit timezone) and must
resolve to the same UTC instant as the manifest timestamps.

Timestamps in the manifest (``started_at``/``finished_at``) are
required and must be ISO-8601 with an explicit timezone. The ETL
never assumes a timezone and never falls back to
:func:`datetime.now`; a manifest without valid timestamps is invalid.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

KNOWN_FILE_KINDS: frozenset[str] = frozenset(
    {"item_batch", "description", "search_page", "error_log", "report"}
)
KIND_TO_DIRECTORY: dict[str, str] = {
    "item_batch": "items",
    "description": "descriptions",
}
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class RawRunValidationError(ValueError):
    """Raised when a raw run directory violates the ETL input contract."""


@dataclass(frozen=True)
class ManifestFileEntry:
    """A single, hash-validated file declared by the raw run manifest."""

    path: str
    kind: str
    sha256: str
    resolved_path: Path


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
    declared_files: tuple[ManifestFileEntry, ...] = field(default_factory=tuple)
    data_mode: str = "fixture"


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

    files_entries_raw = manifest.get("files")
    if not isinstance(files_entries_raw, list) or not files_entries_raw:
        raise RawRunValidationError(
            "manifest.files must be a non-empty list of {path, kind, sha256}"
        )

    declared_entries = _validate_manifest_files(files_entries_raw, run_directory)
    item_batches = tuple(
        entry.resolved_path for entry in declared_entries if entry.kind == "item_batch"
    )
    description_paths = tuple(
        entry.resolved_path for entry in declared_entries if entry.kind == "description"
    )

    if not item_batches:
        raise RawRunValidationError("manifest.files must include at least one item_batch")

    _reject_undeclared_files(
        run_directory,
        declared={entry.resolved_path for entry in declared_entries},
    )

    _validate_summary_declaration(manifest, declared_entries, summary_path)
    _validate_summary_semantics(
        summary,
        manifest=manifest,
        started_at=started_at,
        finished_at=finished_at,
        item_batches=item_batches,
        description_count=len(description_paths),
    )

    return RawRunContract(
        run_id=str(manifest.get("run_id") or run_directory.name),
        source=source,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        run_directory=run_directory,
        manifest_path=manifest_path,
        summary_path=summary_path,
        item_batch_paths=item_batches,
        description_paths=description_paths,
        declared_files=tuple(declared_entries),
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


def _validate_sha256(value: object, *, path: str) -> str:
    """Return the normalized (lower-case) hex digest, or raise."""
    if not isinstance(value, str):
        raise RawRunValidationError(f"manifest.files entry {path!r} sha256 must be a string")
    stripped = value.strip()
    if len(stripped) != 64:
        raise RawRunValidationError(
            f"manifest.files entry {path!r} sha256 must be 64 hex chars, " f"got {len(stripped)}"
        )
    if not _SHA256_RE.match(stripped):
        raise RawRunValidationError(f"manifest.files entry {path!r} sha256 has non-hex characters")
    return stripped.lower()


def _normalize_manifest_relative_path(
    raw_path: str,
    *,
    run_directory: Path,
    label: str,
) -> str:
    """Return the POSIX logical path of ``raw_path`` inside ``run_directory``.

    Applies the same rules across ``manifest.files[*].path`` and
    ``manifest.summary_path``: relative, no ``..``, no absolute (POSIX
    or Windows-drive), no ``./`` prefix, must resolve inside the run.
    Backslashes are normalized to ``/`` on input; the returned value is
    always POSIX-shaped.
    """
    cleaned = raw_path.replace("\\", "/").strip()
    if not cleaned:
        raise RawRunValidationError(f"{label} has empty or missing path")
    if cleaned.startswith("/"):
        raise RawRunValidationError(f"{label} must be a relative POSIX path, got {raw_path!r}")
    if len(cleaned) >= 2 and cleaned[1] == ":":
        raise RawRunValidationError(f"{label} must be a relative POSIX path, got {raw_path!r}")
    if cleaned.startswith("./") or cleaned == ".":
        raise RawRunValidationError(f"{label} must not start with './', got {raw_path!r}")
    candidate = Path(cleaned)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise RawRunValidationError(f"{label} is not allowed to escape the run: {raw_path!r}")
    resolved = (run_directory / candidate).resolve()
    if not resolved.is_relative_to(run_directory):
        raise RawRunValidationError(f"{label} resolves outside the run: {raw_path!r}")
    return str(resolved.relative_to(run_directory)).replace("\\", "/")


def _validate_manifest_files(
    entries: list[Any],
    run_directory: Path,
) -> list[ManifestFileEntry]:
    validated: list[ManifestFileEntry] = []
    seen_paths: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise RawRunValidationError(
                "each manifest.files entry must be an object with path/kind/sha256"
            )
        raw_path = entry.get("path")
        kind = entry.get("kind")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise RawRunValidationError("manifest.files entry has empty or missing path")
        if not isinstance(kind, str) or kind not in KNOWN_FILE_KINDS:
            raise RawRunValidationError(f"manifest.files unknown kind: {kind!r}")

        logical = _normalize_manifest_relative_path(
            raw_path, run_directory=run_directory, label="manifest.files entry"
        )
        resolved = (run_directory / logical).resolve()
        if logical in seen_paths:
            raise RawRunValidationError(f"manifest.files declares {logical!r} twice")
        seen_paths.add(logical)

        declared_hash = _validate_sha256(entry.get("sha256"), path=raw_path)
        if not resolved.is_file():
            raise RawRunValidationError(f"manifest.files declares missing file: {raw_path!r}")
        actual_hash = hashlib.sha256(resolved.read_bytes()).hexdigest()
        if actual_hash != declared_hash:
            raise RawRunValidationError(
                f"manifest.files sha256 mismatch for {raw_path!r} "
                f"(expected {declared_hash}, got {actual_hash})"
            )

        # Structural JSON check only for kinds the ETL will parse. JSONL
        # error logs and streaming search pages are hash-verified but not
        # loaded here.
        if kind in {"item_batch", "description", "report"}:
            try:
                json.loads(resolved.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise RawRunValidationError(
                    f"manifest.files declares a non-JSON file: {raw_path!r}"
                ) from exc

        if kind in KIND_TO_DIRECTORY:
            expected_dir = KIND_TO_DIRECTORY[kind]
            if not logical.startswith(expected_dir + "/"):
                raise RawRunValidationError(
                    f"manifest.files {kind!r} path must live under {expected_dir}/, "
                    f"got {raw_path!r}"
                )

        validated.append(
            ManifestFileEntry(
                path=logical,
                kind=kind,
                sha256=declared_hash,
                resolved_path=resolved,
            )
        )
    return validated


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


def _validate_summary_declaration(
    manifest: dict[str, Any],
    declared: list[ManifestFileEntry],
    summary_path: Path,
) -> None:
    summary_path_declared = manifest.get("summary_path")
    if not isinstance(summary_path_declared, str) or not summary_path_declared.strip():
        raise RawRunValidationError("manifest.summary_path is required")

    run_directory = summary_path.parent
    normalized = _normalize_manifest_relative_path(
        summary_path_declared, run_directory=run_directory, label="manifest.summary_path"
    )

    reports = [entry for entry in declared if entry.kind == "report"]
    exact_matches = [entry for entry in reports if entry.path == normalized]
    if not exact_matches:
        raise RawRunValidationError(
            f"manifest.summary_path {normalized!r} does not match the declared "
            f"report path in manifest.files"
        )
    if len(exact_matches) > 1:
        # Structural duplicates are already caught by _validate_manifest_files,
        # but keep the fallback so the error names the offending field.
        raise RawRunValidationError(
            f"manifest.summary_path {normalized!r} matches more than one report "
            f"entry in manifest.files"
        )
    entry = exact_matches[0]
    if entry.resolved_path != summary_path.resolve():
        raise RawRunValidationError(
            f"manifest.summary_path {normalized!r} does not point to the loaded "
            f"ingestion_summary.json"
        )


def _validate_summary_semantics(
    summary: dict[str, Any],
    *,
    manifest: dict[str, Any],
    started_at: datetime,
    finished_at: datetime,
    item_batches: tuple[Path, ...],
    description_count: int,
) -> None:
    summary_run_id = summary.get("run_id")
    manifest_run_id = manifest.get("run_id")
    if not isinstance(summary_run_id, str) or not summary_run_id.strip():
        raise RawRunValidationError("summary.run_id is required and must be a string")
    if summary_run_id != manifest_run_id:
        raise RawRunValidationError(
            f"summary.run_id {summary_run_id!r} does not match manifest.run_id "
            f"{manifest_run_id!r}"
        )

    summary_status = summary.get("status")
    if summary_status is None:
        raise RawRunValidationError("summary.status is required")
    if summary_status != manifest.get("status"):
        raise RawRunValidationError(
            f"summary.status {summary_status!r} does not match manifest.status "
            f"{manifest.get('status')!r}"
        )

    _require_matching_summary_timestamp(summary, "started_at", started_at)
    _require_matching_summary_timestamp(summary, "finished_at", finished_at)

    items_downloaded = summary.get("items_downloaded")
    if not isinstance(items_downloaded, int) or items_downloaded < 0:
        raise RawRunValidationError(
            f"summary.items_downloaded must be a non-negative int, got " f"{items_downloaded!r}"
        )
    actual_items = _count_successful_envelopes(item_batches)
    if items_downloaded != actual_items:
        raise RawRunValidationError(
            f"summary.items_downloaded={items_downloaded} does not match the "
            f"count of successful item envelopes ({actual_items})"
        )

    descriptions_downloaded = summary.get("descriptions_downloaded")
    if not isinstance(descriptions_downloaded, int) or descriptions_downloaded < 0:
        raise RawRunValidationError(
            f"summary.descriptions_downloaded must be a non-negative int, got "
            f"{descriptions_downloaded!r}"
        )
    if descriptions_downloaded != description_count:
        raise RawRunValidationError(
            f"summary.descriptions_downloaded={descriptions_downloaded} does not "
            f"match the declared descriptions count ({description_count})"
        )


def _require_matching_summary_timestamp(
    summary: dict[str, Any], key: str, expected: datetime
) -> None:
    """Require ``summary[key]`` to be an ISO-8601 tz-aware timestamp equal to ``expected``.

    Unlike a "cross-check", the field is not optional: a missing,
    null, or empty value is rejected. The comparison is done after
    normalizing both sides to UTC, so an equivalent offset (e.g.
    ``-03:00`` vs ``Z``) is accepted as long as the instant matches.
    """
    if key not in summary or summary.get(key) is None:
        raise RawRunValidationError(f"summary.{key} is required")
    raw = summary.get(key)
    if not isinstance(raw, str) or not raw.strip():
        raise RawRunValidationError(f"summary.{key} is required")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RawRunValidationError(f"summary.{key} is not ISO-8601: {raw!r}") from exc
    if parsed.tzinfo is None:
        raise RawRunValidationError(f"summary.{key} must include a timezone offset, got {raw!r}")
    if parsed.astimezone(UTC) != expected:
        raise RawRunValidationError(
            f"summary.{key} {raw!r} does not match manifest.{key} " f"({expected.isoformat()})"
        )


def _count_successful_envelopes(item_batches: tuple[Path, ...]) -> int:
    total = 0
    for batch_path in item_batches:
        try:
            payload = json.loads(batch_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, list):
            continue
        for envelope in payload:
            if not isinstance(envelope, dict):
                continue
            body = envelope.get("body")
            if envelope.get("code") != 200 or not isinstance(body, dict):
                continue
            item_id = envelope.get("id") or body.get("id")
            if isinstance(item_id, str) and item_id:
                total += 1
    return total
