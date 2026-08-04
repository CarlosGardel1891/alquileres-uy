"""SQLite persistence for ingestion control (runs, queries, items, errors).

The repository stores control-plane data only: which runs happened, which
queries were sent, which item IDs were seen, and which errors were logged.
Analytical data (raw response payloads) lives on disk under
``data/raw/mercadolibre/`` and is *not* stored in SQLite.

Idempotency is enforced at the ``items`` level: repeated runs for the same
``item_id`` never insert a duplicate row; ``first_seen_at`` is preserved
and ``last_seen_at`` is refreshed.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .models import CandidateStatus, QueryStatus, RunStatus

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY,
        source TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        status TEXT NOT NULL,
        query_plan_hash TEXT,
        max_items INTEGER NOT NULL,
        requests_per_second REAL NOT NULL,
        total_search_results INTEGER NOT NULL DEFAULT 0,
        total_unique_items INTEGER NOT NULL DEFAULT 0,
        total_items_downloaded INTEGER NOT NULL DEFAULT 0,
        total_descriptions_downloaded INTEGER NOT NULL DEFAULT 0,
        total_errors INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS queries (
        query_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        segment_key TEXT NOT NULL,
        parameters_json TEXT NOT NULL,
        status TEXT NOT NULL,
        reported_total INTEGER,
        pages_downloaded INTEGER NOT NULL DEFAULT 0,
        results_received INTEGER NOT NULL DEFAULT 0,
        error_message TEXT,
        repeated_page_detected INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS items (
        item_id TEXT PRIMARY KEY,
        source TEXT NOT NULL,
        first_seen_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        latest_raw_path TEXT,
        category_id TEXT,
        status TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS run_items (
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        item_id TEXT NOT NULL REFERENCES items(item_id),
        query_id TEXT REFERENCES queries(query_id),
        raw_path TEXT,
        position INTEGER,
        candidate_status TEXT,
        exclusion_reason TEXT,
        PRIMARY KEY (run_id, item_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS request_errors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL REFERENCES runs(run_id),
        endpoint TEXT NOT NULL,
        status_code INTEGER,
        attempt INTEGER NOT NULL,
        error_type TEXT NOT NULL,
        message TEXT,
        occurred_at TEXT NOT NULL
    )
    """,
)


class IngestionRepository:
    """SQLite-backed control-plane repository."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = Path(database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            self._database_path,
            isolation_level=None,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._create_schema()

    @property
    def path(self) -> Path:
        return self._database_path

    def close(self) -> None:
        self._connection.close()

    def _create_schema(self) -> None:
        with self._transaction() as cursor:
            for statement in SCHEMA_STATEMENTS:
                cursor.execute(statement)

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Cursor]:
        cursor = self._connection.cursor()
        cursor.execute("BEGIN")
        try:
            yield cursor
        except Exception:
            cursor.execute("ROLLBACK")
            raise
        else:
            cursor.execute("COMMIT")
        finally:
            cursor.close()

    # ---- runs ----------------------------------------------------------

    def start_run(
        self,
        *,
        run_id: str,
        source: str,
        started_at: str,
        max_items: int,
        requests_per_second: float,
        query_plan_hash: str,
    ) -> None:
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO runs (
                    run_id, source, started_at, status, query_plan_hash,
                    max_items, requests_per_second
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    source,
                    started_at,
                    RunStatus.STARTED.value,
                    query_plan_hash,
                    max_items,
                    requests_per_second,
                ),
            )

    def finalize_run(
        self,
        *,
        run_id: str,
        finished_at: str,
        status: RunStatus,
        totals: dict[str, int],
    ) -> None:
        with self._transaction() as cursor:
            cursor.execute(
                """
                UPDATE runs
                   SET finished_at = ?,
                       status = ?,
                       total_search_results = ?,
                       total_unique_items = ?,
                       total_items_downloaded = ?,
                       total_descriptions_downloaded = ?,
                       total_errors = ?
                 WHERE run_id = ?
                """,
                (
                    finished_at,
                    status.value,
                    totals.get("search_results", 0),
                    totals.get("unique_items", 0),
                    totals.get("items_downloaded", 0),
                    totals.get("descriptions_downloaded", 0),
                    totals.get("errors", 0),
                    run_id,
                ),
            )

    # ---- queries -------------------------------------------------------

    def record_query(
        self,
        *,
        query_id: str,
        run_id: str,
        segment_key: str,
        parameters: dict[str, Any],
        status: QueryStatus,
        reported_total: int | None = None,
        pages_downloaded: int = 0,
        results_received: int = 0,
        error_message: str | None = None,
        repeated_page_detected: bool = False,
    ) -> None:
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO queries (
                    query_id, run_id, segment_key, parameters_json, status,
                    reported_total, pages_downloaded, results_received,
                    error_message, repeated_page_detected
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    query_id,
                    run_id,
                    segment_key,
                    json.dumps(parameters, sort_keys=True, ensure_ascii=False),
                    status.value,
                    reported_total,
                    pages_downloaded,
                    results_received,
                    error_message,
                    1 if repeated_page_detected else 0,
                ),
            )

    # ---- items ---------------------------------------------------------

    def upsert_item(
        self,
        *,
        item_id: str,
        source: str,
        observed_at: str,
        latest_raw_path: str | None = None,
        category_id: str | None = None,
        status: str | None = None,
    ) -> None:
        """Insert an item or refresh ``last_seen_at`` if already present.

        ``first_seen_at`` is preserved; ``last_seen_at`` is always updated.
        Optional fields only overwrite the existing row when non-null.
        """
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO items (
                    item_id, source, first_seen_at, last_seen_at,
                    latest_raw_path, category_id, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_id) DO UPDATE SET
                    last_seen_at = excluded.last_seen_at,
                    latest_raw_path = COALESCE(excluded.latest_raw_path,
                                               items.latest_raw_path),
                    category_id = COALESCE(excluded.category_id, items.category_id),
                    status = COALESCE(excluded.status, items.status)
                """,
                (
                    item_id,
                    source,
                    observed_at,
                    observed_at,
                    latest_raw_path,
                    category_id,
                    status,
                ),
            )

    def record_run_item(
        self,
        *,
        run_id: str,
        item_id: str,
        query_id: str | None,
        raw_path: str | None,
        position: int,
        candidate_status: CandidateStatus,
        exclusion_reason: str | None,
    ) -> None:
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO run_items (
                    run_id, item_id, query_id, raw_path, position,
                    candidate_status, exclusion_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    item_id,
                    query_id,
                    raw_path,
                    position,
                    candidate_status.value,
                    exclusion_reason,
                ),
            )

    # ---- errors --------------------------------------------------------

    def record_error(
        self,
        *,
        run_id: str,
        endpoint: str,
        status_code: int | None,
        attempt: int,
        error_type: str,
        message: str,
        occurred_at: str,
    ) -> None:
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO request_errors (
                    run_id, endpoint, status_code, attempt,
                    error_type, message, occurred_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, endpoint, status_code, attempt, error_type, message, occurred_at),
            )

    # ---- read helpers used by tests and reporting ----------------------

    def count_items(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) AS n FROM items").fetchone()
        return int(row["n"])

    def item(self, item_id: str) -> sqlite3.Row | None:
        return self._connection.execute(
            "SELECT * FROM items WHERE item_id = ?", (item_id,)
        ).fetchone()

    def run_items(self, run_id: str) -> Iterable[sqlite3.Row]:
        return self._connection.execute(
            "SELECT * FROM run_items WHERE run_id = ? ORDER BY position",
            (run_id,),
        ).fetchall()

    def errors_by_status(self, run_id: str) -> dict[str, int]:
        rows = self._connection.execute(
            """
            SELECT COALESCE(CAST(status_code AS TEXT), error_type) AS key,
                   COUNT(*) AS n
              FROM request_errors
             WHERE run_id = ?
             GROUP BY key
            """,
            (run_id,),
        ).fetchall()
        return {str(row["key"]): int(row["n"]) for row in rows}
