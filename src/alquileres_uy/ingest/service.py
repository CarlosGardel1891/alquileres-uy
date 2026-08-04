"""Ingestion orchestrator for MercadoLibre.

The service ties together the query plan, HTTP client, filesystem writer
and SQLite repository. It:

1. probes each seed segment;
2. splits segments whose reported total exceeds the safe cap;
3. paginates every leaf segment up to :data:`MAX_SEARCH_OFFSET`;
4. deduplicates item IDs globally;
5. downloads item details in multiget batches of 20;
6. downloads descriptions;
7. writes a manifest and summary for the run.

Raw responses are persisted before parsing. The workdir is unique per
run, so subsequent runs never overwrite prior data.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .client import MAX_MULTIGET_BATCH_SIZE, MercadoLibreClient
from .config import (
    MAX_SEARCH_OFFSET,
    MAX_SEARCH_PAGE_SIZE,
    IngestionConfig,
)
from .errors import IngestionError
from .filesystem import append_jsonl, atomic_write_json
from .models import (
    CandidateStatus,
    FieldCoverage,
    QuerySegment,
    QueryStatus,
    RunStatus,
)
from .query_plan import (
    SAFE_SEGMENT_LIMIT,
    build_initial_plan,
    classify_candidate,
    plan_hash,
    split_by_bedrooms,
    split_by_price,
)
from .reporting import format_duration, write_manifest, write_summary
from .repository import IngestionRepository

logger = logging.getLogger(__name__)

MAX_SEGMENT_DEPTH = 3
MAX_PAGES_PER_SEGMENT = MAX_SEARCH_OFFSET // MAX_SEARCH_PAGE_SIZE


@dataclass
class IngestionResult:
    run_id: str
    workdir: Path
    summary: dict[str, Any]
    manifest_path: Path | None
    summary_path: Path | None


@dataclass
class _PlanEntry:
    segment: QuerySegment
    depth: int = 0
    is_leaf: bool = False


@dataclass
class _RunState:
    seen_ids: set[str] = field(default_factory=set)
    unique_ids: list[str] = field(default_factory=list)
    duplicate_ids_across_queries: int = 0
    search_results_received: int = 0
    queries_planned: int = 0
    queries_completed: int = 0
    queries_failed: int = 0
    items_requested: int = 0
    items_downloaded: int = 0
    items_failed: int = 0
    descriptions_requested: int = 0
    descriptions_downloaded: int = 0
    descriptions_missing: int = 0
    errors: int = 0
    candidate_items: int = 0
    excluded_items: int = 0
    unknown_items: int = 0
    files: set[str] = field(default_factory=set)
    field_coverage: dict[str, FieldCoverage] = field(default_factory=dict)


class IngestionService:
    """Coordinates one ingestion run."""

    def __init__(
        self,
        config: IngestionConfig,
        client_factory: Callable[[IngestionConfig], MercadoLibreClient] | None = None,
        repository_factory: Callable[[Path], IngestionRepository] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._client_factory = client_factory or (lambda cfg: MercadoLibreClient(cfg))
        self._repository_factory = repository_factory or IngestionRepository
        self._clock = clock or (lambda: datetime.now(UTC))

    # -- entry points ---------------------------------------------------

    def dry_run(self) -> dict[str, Any]:
        segments = build_initial_plan(site_id=self._config.site_id)
        return {
            "dry_run": True,
            "site_id": self._config.site_id,
            "seed_segments": [segment.as_dict() for segment in segments],
            "seed_segment_count": len(segments),
            "query_plan_hash": plan_hash(segments),
            "max_items": self._config.max_items,
            "requests_per_second": self._config.requests_per_second,
            "database_path": str(self._config.database_path),
            "output_dir": str(self._config.output_dir),
        }

    def run(self) -> IngestionResult:
        started_at = self._clock()
        run_id = uuid.uuid4().hex
        workdir = self._prepare_workdir(started_at, run_id)
        segments = build_initial_plan(site_id=self._config.site_id)
        query_plan_hash = plan_hash(segments)

        repository = self._repository_factory(self._config.database_path)
        state = _RunState()
        run_status = RunStatus.COMPLETED

        try:
            repository.start_run(
                run_id=run_id,
                source="mercadolibre",
                started_at=self._iso(started_at),
                max_items=self._config.max_items,
                requests_per_second=self._config.requests_per_second,
                query_plan_hash=query_plan_hash,
            )
            client = self._client_factory(self._config)

            self._collect_ids(client, repository, run_id, workdir, segments, state)
            self._download_items(client, repository, run_id, workdir, state)
            self._download_descriptions(client, repository, run_id, workdir, state)
        except Exception:
            run_status = RunStatus.FAILED
            logger.exception("ingestion failed for run %s", run_id)
            raise
        finally:
            finished_at = self._clock()
            repository.finalize_run(
                run_id=run_id,
                finished_at=self._iso(finished_at),
                status=run_status,
                totals={
                    "search_results": state.search_results_received,
                    "unique_items": len(state.unique_ids),
                    "items_downloaded": state.items_downloaded,
                    "descriptions_downloaded": state.descriptions_downloaded,
                    "errors": state.errors,
                },
            )

            duration = (finished_at - started_at).total_seconds()
            summary = self._build_summary(
                run_id=run_id,
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=duration,
                state=state,
                errors_by_status=repository.errors_by_status(run_id),
            )
            summary_path = write_summary(workdir, summary)
            state.files.add("ingestion_summary.json")
            manifest_path = write_manifest(
                workdir,
                run_id=run_id,
                source="mercadolibre",
                site_id=self._config.site_id,
                started_at=self._iso(started_at),
                finished_at=self._iso(finished_at),
                status=run_status,
                query_plan_hash=query_plan_hash,
                max_items=self._config.max_items,
                requests_per_second=self._config.requests_per_second,
                request_timeout_seconds=self._config.request_timeout_seconds,
                token_used=self._config.access_token is not None,
                files=sorted(state.files),
            )
            self._log_summary(summary, duration)
            repository.close()

        return IngestionResult(
            run_id=run_id,
            workdir=workdir,
            summary=summary,
            manifest_path=manifest_path,
            summary_path=summary_path,
        )

    # -- id collection --------------------------------------------------

    def _collect_ids(
        self,
        client: MercadoLibreClient,
        repository: IngestionRepository,
        run_id: str,
        workdir: Path,
        seed_segments: list[QuerySegment],
        state: _RunState,
    ) -> None:
        searches_dir = workdir / "searches"
        errors_path = workdir / "errors" / "errors.jsonl"

        queue: list[_PlanEntry] = [_PlanEntry(segment=segment) for segment in seed_segments]
        query_index = 0

        while queue and len(state.unique_ids) < self._config.max_items:
            entry = queue.pop(0)
            query_index += 1
            state.queries_planned += 1
            query_id = f"{run_id}-{query_index:04d}"
            segment_dir = searches_dir / f"query_{query_index:04d}"
            pages_downloaded = 0
            results_received = 0
            reported_total: int | None = None
            error_message: str | None = None

            try:
                for page_index in range(1, MAX_PAGES_PER_SEGMENT + 1):
                    offset = (page_index - 1) * MAX_SEARCH_PAGE_SIZE
                    params = self._segment_to_search_params(entry.segment, offset)
                    response = client.search_items(self._config.site_id, params=params)
                    page_data = response.json()
                    page_path, _ = atomic_write_json(
                        segment_dir / f"page_{page_index:04d}.json", page_data
                    )
                    state.files.add(str(page_path.relative_to(workdir)))
                    pages_downloaded += 1
                    reported_total = self._paging_total(page_data) or reported_total

                    ids_on_page = self._extract_ids(page_data)
                    results_received += len(ids_on_page)

                    if not entry.is_leaf and reported_total and reported_total > SAFE_SEGMENT_LIMIT:
                        splits = self._split_segment(entry)
                        if splits:
                            queue.extend(splits)
                            break

                    for item_id in ids_on_page:
                        if item_id in state.seen_ids:
                            state.duplicate_ids_across_queries += 1
                            continue
                        state.seen_ids.add(item_id)
                        state.unique_ids.append(item_id)
                        if len(state.unique_ids) >= self._config.max_items:
                            break

                    if len(ids_on_page) < MAX_SEARCH_PAGE_SIZE:
                        break
                    if reported_total is not None and offset + MAX_SEARCH_PAGE_SIZE >= min(
                        reported_total, MAX_SEARCH_OFFSET
                    ):
                        break
                    if len(state.unique_ids) >= self._config.max_items:
                        break
            except IngestionError as exc:
                state.queries_failed += 1
                error_message = str(exc)
                state.errors += 1
                repository.record_error(
                    run_id=run_id,
                    endpoint=f"/sites/{self._config.site_id}/search",
                    status_code=getattr(exc, "status_code", None),
                    attempt=self._config.max_attempts,
                    error_type=exc.__class__.__name__,
                    message=str(exc),
                    occurred_at=self._iso(self._clock()),
                )
                append_jsonl(
                    errors_path,
                    {
                        "run_id": run_id,
                        "query_id": query_id,
                        "endpoint": "search",
                        "error_type": exc.__class__.__name__,
                        "message": str(exc),
                    },
                )
                state.files.add(str(errors_path.relative_to(workdir)))
            else:
                state.queries_completed += 1
                state.search_results_received += results_received

            repository.record_query(
                query_id=query_id,
                run_id=run_id,
                segment_key=entry.segment.segment_key,
                parameters=entry.segment.parameters,
                status=QueryStatus.COMPLETED if error_message is None else QueryStatus.FAILED,
                reported_total=reported_total,
                pages_downloaded=pages_downloaded,
                results_received=results_received,
                error_message=error_message,
            )

    def _segment_to_search_params(self, segment: QuerySegment, offset: int) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": MAX_SEARCH_PAGE_SIZE, "offset": offset}
        for key in ("category", "state", "price", "BEDROOMS"):
            if key in segment.parameters:
                params[key] = segment.parameters[key]
        if segment.parameters.get("operation") == "rent":
            params.setdefault("q", "alquiler")
        return params

    def _split_segment(self, entry: _PlanEntry) -> list[_PlanEntry]:
        if entry.depth >= MAX_SEGMENT_DEPTH:
            entry.is_leaf = True
            return []
        if "price" not in entry.segment.parameters:
            return [
                _PlanEntry(segment=child, depth=entry.depth + 1)
                for child in split_by_price(entry.segment)
            ]
        if "BEDROOMS" not in entry.segment.parameters:
            return [
                _PlanEntry(segment=child, depth=entry.depth + 1, is_leaf=True)
                for child in split_by_bedrooms(entry.segment)
            ]
        entry.is_leaf = True
        return []

    def _paging_total(self, page_data: Any) -> int | None:
        if not isinstance(page_data, dict):
            return None
        paging = page_data.get("paging")
        if isinstance(paging, dict):
            total = paging.get("total")
            if isinstance(total, int):
                return total
        return None

    def _extract_ids(self, page_data: Any) -> list[str]:
        if not isinstance(page_data, dict):
            return []
        results = page_data.get("results")
        if not isinstance(results, list):
            return []
        ids: list[str] = []
        for entry in results:
            if isinstance(entry, dict):
                value = entry.get("id")
                if isinstance(value, str):
                    ids.append(value)
        return ids

    # -- item downloading -----------------------------------------------

    def _download_items(
        self,
        client: MercadoLibreClient,
        repository: IngestionRepository,
        run_id: str,
        workdir: Path,
        state: _RunState,
    ) -> None:
        items_dir = workdir / "items"
        errors_path = workdir / "errors" / "errors.jsonl"
        state.items_requested = len(state.unique_ids)
        ordered_ids = sorted(state.unique_ids)
        batch_index = 0
        position = 0

        for start in range(0, len(ordered_ids), MAX_MULTIGET_BATCH_SIZE):
            batch_ids = ordered_ids[start : start + MAX_MULTIGET_BATCH_SIZE]
            batch_index += 1
            try:
                response = client.get_items(batch_ids)
                batch_data = response.json()
                batch_path, _ = atomic_write_json(
                    items_dir / f"batch_{batch_index:04d}.json", batch_data
                )
                state.files.add(str(batch_path.relative_to(workdir)))
            except IngestionError as exc:
                state.errors += 1
                state.items_failed += len(batch_ids)
                repository.record_error(
                    run_id=run_id,
                    endpoint="/items",
                    status_code=getattr(exc, "status_code", None),
                    attempt=self._config.max_attempts,
                    error_type=exc.__class__.__name__,
                    message=str(exc),
                    occurred_at=self._iso(self._clock()),
                )
                append_jsonl(
                    errors_path,
                    {
                        "run_id": run_id,
                        "endpoint": "items",
                        "batch_index": batch_index,
                        "error_type": exc.__class__.__name__,
                        "message": str(exc),
                    },
                )
                state.files.add(str(errors_path.relative_to(workdir)))
                continue

            if not isinstance(batch_data, list):
                state.items_failed += len(batch_ids)
                continue

            for envelope in batch_data:
                if not isinstance(envelope, dict):
                    continue
                item_id = envelope.get("id") or (
                    envelope.get("body", {}).get("id")
                    if isinstance(envelope.get("body"), dict)
                    else None
                )
                code = envelope.get("code")
                body = envelope.get("body")
                if code != 200 or not isinstance(body, dict):
                    state.items_failed += 1
                    continue
                item_id = item_id or body.get("id")
                if not isinstance(item_id, str):
                    continue
                state.items_downloaded += 1
                position += 1
                candidate_status_str, reason = classify_candidate(body)
                candidate_status = CandidateStatus(candidate_status_str)
                if candidate_status is CandidateStatus.CANDIDATE:
                    state.candidate_items += 1
                elif candidate_status is CandidateStatus.EXCLUDED:
                    state.excluded_items += 1
                else:
                    state.unknown_items += 1

                observed_at = self._iso(self._clock())
                repository.upsert_item(
                    item_id=item_id,
                    source="mercadolibre",
                    observed_at=observed_at,
                    latest_raw_path=str(batch_path.relative_to(workdir)),
                    category_id=body.get("category_id")
                    if isinstance(body.get("category_id"), str)
                    else None,
                    status=candidate_status.value,
                )
                repository.record_run_item(
                    run_id=run_id,
                    item_id=item_id,
                    query_id=None,
                    raw_path=str(batch_path.relative_to(workdir)),
                    position=position,
                    candidate_status=candidate_status,
                    exclusion_reason=reason,
                )
                self._track_field_coverage(state, body)

    def _track_field_coverage(self, state: _RunState, item: dict[str, Any]) -> None:
        tracked = ("price", "currency_id", "location", "date_created", "category_id")
        for field_name in tracked:
            coverage = state.field_coverage.setdefault(field_name, FieldCoverage())
            coverage.total += 1
            if field_name == "location":
                if item.get("location") or item.get("address"):
                    coverage.present += 1
            elif item.get(field_name) not in (None, ""):
                coverage.present += 1

    # -- descriptions ---------------------------------------------------

    def _download_descriptions(
        self,
        client: MercadoLibreClient,
        repository: IngestionRepository,
        run_id: str,
        workdir: Path,
        state: _RunState,
    ) -> None:
        descriptions_dir = workdir / "descriptions"
        errors_path = workdir / "errors" / "errors.jsonl"
        target_ids = sorted(state.unique_ids)
        state.descriptions_requested = len(target_ids)

        for item_id in target_ids:
            try:
                response = client.get_item_description(item_id)
            except IngestionError as exc:
                state.descriptions_missing += 1
                if getattr(exc, "status_code", None) not in {404}:
                    state.errors += 1
                    repository.record_error(
                        run_id=run_id,
                        endpoint="/items/{id}/description",
                        status_code=getattr(exc, "status_code", None),
                        attempt=self._config.max_attempts,
                        error_type=exc.__class__.__name__,
                        message=str(exc),
                        occurred_at=self._iso(self._clock()),
                    )
                    append_jsonl(
                        errors_path,
                        {
                            "run_id": run_id,
                            "endpoint": "description",
                            "item_id": item_id,
                            "error_type": exc.__class__.__name__,
                            "message": str(exc),
                        },
                    )
                    state.files.add(str(errors_path.relative_to(workdir)))
                continue
            body = response.json()
            path, _ = atomic_write_json(descriptions_dir / f"{item_id}.json", body)
            state.files.add(str(path.relative_to(workdir)))
            state.descriptions_downloaded += 1

    # -- helpers --------------------------------------------------------

    def _prepare_workdir(self, started_at: datetime, run_id: str) -> Path:
        timestamp = started_at.strftime("%Y-%m-%dT%H%M%SZ")
        workdir = Path(self._config.output_dir) / f"{timestamp}_{run_id[:8]}"
        workdir.mkdir(parents=True, exist_ok=False)
        (workdir / "searches").mkdir()
        (workdir / "items").mkdir()
        (workdir / "descriptions").mkdir()
        (workdir / "errors").mkdir()
        return workdir

    def _iso(self, moment: datetime) -> str:
        return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _build_summary(
        self,
        *,
        run_id: str,
        started_at: datetime,
        finished_at: datetime,
        duration_seconds: float,
        state: _RunState,
        errors_by_status: dict[str, int],
    ) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "status": "completed",
            "started_at": self._iso(started_at),
            "finished_at": self._iso(finished_at),
            "duration_seconds": round(duration_seconds, 3),
            "queries_planned": state.queries_planned,
            "queries_completed": state.queries_completed,
            "queries_failed": state.queries_failed,
            "search_results_received": state.search_results_received,
            "unique_ids_found": len(state.unique_ids),
            "duplicate_ids_across_queries": state.duplicate_ids_across_queries,
            "items_requested": state.items_requested,
            "items_downloaded": state.items_downloaded,
            "items_failed": state.items_failed,
            "descriptions_requested": state.descriptions_requested,
            "descriptions_downloaded": state.descriptions_downloaded,
            "candidate_items": state.candidate_items,
            "excluded_items": state.excluded_items,
            "unknown_items": state.unknown_items,
            "errors_by_status": errors_by_status,
            "field_coverage": {name: cov.as_dict() for name, cov in state.field_coverage.items()},
        }

    def _log_summary(self, summary: dict[str, Any], duration: float) -> None:
        logger.info(
            "Ingesta completada\n"
            "Consultas ejecutadas: %s/%s\n"
            "Resultados recibidos: %s\n"
            "IDs únicos: %s\n"
            "Duplicados entre segmentos: %s\n"
            "Detalles descargados: %s\n"
            "Descripciones descargadas: %s\n"
            "Errores permanentes: %s\n"
            "Candidatos: %s\n"
            "Duración: %s",
            summary["queries_completed"],
            summary["queries_planned"],
            summary["search_results_received"],
            summary["unique_ids_found"],
            summary["duplicate_ids_across_queries"],
            summary["items_downloaded"],
            summary["descriptions_downloaded"],
            sum(summary["errors_by_status"].values()),
            summary["candidate_items"],
            format_duration(duration),
        )
