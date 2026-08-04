"""Build the ``lineage.json`` document for a single ETL run.

``lineage.json`` is written **last** so it can hash every other file
the run produced. Because it cannot hash itself, the payload includes
``"lineage_self_hashed": false``. Inputs include the raw run manifest
and summary as well as every declared batch and description; outputs
include the four Parquet files plus every sidecar JSON except
``lineage.json`` itself.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from alquileres_uy import __version__

from .contracts import RawRunContract


def file_sha256(path: Path | None) -> str | None:
    if path is None:
        return None
    path = Path(path)
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_input_hashes(runs: Iterable[RawRunContract]) -> tuple[dict[str, str], int]:
    hashes: dict[str, str] = {}
    count = 0
    for run in runs:
        for path in (run.manifest_path, run.summary_path):
            digest = file_sha256(path)
            if digest is None:
                continue
            hashes[f"{run.run_directory.name}/{path.name}"] = digest
            count += 1
        for path in (*run.item_batch_paths, *run.description_paths):
            digest = file_sha256(path)
            if digest is None:
                continue
            key = f"{run.run_directory.name}/{path.relative_to(run.run_directory).as_posix()}"
            hashes[key] = digest
            count += 1
    return hashes, count


def build_lineage(
    *,
    etl_run_id: str,
    etl_schema_version: str,
    data_mode: str,
    started_at: str,
    finished_at: str,
    runs: Iterable[RawRunContract],
    gate_approval_path: Path | None,
    exchange_rate_path: Path,
    neighborhood_aliases_path: Path | None,
    output_files: dict[str, Path],
    row_counts: dict[str, int],
) -> dict[str, Any]:
    """Assemble the lineage payload for :func:`writers.write_json`."""
    runs_list = list(runs)
    input_runs_meta: list[dict[str, Any]] = [
        {
            "run_id": run.run_id,
            "source": run.source,
            "run_directory_name": run.run_directory.name,
            "item_batch_count": len(run.item_batch_paths),
            "description_count": len(run.description_paths),
        }
        for run in runs_list
    ]
    input_hashes, input_count = build_input_hashes(runs_list)
    output_sha: dict[str, str | None] = {
        name: file_sha256(path) for name, path in output_files.items() if name != "lineage"
    }
    output_files_meta = {
        name: Path(path).name for name, path in output_files.items() if name != "lineage"
    }
    return {
        "etl_run_id": etl_run_id,
        "etl_schema_version": etl_schema_version,
        "data_mode": data_mode,
        "started_at": started_at,
        "finished_at": finished_at,
        "application_version": __version__,
        "input_runs": input_runs_meta,
        "input_file_count": input_count,
        "input_file_sha256": input_hashes,
        "gate_approval_path": (
            Path(gate_approval_path).name if gate_approval_path is not None else None
        ),
        "gate_approval_sha256": file_sha256(gate_approval_path),
        "exchange_rate_path": Path(exchange_rate_path).name,
        "exchange_rate_sha256": file_sha256(exchange_rate_path),
        "neighborhood_aliases_sha256": file_sha256(neighborhood_aliases_path),
        "output_files": output_files_meta,
        "output_sha256": output_sha,
        "row_counts": dict(row_counts),
        "lineage_self_hashed": False,
    }
