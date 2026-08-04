"""Source gate for MercadoLibre: decide whether the source is viable.

The gate uses **two distinct HTTP clients** — an anonymous one that
never carries an ``Authorization`` header and an optional authenticated
one used only after a ``401``/``403`` on the anonymous call.

Every search probe is persisted as a wrapped
``{request, response}`` document (``search_no_auth.json`` /
``search_with_auth.json``), success or failure. Sanitizer redacts any
bearer token, cookie or other sensitive value.

Category verification walks the site tree hierarchically via
:func:`category_tree.resolve_category_tree`, so the required leaves
(``apartment`` and ``house``) can live several levels below the root.
Ambiguous or missing categories keep the decision at ``INCONCLUSIVE``.

Beyond presence coverage, each of the 20 sampled items is classified
with :func:`classify_sample_item` to check that its structured
operation, property type and location values match the closed scope
(monthly rental of an apartment or house in Montevideo). The gate only
returns ``APPROVED`` when at least 16 of 20 items satisfy the combined
target — separate metrics never substitute for the combined one.

``token_used`` is set the moment the authenticated call is executed,
regardless of whether it succeeded.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .approval import write_approval
from .category_tree import (
    PROPERTY_TYPE_LABELS,
    CategoryResolution,
    normalize_category_name,
    resolve_category_tree,
)
from .client import MercadoLibreClient
from .config import IngestionConfig
from .errors import (
    AuthenticationError,
    AuthorizationError,
    HttpError,
    IngestionError,
)
from .filesystem import atomic_write_json, sanitize_for_artifact
from .models import (
    REQUIRED_PROPERTY_TYPES,
    FieldCoverage,
    SampleItemClassification,
    SourceGateDecision,
    SourceGateReport,
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
MIN_TARGET_HITS = 16

_ALLOWED_MONTHLY_RENTAL_VALUES: frozenset[str] = frozenset(
    {"alquiler", "alquiler mensual", "rent", "monthly rent"}
)
# MercadoLibre attribute value_ids historically observed for the same
# operation. Kept explicit so a live change in the value_id set is easy
# to audit.
_ALLOWED_MONTHLY_RENTAL_VALUE_IDS: frozenset[str] = frozenset({"242075"})
_REJECTED_TEMPORARY_TOKENS: frozenset[str] = frozenset(
    {
        "alquiler temporal",
        "alquiler temporario",
        "temporal",
        "temporada",
        "temporary",
        "temporary rental",
        "vacation rental",
        "short term",
        "short-term rental",
    }
)
_REJECTED_SALE_TOKENS: frozenset[str] = frozenset({"venta", "sale"})
_MONTEVIDEO_ALIASES: frozenset[str] = frozenset({"montevideo"})


@dataclass
class SourceGateArtifacts:
    """Filesystem paths produced by the gate for later inspection."""

    search_no_auth: Path | None = None
    search_with_auth: Path | None = None
    items_batch: Path | None = None
    coverage: Path | None = None
    approval: Path | None = None
    site_categories_root: Path | None = None
    category_tree_summary: Path | None = None
    descriptions_dir: Path | None = None
    descriptions_written: list[Path] = field(default_factory=list)


def run_source_gate(
    config: IngestionConfig,
    anonymous_client: MercadoLibreClient,
    authenticated_client: MercadoLibreClient | None,
    workdir: Path,
) -> tuple[SourceGateReport, SourceGateArtifacts]:
    """Execute the gate and return ``(report, artifacts)``."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    descriptions_dir = workdir / "descriptions"
    descriptions_dir.mkdir(parents=True, exist_ok=True)
    artifacts = SourceGateArtifacts(descriptions_dir=descriptions_dir)
    notes: list[str] = []

    search_endpoint = f"/sites/{config.site_id}/search"
    search_params = _initial_search_params(config)
    known_token = _extract_token(authenticated_client)

    active_client: MercadoLibreClient | None = None
    token_used = False
    search_data: dict[str, Any] | None = None

    anon_attempt = _probe(anonymous_client, config.site_id, search_params, authenticated=False)
    artifacts.search_no_auth = _write_probe_artifact(
        workdir / "search_no_auth.json",
        endpoint=search_endpoint,
        attempt=anon_attempt,
        token=known_token,
    )
    if (
        isinstance(anon_attempt.body, dict)
        and anon_attempt.status_code
        and 200 <= anon_attempt.status_code < 300
    ):
        search_data = anon_attempt.body
        active_client = anonymous_client

    if search_data is None:
        if anon_attempt.status_code in (401, 403):
            notes.append(f"anonymous search returned {anon_attempt.status_code}")
            if authenticated_client is None:
                notes.append("no MELI_ACCESS_TOKEN available for retry")
            else:
                token_used = True
                auth_attempt = _probe(
                    authenticated_client,
                    config.site_id,
                    search_params,
                    authenticated=True,
                )
                artifacts.search_with_auth = _write_probe_artifact(
                    workdir / "search_with_auth.json",
                    endpoint=search_endpoint,
                    attempt=auth_attempt,
                    token=known_token,
                )
                if (
                    auth_attempt.status_code
                    and 200 <= auth_attempt.status_code < 300
                    and isinstance(auth_attempt.body, dict)
                ):
                    search_data = auth_attempt.body
                    active_client = authenticated_client
                else:
                    notes.append(
                        "authenticated search failed with "
                        f"{auth_attempt.status_code or auth_attempt.error_type}"
                    )
        elif anon_attempt.status_code is None:
            notes.append(
                f"anonymous search failed with {anon_attempt.error_type}: "
                f"{anon_attempt.message}"
            )
        else:
            notes.append(f"anonymous search returned {anon_attempt.status_code}")

    if search_data is None or active_client is None:
        return _finalize(
            workdir,
            artifacts,
            SourceGateReport(
                decision=SourceGateDecision.INCONCLUSIVE,
                token_used=token_used,
                sample_size=0,
                notes=notes or ["no usable search response captured"],
            ),
        )

    reported_total = _extract_reported_total(search_data)
    available_filters = _extract_filter_ids(search_data.get("available_filters"))
    item_ids = _unique_item_ids(search_data.get("results"))

    if len(item_ids) < SAMPLE_SIZE:
        notes.append(f"only {len(item_ids)} unique IDs from search (need {SAMPLE_SIZE})")
        return _finalize(
            workdir,
            artifacts,
            SourceGateReport(
                decision=SourceGateDecision.INCONCLUSIVE,
                token_used=token_used,
                sample_size=len(item_ids),
                notes=notes,
                available_filters=available_filters,
                reported_total=reported_total,
            ),
        )

    sample_ids = item_ids[:SAMPLE_SIZE]

    try:
        multiget_response = active_client.get_items(sample_ids)
        multiget_data = multiget_response.json()
    except IngestionError as exc:
        notes.append(f"multiget failed: {exc}")
        return _finalize(
            workdir,
            artifacts,
            SourceGateReport(
                decision=SourceGateDecision.INCONCLUSIVE,
                token_used=token_used,
                sample_size=len(sample_ids),
                notes=notes,
                reported_total=reported_total,
                available_filters=available_filters,
            ),
        )

    artifacts.items_batch, _ = atomic_write_json(
        workdir / "items_batch_001.json",
        sanitize_for_artifact(multiget_data, token=known_token),
    )

    successful_items = _extract_successful_items(multiget_data)
    coverage, date_coverage = _measure_coverage(successful_items)
    categories_seen = sorted(
        {str(item.get("category_id")) for item in successful_items if item.get("category_id")}
    )
    operation_detection = _operation_detection_summary(successful_items)

    resolution = resolve_category_tree(active_client, config.site_id, workdir, token=known_token)
    artifacts.site_categories_root = workdir / "site_categories_root.json"
    artifacts.category_tree_summary = workdir / "category_tree_summary.json"
    notes.extend(resolution.notes)

    classifications = [
        classify_sample_item(item, resolution.verified_category_ids) for item in successful_items
    ]
    (
        operation_value_coverage,
        property_type_value_coverage,
        montevideo_coverage,
        target_valid_coverage,
        classification_reasons,
    ) = _combined_coverages(classifications, sample_size=len(sample_ids))

    description_cov, description_paths = _download_descriptions(
        active_client, sample_ids, descriptions_dir, token=known_token
    )
    artifacts.descriptions_written = description_paths

    decision = _decide(
        coverage=coverage,
        date_coverage=date_coverage,
        sample_ids=sample_ids,
        resolution=resolution,
        target_valid_coverage=target_valid_coverage,
        notes=notes,
    )

    # Only expose the required property types; extras from the resolver
    # never enter the report and therefore never enter the approval.
    verified_required = {
        pt: cid
        for pt, cid in resolution.verified_category_ids.items()
        if pt in REQUIRED_PROPERTY_TYPES
    }

    report = SourceGateReport(
        decision=decision,
        token_used=token_used,
        sample_size=len(sample_ids),
        essential_coverage=coverage,
        date_created_coverage=date_coverage,
        description_coverage=description_cov,
        operation_detection=operation_detection,
        notes=notes,
        categories_observed=categories_seen,
        available_filters=available_filters,
        reported_total=reported_total,
        verified_category_ids=verified_required,
        operation_value_coverage=operation_value_coverage,
        property_type_value_coverage=property_type_value_coverage,
        montevideo_coverage=montevideo_coverage,
        target_valid_coverage=target_valid_coverage,
        classification_reasons=classification_reasons,
        category_tree=resolution.as_dict(),
    )
    return _finalize(workdir, artifacts, report)


# ---- classification -----------------------------------------------------


def classify_sample_item(
    item: dict[str, Any],
    verified_category_ids: dict[str, str],
) -> SampleItemClassification:
    """Return a :class:`SampleItemClassification` for a single MELI item."""
    item_id = item.get("id") if isinstance(item.get("id"), str) else None
    reasons: list[str] = []

    op_value = _attribute_value(item, "OPERATION")
    op_value_id = _attribute_value(item, "OPERATION", key="value_id")
    op_norm = normalize_category_name(op_value) if op_value else ""
    monthly_rental = False
    if not op_value and not op_value_id:
        reasons.append("missing_operation")
        operation = ""
    else:
        operation = op_norm or op_value_id or ""
        if any(token in op_norm for token in _REJECTED_TEMPORARY_TOKENS):
            reasons.append("temporary_rental")
        elif any(token in op_norm for token in _REJECTED_SALE_TOKENS):
            reasons.append("sale")
        elif op_norm in _ALLOWED_MONTHLY_RENTAL_VALUES or (
            isinstance(op_value_id, str) and op_value_id in _ALLOWED_MONTHLY_RENTAL_VALUE_IDS
        ):
            monthly_rental = True
        else:
            reasons.append("unknown_operation")

    verified_by_id = {cid: pt for pt, cid in verified_category_ids.items()}
    raw_category = item.get("category_id") if isinstance(item.get("category_id"), str) else None
    pt_from_category = verified_by_id.get(raw_category) if raw_category else None

    attr_value = _attribute_value(item, "PROPERTY_TYPE")
    attr_norm = normalize_category_name(attr_value) if attr_value else ""
    pt_from_attribute: str | None = None
    for internal, aliases in PROPERTY_TYPE_LABELS.items():
        if attr_norm and attr_norm in aliases:
            pt_from_attribute = internal
            break

    allowed_property_type = False
    if pt_from_category and pt_from_attribute and pt_from_category != pt_from_attribute:
        reasons.append("property_type_conflict")
        property_type = pt_from_category
    elif pt_from_category:
        property_type = pt_from_category
        allowed_property_type = property_type in REQUIRED_PROPERTY_TYPES
    elif pt_from_attribute:
        property_type = pt_from_attribute
        allowed_property_type = property_type in REQUIRED_PROPERTY_TYPES
    else:
        property_type = ""
        reasons.append("property_type_unknown")

    location = item.get("location") or item.get("address") or {}
    state_name = ""
    if isinstance(location, dict):
        state_field = location.get("state") or location.get("state_name")
        if isinstance(state_field, dict):
            state_name = state_field.get("name") or ""
        elif isinstance(state_field, str):
            state_name = state_field
    location_norm = normalize_category_name(state_name) if state_name else ""
    location_valid = location_norm in _MONTEVIDEO_ALIASES
    if not location_valid:
        reasons.append("outside_montevideo" if state_name else "missing_location")

    valid_for_target = monthly_rental and allowed_property_type and location_valid

    return SampleItemClassification(
        item_id=item_id,
        operation=operation,
        property_type=property_type,
        location_valid=location_valid,
        monthly_rental=monthly_rental,
        allowed_property_type=allowed_property_type,
        valid_for_target=valid_for_target,
        reasons=tuple(reasons),
    )


def _combined_coverages(
    classifications: list[SampleItemClassification],
    *,
    sample_size: int,
) -> tuple[FieldCoverage, FieldCoverage, FieldCoverage, FieldCoverage, dict[str, int]]:
    op_cov = FieldCoverage(total=sample_size)
    pt_cov = FieldCoverage(total=sample_size)
    mvd_cov = FieldCoverage(total=sample_size)
    target_cov = FieldCoverage(total=sample_size)
    reasons: dict[str, int] = {}
    for cls in classifications:
        if cls.monthly_rental:
            op_cov.present += 1
        if cls.allowed_property_type:
            pt_cov.present += 1
        if cls.location_valid:
            mvd_cov.present += 1
        if cls.valid_for_target:
            target_cov.present += 1
        for reason in cls.reasons:
            reasons[reason] = reasons.get(reason, 0) + 1
    return op_cov, pt_cov, mvd_cov, target_cov, reasons


# ---- probe capture -----------------------------------------------------


@dataclass
class _ProbeAttempt:
    authenticated: bool
    status_code: int | None
    body: Any = None
    error_type: str | None = None
    message: str | None = None


def _probe(
    client: MercadoLibreClient,
    site_id: str,
    params: dict[str, Any],
    *,
    authenticated: bool,
) -> _ProbeAttempt:
    try:
        response = client.search_items(site_id, params=params)
    except HttpError as exc:
        return _ProbeAttempt(
            authenticated=authenticated,
            status_code=exc.status_code,
            body=exc.response_body,
            error_type=exc.__class__.__name__,
            message=exc.message,
        )
    except IngestionError as exc:
        return _ProbeAttempt(
            authenticated=authenticated,
            status_code=None,
            body=None,
            error_type=exc.__class__.__name__,
            message=str(exc),
        )
    try:
        parsed = response.json()
    except ValueError:
        parsed = None
    return _ProbeAttempt(
        authenticated=authenticated,
        status_code=response.status_code,
        body=parsed,
    )


def _write_probe_artifact(
    path: Path,
    *,
    endpoint: str,
    attempt: _ProbeAttempt,
    token: str | None = None,
) -> Path:
    response: dict[str, Any] = {"status_code": attempt.status_code}
    if attempt.body is not None:
        response["body"] = sanitize_for_artifact(attempt.body, token=token)
    if attempt.error_type is not None:
        response["error_type"] = attempt.error_type
    if attempt.message is not None:
        response["message"] = sanitize_for_artifact(attempt.message, token=token)
    payload = {
        "request": {
            "method": "GET",
            "endpoint": endpoint,
            "authenticated": attempt.authenticated,
        },
        "response": response,
    }
    written, _ = atomic_write_json(path, payload)
    return written


def _extract_token(client: MercadoLibreClient | None) -> str | None:
    if client is None:
        return None
    token = getattr(client._config, "access_token", None)
    return token if isinstance(token, str) and token else None


# ---- search-data helpers -----------------------------------------------


def _initial_search_params(config: IngestionConfig) -> dict[str, Any]:
    return {
        "limit": 20,
        "offset": 0,
        "q": "alquiler",
        "state": "Montevideo",
    }


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


def _attribute_value(
    item: dict[str, Any],
    attribute_id: str,
    *,
    key: str = "value_name",
) -> str | None:
    attributes = item.get("attributes")
    if not isinstance(attributes, list):
        return None
    for attribute in attributes:
        if not isinstance(attribute, dict):
            continue
        if attribute.get(attribute_id) is not None or attribute.get("id") != attribute_id:
            pass
        if attribute.get("id") != attribute_id:
            continue
        value = attribute.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _operation_detection_summary(items: list[dict[str, Any]]) -> str:
    modes: set[str] = set()
    for item in items:
        if item.get("category_id"):
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
    *,
    token: str | None = None,
) -> tuple[FieldCoverage, list[Path]]:
    coverage = FieldCoverage(total=len(item_ids))
    written: list[Path] = []
    for item_id in item_ids:
        try:
            response = client.get_item_description(item_id)
        except IngestionError as exc:
            logger.info("description unavailable", extra={"item_id": item_id, "error": str(exc)})
            continue
        body = response.json()
        path, _ = atomic_write_json(
            descriptions_dir / f"{item_id}.json",
            sanitize_for_artifact(body, token=token),
        )
        written.append(path)
        if isinstance(body, dict) and (body.get("plain_text") or body.get("text")):
            coverage.present += 1
    return coverage, written


def _decide(
    *,
    coverage: dict[str, FieldCoverage],
    date_coverage: FieldCoverage,
    sample_ids: list[str],
    resolution: CategoryResolution,
    target_valid_coverage: FieldCoverage,
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

    if resolution.limits_exceeded:
        notes.append("cannot approve: category tree walk exceeded defensive limits")
        return SourceGateDecision.INCONCLUSIVE
    if resolution.ambiguous_property_types:
        notes.append(
            "cannot approve: ambiguous categories for "
            f"{', '.join(resolution.ambiguous_property_types)}"
        )
        return SourceGateDecision.INCONCLUSIVE
    missing = sorted(REQUIRED_PROPERTY_TYPES - resolution.verified_category_ids.keys())
    if missing:
        notes.append(
            "cannot approve: required property categories not verified: " f"{', '.join(missing)}"
        )
        return SourceGateDecision.INCONCLUSIVE

    if target_valid_coverage.present < MIN_TARGET_HITS:
        notes.append(
            f"combined target coverage {target_valid_coverage.present}/{SAMPLE_SIZE} below "
            f"threshold {MIN_TARGET_HITS}"
        )
        return SourceGateDecision.REJECTED

    return SourceGateDecision.APPROVED


def _finalize(
    workdir: Path,
    artifacts: SourceGateArtifacts,
    report: SourceGateReport,
) -> tuple[SourceGateReport, SourceGateArtifacts]:
    coverage_path, coverage_sha = atomic_write_json(workdir / "coverage.json", report.as_dict())
    artifacts.coverage = coverage_path

    if report.decision is SourceGateDecision.APPROVED and REQUIRED_PROPERTY_TYPES.issubset(
        report.verified_category_ids.keys()
    ):
        artifacts.approval = write_approval(
            workdir,
            report=report,
            coverage_path=coverage_path,
            coverage_sha256=coverage_sha,
        )
    return report, artifacts


# Keep AuthenticationError / AuthorizationError referenced so linters see
# them being used even though the probe helper handles both via the
# HttpError base class.
_ = (AuthenticationError, AuthorizationError)
