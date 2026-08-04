"""Source gate for MercadoLibre: decide whether the source is viable.

The gate runs a minimum viable slice of the ingestion pipeline against
MercadoLibre's public API. It probes the search endpoint without a token
first; only if the search returns 401 or 403 and a token is available
will it retry with authentication. It then fetches a 20-item multiget
sample, tries to obtain descriptions, and measures coverage of the
fields the pipeline depends on downstream.

The decision is one of :class:`SourceGateDecision`. The gate never
raises on expected HTTP failures — it records them in the report so the
caller can make an informed decision.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .client import MercadoLibreClient
from .config import IngestionConfig
from .errors import (
    AuthenticationError,
    AuthorizationError,
    HttpError,
    IngestionError,
)
from .filesystem import atomic_write_json
from .models import FieldCoverage, SourceGateDecision, SourceGateReport
from .query_plan import (
    CATEGORY_APARTMENT,
    CATEGORY_HOUSE,
    build_initial_plan,
)

logger = logging.getLogger(__name__)

ESSENTIAL_FIELDS: tuple[str, ...] = (
    "price",
    "currency",
    "location",
    "property_type",
    "operation",
    "bedrooms",
    "surface",
)
SAMPLE_SIZE = 20
MIN_ESSENTIAL_HITS = 16
MIN_DATE_HITS = 16


@dataclass
class SourceGateArtifacts:
    """Filesystem paths produced by the gate for later inspection."""

    search_no_auth: Path | None = None
    search_with_auth: Path | None = None
    items_batch: Path | None = None
    coverage: Path | None = None
    descriptions_dir: Path | None = None
    descriptions_written: list[Path] = field(default_factory=list)


def run_source_gate(
    config: IngestionConfig,
    client: MercadoLibreClient,
    workdir: Path,
) -> tuple[SourceGateReport, SourceGateArtifacts]:
    """Execute the gate and return ``(report, artifacts)``.

    ``workdir`` is where the gate persists the raw responses used to
    justify its decision. It is created if it does not exist.
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    descriptions_dir = workdir / "descriptions"
    descriptions_dir.mkdir(parents=True, exist_ok=True)
    artifacts = SourceGateArtifacts(descriptions_dir=descriptions_dir)
    notes: list[str] = []

    seed_segment = build_initial_plan(site_id=config.site_id)[0]
    search_params = _build_search_params(seed_segment.parameters)

    token_used = False
    search_data: dict[str, Any] | None = None
    reported_total: int | None = None

    try:
        response = client.search_items(config.site_id, params=search_params)
        search_data = _safe_json(response)
        artifacts.search_no_auth, _ = atomic_write_json(
            workdir / "search_no_auth.json", search_data
        )
    except (AuthenticationError, AuthorizationError) as exc:
        notes.append(f"anonymous search returned {exc.status_code}")
        if config.access_token:
            token_used = True
            try:
                response = client.search_items(config.site_id, params=search_params)
                search_data = _safe_json(response)
                artifacts.search_with_auth, _ = atomic_write_json(
                    workdir / "search_with_auth.json", search_data
                )
            except HttpError as auth_exc:
                notes.append(f"authenticated search failed with {auth_exc.status_code}")
        else:
            notes.append("no MELI_ACCESS_TOKEN available for retry")
    except IngestionError as exc:
        notes.append(f"search failed: {exc}")

    if not isinstance(search_data, dict) or not search_data:
        report = SourceGateReport(
            decision=SourceGateDecision.INCONCLUSIVE,
            token_used=token_used,
            sample_size=0,
            notes=notes or ["no search response captured"],
        )
        _write_coverage(workdir, report, artifacts)
        return report, artifacts

    reported_total = _extract_reported_total(search_data)
    available_filters = _extract_filter_ids(search_data.get("available_filters"))

    item_ids = _unique_item_ids(search_data.get("results"))
    if len(item_ids) < SAMPLE_SIZE:
        notes.append(f"only {len(item_ids)} unique IDs from anonymous search (need {SAMPLE_SIZE})")
        decision = SourceGateDecision.INCONCLUSIVE
        report = SourceGateReport(
            decision=decision,
            token_used=token_used,
            sample_size=len(item_ids),
            notes=notes,
            available_filters=available_filters,
            reported_total=reported_total,
        )
        _write_coverage(workdir, report, artifacts)
        return report, artifacts

    sample_ids = item_ids[:SAMPLE_SIZE]

    try:
        multiget_response = client.get_items(sample_ids)
        multiget_data = _safe_json(multiget_response)
    except IngestionError as exc:
        notes.append(f"multiget failed: {exc}")
        report = SourceGateReport(
            decision=SourceGateDecision.INCONCLUSIVE,
            token_used=token_used,
            sample_size=len(sample_ids),
            notes=notes,
            reported_total=reported_total,
            available_filters=available_filters,
        )
        _write_coverage(workdir, report, artifacts)
        return report, artifacts

    artifacts.items_batch, _ = atomic_write_json(workdir / "items_batch_001.json", multiget_data)

    successful_items = _extract_successful_items(multiget_data)
    coverage, date_coverage = _measure_coverage(successful_items)
    categories = sorted(
        {str(item.get("category_id")) for item in successful_items if item.get("category_id")}
    )
    operation_detection = _operation_detection_summary(successful_items)

    description_cov, description_paths = _download_descriptions(
        client, sample_ids, descriptions_dir
    )
    artifacts.descriptions_written = description_paths

    decision = _decide(coverage, date_coverage, sample_ids, notes)

    report = SourceGateReport(
        decision=decision,
        token_used=token_used,
        sample_size=len(sample_ids),
        essential_coverage=coverage,
        date_created_coverage=date_coverage,
        description_coverage=description_cov,
        operation_detection=operation_detection,
        notes=notes,
        categories_observed=categories,
        available_filters=available_filters,
        reported_total=reported_total,
    )
    _write_coverage(workdir, report, artifacts)
    return report, artifacts


# ---- helpers -----------------------------------------------------------


def _build_search_params(segment_params: dict[str, Any]) -> dict[str, Any]:
    """Translate a query segment into MercadoLibre search parameters."""
    params: dict[str, Any] = {"limit": 20, "offset": 0}
    if "category" in segment_params:
        params["category"] = segment_params["category"]
    if "state" in segment_params:
        params["state"] = segment_params["state"]
    # Operation is expressed via q= fallback; the gate reads the observed
    # available_filters to refine attribute-based filtering afterwards.
    parts = []
    if segment_params.get("operation") == "rent":
        parts.append("alquiler")
    if parts:
        params["q"] = " ".join(parts)
    return params


def _safe_json(response: Any) -> Any:
    """Return the parsed JSON body as-is (dict for search/description, list for multiget)."""
    return response.json()


def _extract_reported_total(search_data: dict[str, Any]) -> int | None:
    paging = search_data.get("paging")
    if not isinstance(paging, dict):
        return None
    total = paging.get("total")
    return int(total) if isinstance(total, int) else None


def _extract_filter_ids(available_filters: Any) -> list[str]:
    if not isinstance(available_filters, list):
        return []
    ids: list[str] = []
    for entry in available_filters:
        if isinstance(entry, dict):
            filter_id = entry.get("id")
            if isinstance(filter_id, str):
                ids.append(filter_id)
    return sorted(set(ids))


def _unique_item_ids(results: Any) -> list[str]:
    if not isinstance(results, list):
        return []
    seen: set[str] = set()
    ordered: list[str] = []
    for entry in results:
        if not isinstance(entry, dict):
            continue
        item_id = entry.get("id")
        if isinstance(item_id, str) and item_id not in seen:
            seen.add(item_id)
            ordered.append(item_id)
    return ordered


def _extract_successful_items(multiget_data: Any) -> list[dict[str, Any]]:
    if not isinstance(multiget_data, list):
        return []
    items: list[dict[str, Any]] = []
    for entry in multiget_data:
        if not isinstance(entry, dict):
            continue
        code = entry.get("code")
        body = entry.get("body")
        if code == 200 and isinstance(body, dict):
            items.append(body)
    return items


def _measure_coverage(
    items: list[dict[str, Any]],
) -> tuple[dict[str, FieldCoverage], FieldCoverage]:
    coverage = {field_name: FieldCoverage() for field_name in ESSENTIAL_FIELDS}
    date_coverage = FieldCoverage()
    for item in items:
        for field_name in ESSENTIAL_FIELDS:
            coverage[field_name].total += 1
            if _has_field(item, field_name):
                coverage[field_name].present += 1
        date_coverage.total += 1
        if _valid_date_created(item):
            date_coverage.present += 1
    return coverage, date_coverage


def _has_field(item: dict[str, Any], field_name: str) -> bool:
    if field_name == "price":
        return isinstance(item.get("price"), int | float) and item.get("price") is not None
    if field_name == "currency":
        return bool(item.get("currency_id"))
    if field_name == "location":
        location = item.get("location") or item.get("address")
        if isinstance(location, dict):
            return bool(location.get("state") or location.get("city"))
        return bool(location)
    if field_name == "property_type":
        return _attribute_present(item, "PROPERTY_TYPE") or bool(item.get("category_id"))
    if field_name == "operation":
        return _attribute_present(item, "OPERATION")
    if field_name == "bedrooms":
        return _attribute_present(item, "BEDROOMS") or _attribute_present(item, "ROOMS")
    if field_name == "surface":
        for attribute_id in ("TOTAL_AREA", "COVERED_AREA", "SURFACE_TOTAL"):
            if _attribute_present(item, attribute_id):
                return True
        return False
    return False


def _valid_date_created(item: dict[str, Any]) -> bool:
    value = item.get("date_created")
    if not isinstance(value, str) or len(value) < 10:
        return False
    return value[0].isdigit()


def _attribute_present(item: dict[str, Any], attribute_id: str) -> bool:
    attributes = item.get("attributes")
    if not isinstance(attributes, list):
        return False
    for attribute in attributes:
        if not isinstance(attribute, dict):
            continue
        if attribute.get("id") != attribute_id:
            continue
        for key in ("value_id", "value_name", "value_struct"):
            if attribute.get(key):
                return True
    return False


def _operation_detection_summary(items: list[dict[str, Any]]) -> str:
    modes: set[str] = set()
    for item in items:
        if item.get("category_id") in {CATEGORY_APARTMENT, CATEGORY_HOUSE}:
            modes.add("category")
        if _attribute_present(item, "OPERATION"):
            modes.add("attribute")
    if not modes:
        return "text-only"
    return "+".join(sorted(modes))


def _download_descriptions(
    client: MercadoLibreClient,
    item_ids: list[str],
    descriptions_dir: Path,
) -> tuple[FieldCoverage, list[Path]]:
    coverage = FieldCoverage(total=len(item_ids))
    written: list[Path] = []
    for item_id in item_ids:
        try:
            response = client.get_item_description(item_id)
        except IngestionError as exc:
            logger.info("description unavailable", extra={"item_id": item_id, "error": str(exc)})
            continue
        body = _safe_json(response)
        path, _ = atomic_write_json(descriptions_dir / f"{item_id}.json", body)
        written.append(path)
        if isinstance(body, dict) and (body.get("plain_text") or body.get("text")):
            coverage.present += 1
    return coverage, written


def _decide(
    coverage: dict[str, FieldCoverage],
    date_coverage: FieldCoverage,
    sample_ids: list[str],
    notes: list[str],
) -> SourceGateDecision:
    if len(sample_ids) < SAMPLE_SIZE:
        return SourceGateDecision.INCONCLUSIVE

    essential_hits = min(coverage[field].present for field in ESSENTIAL_FIELDS)
    if essential_hits < MIN_ESSENTIAL_HITS:
        notes.append(
            f"essential coverage {essential_hits}/{SAMPLE_SIZE} below threshold "
            f"{MIN_ESSENTIAL_HITS}"
        )
        return SourceGateDecision.REJECTED

    if date_coverage.present < MIN_DATE_HITS:
        notes.append(
            f"date_created coverage {date_coverage.present}/{SAMPLE_SIZE} below threshold "
            f"{MIN_DATE_HITS}"
        )
        return SourceGateDecision.REJECTED

    return SourceGateDecision.APPROVED


def _write_coverage(
    workdir: Path,
    report: SourceGateReport,
    artifacts: SourceGateArtifacts,
) -> None:
    coverage_path, _ = atomic_write_json(workdir / "coverage.json", report.as_dict())
    artifacts.coverage = coverage_path
