"""Manifest and ingestion summary generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from alquileres_uy import __version__

from .filesystem import atomic_write_json
from .models import RunStatus


def write_manifest(
    workdir: Path,
    *,
    run_id: str,
    source: str,
    site_id: str,
    started_at: str,
    finished_at: str,
    status: RunStatus,
    query_plan_hash: str,
    max_items: int,
    requests_per_second: float,
    request_timeout_seconds: float,
    token_used: bool,
    files: list[dict[str, str]],
) -> Path:
    manifest = {
        "run_id": run_id,
        "source": source,
        "site_id": site_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "status": status.value,
        "application_version": __version__,
        "query_plan_hash": query_plan_hash,
        "config": {
            "max_items": max_items,
            "requests_per_second": requests_per_second,
            "timeout_seconds": request_timeout_seconds,
        },
        "authentication": {"token_used": token_used},
        "files": sorted(files, key=lambda entry: entry.get("path", "")),
        "summary_path": "ingestion_summary.json",
    }
    path, _ = atomic_write_json(Path(workdir) / "manifest.json", manifest)
    return path


def write_summary(workdir: Path, summary: dict[str, Any]) -> Path:
    path, _ = atomic_write_json(Path(workdir) / "ingestion_summary.json", summary)
    return path


def format_duration(seconds: float) -> str:
    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
