"""Validation of a raw ingestion run before the ETL touches it."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


class RawRunValidationError(ValueError):
    """Raised when a raw run directory violates the ETL input contract."""


@dataclass(frozen=True)
class RawRunContract:
    """The subset of a raw run the ETL depends on, once validated."""

    run_id: str
    source: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None
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

    manifest_path = run_directory / "manifest.json"
    summary_path = run_directory / "ingestion_summary.json"
    for path, label in ((manifest_path, "manifest"), (summary_path, "summary")):
        if not path.is_file():
            raise RawRunValidationError(f"missing {label}.json in {run_directory}")

    manifest = _load_json(manifest_path)
    summary = _load_json(summary_path)
    _ = summary  # summary shape is not strictly validated yet; presence is enough

    source = manifest.get("source")
    if source != "mercadolibre":
        raise RawRunValidationError(f"manifest source must be 'mercadolibre', got {source!r}")
    status = manifest.get("status")
    if status != "completed":
        raise RawRunValidationError(f"manifest status must be 'completed', got {status!r}")

    items_dir = run_directory / "items"
    if not items_dir.is_dir():
        raise RawRunValidationError(f"missing items/ directory in {run_directory}")

    item_batches: list[Path] = []
    seen: set[str] = set()
    for candidate in sorted(items_dir.glob("*.json")):
        resolved = candidate.resolve()
        if not resolved.is_relative_to(run_directory):
            raise RawRunValidationError(f"item batch escapes run directory: {resolved}")
        rel = str(resolved.relative_to(run_directory)).replace("\\", "/")
        if rel in seen:
            raise RawRunValidationError(f"duplicate item batch path: {rel}")
        seen.add(rel)
        # Structural sanity check.
        try:
            json.loads(candidate.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RawRunValidationError(f"item batch is not valid JSON: {candidate}") from exc
        item_batches.append(candidate)

    if not item_batches:
        raise RawRunValidationError(f"no item batches under {items_dir}")

    descriptions_dir = run_directory / "descriptions"
    description_paths: list[Path] = []
    if descriptions_dir.is_dir():
        for candidate in sorted(descriptions_dir.glob("*.json")):
            resolved = candidate.resolve()
            if not resolved.is_relative_to(run_directory):
                raise RawRunValidationError(f"description escapes run directory: {resolved}")
            description_paths.append(candidate)

    return RawRunContract(
        run_id=str(manifest.get("run_id") or run_directory.name),
        source=source,
        status=status,
        started_at=_parse_iso(manifest.get("started_at")),
        finished_at=_parse_iso(manifest.get("finished_at")),
        run_directory=run_directory,
        manifest_path=manifest_path,
        summary_path=summary_path,
        item_batch_paths=tuple(item_batches),
        description_paths=tuple(description_paths),
        data_mode=data_mode,
    )


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RawRunValidationError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RawRunValidationError(f"{path} root must be a JSON object")
    return data


def _parse_iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
