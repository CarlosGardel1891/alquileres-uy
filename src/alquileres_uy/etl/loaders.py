"""Iterate the item envelopes and description bodies of a raw run."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .contracts import RawRunContract
from .models import ExtractedItem


def iter_raw_items(run: RawRunContract) -> Iterator[ExtractedItem]:
    """Yield one :class:`ExtractedItem` per successful multiget envelope."""
    description_index = _build_description_index(run.description_paths)
    for batch_path in run.item_batch_paths:
        payload = _read_json(batch_path)
        if not isinstance(payload, list):
            continue
        rel_batch_path = _relative(batch_path, run.run_directory)
        for envelope in payload:
            if not isinstance(envelope, dict):
                yield ExtractedItem(
                    source_item_id=None,
                    raw_item_path=rel_batch_path,
                    raw_description_path=None,
                    source_run_id=run.run_id,
                    body={},
                    description_body=None,
                    first_seen_at=None,
                    last_seen_at=None,
                )
                continue
            code = envelope.get("code")
            body = envelope.get("body") if isinstance(envelope.get("body"), dict) else None
            item_id_raw = envelope.get("id")
            if not isinstance(item_id_raw, str):
                item_id_raw = body.get("id") if isinstance(body, dict) else None
            item_id = item_id_raw if isinstance(item_id_raw, str) else None

            if code != 200 or body is None:
                yield ExtractedItem(
                    source_item_id=item_id,
                    raw_item_path=rel_batch_path,
                    raw_description_path=None,
                    source_run_id=run.run_id,
                    body={},
                    description_body=None,
                    first_seen_at=None,
                    last_seen_at=None,
                )
                continue

            description_path, description_body = description_index.get(item_id, (None, None))
            yield ExtractedItem(
                source_item_id=item_id,
                raw_item_path=rel_batch_path,
                raw_description_path=description_path,
                source_run_id=run.run_id,
                body=body,
                description_body=description_body,
                first_seen_at=run.started_at,
                last_seen_at=run.finished_at,
            )


def _build_description_index(
    description_paths: tuple[Path, ...],
) -> dict[str, tuple[str, dict[str, Any] | None]]:
    index: dict[str, tuple[str, dict[str, Any] | None]] = {}
    for description_path in description_paths:
        item_id = description_path.stem
        body = _read_json(description_path)
        rel = description_path.parent.name + "/" + description_path.name
        index[item_id] = (rel, body if isinstance(body, dict) else None)
    return index


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return path.name
