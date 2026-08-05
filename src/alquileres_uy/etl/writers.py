"""Deterministic Parquet + JSON writers for ETL outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def write_parquet(df: pd.DataFrame, path: Path, sort_by: str | None = None) -> Path:
    """Write ``df`` as zstd-compressed Parquet with a deterministic column order."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = df.copy()
    if sort_by and sort_by in frame.columns:
        frame = frame.sort_values(by=sort_by, kind="stable").reset_index(drop=True)
    else:
        frame = frame.reset_index(drop=True)
    table = pa.Table.from_pandas(frame, preserve_index=False)
    pq.write_table(table, path, compression="zstd")
    return path


def write_json(payload: dict[str, Any] | list[Any], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return path
