"""Source gate for MercadoLibre: decide whether the source is viable.

The gate probes MercadoLibre with **two distinct HTTP clients**: an
anonymous one that never carries an ``Authorization`` header, and an
optional authenticated one that only runs if the anonymous probe hits
``401``/``403`` and a token was made available by the caller. Neither
client's session is reused across roles, so the anonymous evidence
cannot be contaminated by a stale bearer token.

Every search probe — success, 401/403, or transport error — is
persisted as a wrapped ``{request, response}`` artifact under
``search_no_auth.json`` / ``search_with_auth.json``. The artifacts are
sanitized before writing so tokens can never leak.

``token_used`` is set the moment the authenticated call is *executed*,
regardless of whether it succeeded, so the report faithfully answers
"did the pipeline actually send a bearer token?".

When the gate reaches ``APPROVED`` it also emits
``source_gate_approval.json`` which the ingestion CLI will require. The
gate can only approve when **both** required property categories
(``apartment`` and ``house``) were verified against the live site tree.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .approval import write_approval
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

# Maps the *internal* property_type key (never translated) to the set of
# lowercase MercadoLibre category names that identify it.
PROPERTY_TYPE_LABELS: dict[str, tuple[str, ...]] = {
    "apartment": ("apartamento", "apartamentos", "apartment", "apartments"),
    "house": ("casa", "casas", "house", "houses"),
}


@dataclass
class SourceGateArtifacts:
    """Filesystem paths produced by the gate for later inspection."""

    search_no_auth: Path | None = None
    search_with_auth: Path | None = None
    items_batch: Path | None = None
    coverage: Path | None = None
    approval: Path | None = None
    site_categories: Path | None = None
    descriptions_dir: Path | None = None
    descriptions_written: list[Path] = field(default_factory=list)


def run_source_gate(
    config: IngestionConfig,
    anonymous_client: MercadoLibreClient,
    authenticated_client: MercadoLibreClient | None,
    workdir: Path,
) -> tuple[SourceGateReport, SourceGateArtifacts]:
    """Execute the gate and return ``(report, artifacts)``.

    ``anonymous_client`` is always used first. ``authenticated_client``
    is invoked only when the anonymous probe returned ``401`` or ``403``
    and it is not ``None`` — the caller is responsible for constructing
    it with the correct config.
    """
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
    reported_total: int | None = None

    anon_attempt = _probe(anonymous_client, config.site_id, search_params, authenticated=False)
    artifacts.search_no_auth = _write_probe_artifact(
        workdir / "search_no_auth.json",
        endpoint=search_endpoint,
        attempt=anon_attempt,
        token=known_token,
    )
    # Anonymous body is only trusted as ingestion input when it came from
    # a 2xx response; error bodies are evidence, not signal.
    if (
        isinstance(anon_attempt.body, dict)
        and anon_attempt.status_code
        and 200 <= anon_attempt.status_code < 300
    ):
        search_data = anon_attempt.body
        active_client = anonymous_client

    if search_data is None:
        # Anonymous probe did not deliver a usable body. Decide whether
        # to escalate to the authenticated client.
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
    categories = sorted(
        {str(item.get("category_id")) for item in successful_items if item.get("category_id")}
    )
    operation_detection = _operation_detection_summary(successful_items)

    verified_category_ids, category_notes = _verify_category_ids(
        active_client, config.site_id, workdir, artifacts, token=known_token
    )
    notes.extend(category_notes)

    description_cov, description_paths = _download_descriptions(
        active_client, sample_ids, descriptions_dir, token=known_token
    )
    artifacts.descriptions_written = description_paths

    decision = _decide(
        coverage=coverage,
        date_coverage=date_coverage,
        sample_ids=sample_ids,
        verified_category_ids=verified_category_ids,
        notes=notes,
    )

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
        verified_category_ids=verified_category_ids,
    )
    return _finalize(workdir, artifacts, report)


# ---- probe capture -----------------------------------------------------


@dataclass
class _ProbeAttempt:
    """Snapshot of a single HTTP probe suitable for on-disk evidence."""

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
    """Run a search call and return a probe attempt, never re-raising."""
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
    """Persist an :class:`_ProbeAttempt` as a wrapped ``{request, response}``."""
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


def _verify_category_ids(
    client: MercadoLibreClient,
    site_id: str,
    workdir: Path,
    artifacts: SourceGateArtifacts,
    *,
    token: str | None = None,
) -> tuple[dict[str, str], list[str]]:
    """Return the verified property_type→category_id mapping."""
    notes: list[str] = []
    try:
        response = client.get_site_categories(site_id)
        categories = response.json()
    except IngestionError as exc:
        notes.append(f"failed to fetch /sites/{site_id}/categories: {exc}")
        return {}, notes

    artifacts.site_categories, _ = atomic_write_json(
        workdir / "site_categories.json",
        sanitize_for_artifact(categories, token=token),
    )

    if not isinstance(categories, list):
        notes.append("site categories response was not a JSON list")
        return {}, notes

    label_to_id: dict[str, str] = {}
    for entry in categories:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        cid = entry.get("id")
        if isinstance(name, str) and isinstance(cid, str):
            label_to_id[name.strip().lower()] = cid

    verified: dict[str, str] = {}
    for property_type, labels in PROPERTY_TYPE_LABELS.items():
        for label in labels:
            if label in label_to_id:
                verified[property_type] = label_to_id[label]
                break

    missing = sorted(REQUIRED_PROPERTY_TYPES - set(verified))
    if missing:
        notes.append(f"required categories not verified: {', '.join(missing)}")
    return verified, notes


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
    verified_category_ids: dict[str, str],
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

    missing_categories = sorted(REQUIRED_PROPERTY_TYPES - verified_category_ids.keys())
    if missing_categories:
        notes.append(
            "cannot approve: required property categories not verified: "
            f"{', '.join(missing_categories)}"
        )
        return SourceGateDecision.INCONCLUSIVE

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


# Keep AuthenticationError / AuthorizationError references so linters see
# them being used even though the probe helper handles both via the
# HttpError base class.
_ = (AuthenticationError, AuthorizationError)
