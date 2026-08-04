"""Orchestrator that turns raw ingestion runs into ETL Parquet datasets."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from .config import EtlConfig
from .contracts import RawRunContract, load_raw_run
from .currency import (
    ExchangeRate,
    convert_common_expenses,
    convert_price_to_usd,
    ensure_mode_consistent,
    load_exchange_rate,
)
from .deduplication import content_hash, possible_duplicate_key
from .extractors import (
    AREA_ATTRIBUTE_IDS,
    ATTRIBUTE_MAP,
    BOOLEAN_ATTRIBUTES,
    attribute_value,
    index_attributes,
    known_attribute_ids,
    parse_area,
    parse_bool,
    parse_plain_number,
)
from .lineage import build_input_hashes, build_lineage, file_sha256
from .loaders import iter_raw_items
from .models import (
    CANONICAL_COLUMN_ORDER,
    DUPLICATE_CANDIDATE_COLUMN_ORDER,
    ETL_SCHEMA_VERSION,
    MODEL_READY_FORBIDDEN_COLUMNS,
    MODEL_READY_REQUIRED_COLUMNS,
    REJECTED_COLUMN_ORDER,
    CanonicalRow,
    ExtractedItem,
    RowRejection,
)
from .neighborhoods import NeighborhoodAliases, load_aliases
from .normalization import normalize_text
from .quality import build_quality_report
from .schemas import (
    CanonicalListingsSchema,
    DuplicateCandidatesSchema,
    ModelReadySchema,
    RejectedListingsSchema,
    check_model_ready_leakage,
)
from .source_scope import classify_location
from .writers import write_json, write_parquet

# Anchored to the repository root via this file's location instead of the
# current working directory, so the CLI works from anywhere.
_REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_ROOT_MARKER = _REPO_ROOT / "tests" / "fixtures"


class StrictQualityGateError(RuntimeError):
    """Raised when ``--strict`` finds any quality signal in the run."""

    def __init__(
        self,
        *,
        rejected_items: int,
        unmapped_attributes: int,
        invalid_dates: int,
        area_inconsistencies: int,
        rows_with_quality_issues: int,
        unsupported_common_expenses: int,
    ) -> None:
        self.rejected_items = rejected_items
        self.unmapped_attributes = unmapped_attributes
        self.invalid_dates = invalid_dates
        self.area_inconsistencies = area_inconsistencies
        self.rows_with_quality_issues = rows_with_quality_issues
        self.unsupported_common_expenses = unsupported_common_expenses
        super().__init__(
            "strict quality gate failed: "
            f"rejected={rejected_items} unmapped_attrs={unmapped_attributes} "
            f"invalid_dates={invalid_dates} area_inconsistencies={area_inconsistencies} "
            f"rows_with_quality_issues={rows_with_quality_issues} "
            f"unsupported_common_expenses={unsupported_common_expenses}"
        )


@dataclass
class EtlResult:
    etl_run_id: str
    workdir: Path
    canonical: pd.DataFrame
    model_ready: pd.DataFrame
    rejected: pd.DataFrame
    duplicate_candidates: pd.DataFrame
    summary: dict[str, Any]


class EtlPipeline:
    """One-shot orchestrator. Instantiate, ``.run()``, discard."""

    def __init__(
        self,
        config: EtlConfig,
        *,
        verified_category_ids: dict[str, str] | None = None,
    ) -> None:
        self._config = config
        self._verified_category_ids = dict(verified_category_ids or {})
        self._exchange_rate: ExchangeRate | None = None
        self._aliases: NeighborhoodAliases | None = None

    # ---- entry points -------------------------------------------------

    def dry_run(self) -> dict[str, Any]:
        rate = load_exchange_rate(self._config.exchange_rate_path)
        ensure_mode_consistent(rate, self._config.data_mode)
        self._exchange_rate = rate
        self._aliases = load_aliases(self._config.neighborhood_aliases_path)
        runs = self._load_runs()

        input_hashes, input_count = build_input_hashes(runs)
        return {
            "dry_run": True,
            "data_mode": self._config.data_mode,
            "strict": self._config.strict,
            "input_runs": [str(run.run_directory.name) for run in runs],
            "input_batch_count": sum(len(run.item_batch_paths) for run in runs),
            "input_description_count": sum(len(run.description_paths) for run in runs),
            "input_file_count": input_count,
            "input_file_sha256": input_hashes,
            "exchange_rate_uyu_per_usd": str(rate.uyu_per_usd),
            "exchange_rate_source": rate.source,
            "exchange_rate_data_mode": rate.data_mode,
            "exchange_rate_sha256": file_sha256(self._config.exchange_rate_path),
            "neighborhood_aliases_sha256": file_sha256(self._config.neighborhood_aliases_path),
            "gate_approval_sha256": file_sha256(self._config.gate_approval_path),
            "output_dir": str(self._config.output_dir),
        }

    def run(self) -> EtlResult:
        started_at = datetime.now(UTC)
        etl_run_id = uuid.uuid4().hex
        rate = load_exchange_rate(self._config.exchange_rate_path)
        ensure_mode_consistent(rate, self._config.data_mode)
        self._exchange_rate = rate
        self._aliases = load_aliases(self._config.neighborhood_aliases_path)
        runs = self._load_runs()

        canonical_rows: list[dict[str, Any]] = []
        rejections: list[RowRejection] = []
        unmapped_counter: Counter[str] = Counter()
        area_inconsistencies = 0
        invalid_dates = 0
        common_expenses_missing = 0
        unsupported_common_expenses = 0
        input_items = 0
        parsed_items = 0

        for run in runs:
            for extracted in iter_raw_items(run):
                input_items += 1
                if not extracted.source_item_id:
                    rejections.append(_build_rejection(extracted, ("missing_item_id",)))
                    continue
                if not extracted.body:
                    rejections.append(_build_rejection(extracted, ("invalid_item_envelope",)))
                    continue
                parsed_items += 1
                canonical, row_rejection, per_row_stats = self._transform_item(
                    extracted, run, started_at
                )
                unmapped_counter.update(per_row_stats.unmapped_attributes)
                area_inconsistencies += per_row_stats.area_inconsistencies
                invalid_dates += per_row_stats.invalid_dates
                if per_row_stats.common_expenses_missing:
                    common_expenses_missing += 1
                if per_row_stats.unsupported_common_expenses:
                    unsupported_common_expenses += 1
                if row_rejection is not None:
                    rejections.append(row_rejection)
                elif canonical is not None:
                    canonical_rows.append(canonical)

        canonical_df = self._assemble_canonical(canonical_rows)
        rejected_df = self._assemble_rejected(rejections)
        duplicate_df = self._assemble_duplicates(canonical_df)
        model_ready_df = self._assemble_model_ready(canonical_df)

        self._validate_schemas(canonical_df, model_ready_df, rejected_df, duplicate_df)

        rows_with_quality_issues = _count_rows_with_issues(canonical_df)
        if self._config.strict:
            self._enforce_strict(
                rejected=len(rejected_df),
                unmapped=sum(unmapped_counter.values()),
                invalid_dates=invalid_dates,
                area_inconsistencies=area_inconsistencies,
                rows_with_quality_issues=rows_with_quality_issues,
                unsupported_common_expenses=unsupported_common_expenses,
            )

        finished_at = datetime.now(UTC)
        workdir_final = self._final_workdir_path(started_at, etl_run_id)
        workdir_tmp = workdir_final.with_suffix(workdir_final.suffix + ".tmp")
        if workdir_tmp.exists():
            shutil.rmtree(workdir_tmp)
        workdir_tmp.mkdir(parents=True, exist_ok=False)

        try:
            outputs = {
                "listings": write_parquet(
                    canonical_df, workdir_tmp / "listings.parquet", sort_by="source_item_id"
                ),
                "model_ready": write_parquet(
                    model_ready_df,
                    workdir_tmp / "model_ready.parquet",
                    sort_by="source_item_id",
                ),
                "rejected_listings": write_parquet(
                    rejected_df,
                    workdir_tmp / "rejected_listings.parquet",
                    sort_by="source_item_id",
                ),
                "duplicate_candidates": write_parquet(
                    duplicate_df,
                    workdir_tmp / "duplicate_candidates.parquet",
                    sort_by="possible_duplicate_group_id",
                ),
            }

            quality_report = build_quality_report(
                canonical=canonical_df,
                model_ready=model_ready_df,
                rejected=rejected_df,
                duplicate_candidates=duplicate_df,
                input_items=input_items,
                parsed_items=parsed_items,
                unmapped_attribute_counts=dict(unmapped_counter),
                area_inconsistencies=area_inconsistencies,
                invalid_dates=invalid_dates,
                common_expenses_missing=common_expenses_missing,
                data_mode=self._config.data_mode,
            )
            outputs["data_quality_report"] = write_json(
                quality_report, workdir_tmp / "data_quality_report.json"
            )
            outputs["unmapped_attributes"] = write_json(
                dict(unmapped_counter), workdir_tmp / "unmapped_attributes.json"
            )

            row_counts = {
                "canonical": int(len(canonical_df)),
                "model_ready": int(len(model_ready_df)),
                "rejected": int(len(rejected_df)),
                "duplicate_candidates": int(len(duplicate_df)),
            }
            summary = {
                "etl_run_id": etl_run_id,
                "status": "completed",
                "data_mode": self._config.data_mode,
                "schema_version": ETL_SCHEMA_VERSION,
                "strict": self._config.strict,
                "input_runs": len(runs),
                "input_items": input_items,
                "canonical_items": row_counts["canonical"],
                "model_ready_items": row_counts["model_ready"],
                "rejected_items": row_counts["rejected"],
                "duplicate_candidates": row_counts["duplicate_candidates"],
                "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
                "started_at": _iso(started_at),
                "finished_at": _iso(finished_at),
            }
            outputs["etl_summary"] = write_json(summary, workdir_tmp / "etl_summary.json")

            schema_snapshot = {
                "schema_version": ETL_SCHEMA_VERSION,
                "canonical_columns": list(CANONICAL_COLUMN_ORDER),
                "model_ready_required": list(MODEL_READY_REQUIRED_COLUMNS),
                "model_ready_forbidden": list(MODEL_READY_FORBIDDEN_COLUMNS),
            }
            outputs["schema"] = write_json(schema_snapshot, workdir_tmp / "schema.json")

            lineage = build_lineage(
                etl_run_id=etl_run_id,
                etl_schema_version=ETL_SCHEMA_VERSION,
                data_mode=self._config.data_mode,
                started_at=_iso(started_at),
                finished_at=_iso(finished_at),
                runs=runs,
                gate_approval_path=self._config.gate_approval_path,
                exchange_rate_path=self._config.exchange_rate_path,
                neighborhood_aliases_path=self._config.neighborhood_aliases_path,
                output_files=outputs,
                row_counts=row_counts,
            )
            outputs["lineage"] = write_json(lineage, workdir_tmp / "lineage.json")
        except Exception:
            shutil.rmtree(workdir_tmp, ignore_errors=True)
            raise

        # Atomic publication.
        workdir_final.parent.mkdir(parents=True, exist_ok=True)
        workdir_tmp.rename(workdir_final)

        return EtlResult(
            etl_run_id=etl_run_id,
            workdir=workdir_final,
            canonical=canonical_df,
            model_ready=model_ready_df,
            rejected=rejected_df,
            duplicate_candidates=duplicate_df,
            summary=summary,
        )

    # ---- helpers ------------------------------------------------------

    def _load_runs(self) -> list[RawRunContract]:
        contracts: list[RawRunContract] = []
        for run_path in self._config.input_run_dirs:
            contracts.append(
                load_raw_run(
                    run_path,
                    data_mode=self._config.data_mode,
                    fixtures_root=FIXTURES_ROOT_MARKER,
                )
            )
        return contracts

    def _transform_item(
        self,
        extracted: ExtractedItem,
        run: RawRunContract,
        etl_processed_at: datetime,
    ) -> tuple[dict[str, Any] | None, RowRejection | None, _PerRowStats]:
        row = CanonicalRow()
        body = extracted.body
        attributes = index_attributes(body)
        stats = _PerRowStats()

        from .extractors import extract_scope

        operation, property_type, reasons = extract_scope(body, self._verified_category_ids)
        montevideo, location_reason = classify_location(body)
        if location_reason:
            reasons.append(location_reason)

        price_original = _coerce_number(body.get("price"))
        currency_original = _coerce_string(body.get("currency_id"))
        price_usd, price_error = convert_price_to_usd(
            price_original,
            currency_original,
            self._exchange_rate,  # type: ignore[arg-type]
        )
        if price_error:
            reasons.append(price_error)

        raw_common = _lookup_attribute(attributes, "COMMON_EXPENSES")
        common_expenses = convert_common_expenses(
            raw_common[0],
            raw_common[1],
            self._exchange_rate,  # type: ignore[arg-type]
            listing_currency=currency_original,
        )
        if not common_expenses["common_expenses_reported"]:
            stats.common_expenses_missing = True

        if reasons:
            return (
                None,
                _build_rejection(
                    extracted,
                    tuple(dict.fromkeys(reasons)),
                    raw_category_id=_coerce_string(body.get("category_id")),
                    raw_currency=currency_original,
                    raw_price=_decimal_to_float(price_original),
                    raw_operation=_attribute_value_str(attributes, "OPERATION"),
                    raw_property_type=_attribute_value_str(attributes, "PROPERTY_TYPE"),
                ),
                stats,
            )

        for attribute_id, column in ATTRIBUTE_MAP.items():
            if attribute_id == "COMMON_EXPENSES":
                continue
            parser = parse_area if attribute_id in AREA_ATTRIBUTE_IDS else parse_plain_number
            value, error = parser(attribute_value(attributes.get(attribute_id)))
            if error:
                row.add_issue(column, error)
            row.set(column, value)

        for attribute_id, column in BOOLEAN_ATTRIBUTES.items():
            row.set(column, parse_bool(attribute_value(attributes.get(attribute_id))))

        total_area = row.columns.get("total_area_m2")
        covered_area = row.columns.get("covered_area_m2")
        total_area_derived = False
        if total_area is None and covered_area is not None:
            total_area = covered_area
            total_area_derived = True
        if total_area is not None and covered_area is not None and covered_area > total_area:
            row.add_issue("total_area_m2", "covered_area_greater_than_total")
            stats.area_inconsistencies += 1
        row.set("total_area_m2", total_area)
        row.set("total_area_derived_from_covered", total_area_derived)

        location = body.get("location") or body.get("address") or {}
        department = "Montevideo" if montevideo else None
        city_name = None
        neighborhood_raw = None
        if isinstance(location, dict):
            city = location.get("city")
            if isinstance(city, dict):
                city_name = normalize_text(city.get("name"))
            elif isinstance(city, str):
                city_name = normalize_text(city)
            neighborhood = location.get("neighborhood")
            if isinstance(neighborhood, dict):
                neighborhood_raw = normalize_text(neighborhood.get("name"))
            elif isinstance(neighborhood, str):
                neighborhood_raw = normalize_text(neighborhood)
        aliases = self._aliases or NeighborhoodAliases()
        neighborhood_normalized, neighborhood_known = aliases.resolve(neighborhood_raw)

        date_created, invalid = _parse_date(body.get("date_created"))
        if invalid:
            row.add_issue("date_created", invalid)
            if invalid == "invalid_date":
                stats.invalid_dates += 1
        last_updated, invalid_last = _parse_date(body.get("last_updated"))
        if invalid_last:
            row.add_issue("last_updated", invalid_last)

        row.set("schema_version", ETL_SCHEMA_VERSION)
        row.set("data_mode", self._config.data_mode)
        row.set("source", run.source)
        row.set("source_run_id", run.run_id)
        row.set("source_item_id", extracted.source_item_id)
        row.set("raw_item_path", f"{run.run_directory.name}/{extracted.raw_item_path}")
        row.set(
            "raw_description_path",
            (
                f"{run.run_directory.name}/{extracted.raw_description_path}"
                if extracted.raw_description_path
                else None
            ),
        )
        row.set("listing_url", _coerce_string(body.get("permalink")))
        row.set("title", normalize_text(body.get("title")))
        description_body = extracted.description_body or {}
        description_text = normalize_text(
            description_body.get("plain_text") or description_body.get("text")
        )
        row.set("description", description_text)
        row.set("description_reported", extracted.raw_description_path is not None)
        row.set("date_created", date_created)
        row.set("last_updated", last_updated)
        row.set("operation", operation)
        row.set("property_type", property_type)
        row.set("department", department)
        row.set("city", city_name)
        row.set("neighborhood_raw", neighborhood_raw)
        row.set("neighborhood_normalized", neighborhood_normalized)
        row.set("neighborhood_known", neighborhood_known)
        if isinstance(location, dict):
            row.set("latitude", _coerce_number(location.get("latitude")))
            row.set("longitude", _coerce_number(location.get("longitude")))
        else:
            row.set("latitude", None)
            row.set("longitude", None)
        row.set("price_original", _decimal_to_float(price_original))
        row.set("currency_original", currency_original)
        row.set("price_usd", _decimal_to_float(price_usd))
        row.set(
            "common_expenses_original",
            _decimal_to_float(common_expenses["common_expenses_original"]),
        )
        row.set("common_expenses_currency", common_expenses["common_expenses_currency"])
        row.set("common_expenses_usd", _decimal_to_float(common_expenses["common_expenses_usd"]))
        row.set("common_expenses_reported", common_expenses["common_expenses_reported"])
        row.set(
            "common_expenses_currency_inferred",
            common_expenses["common_expenses_currency_inferred"],
        )
        if row.columns.get("common_expenses_currency") and (
            row.columns.get("common_expenses_usd") is None
        ):
            row.add_issue("common_expenses_usd", "unsupported_currency")
            stats.unsupported_common_expenses = True
        row.set(
            "total_monthly_cost_usd",
            _sum_optional(price_usd, common_expenses["common_expenses_usd"]),
        )
        row.set("exchange_rate_uyu_per_usd", float(self._exchange_rate.uyu_per_usd))  # type: ignore[union-attr]
        row.set(
            "exchange_rate_date",
            self._exchange_rate.effective_date.isoformat(),  # type: ignore[union-attr]
        )
        row.set(
            "exchange_rate_source",
            self._exchange_rate.source,  # type: ignore[union-attr]
        )
        row.set("first_seen_at", extracted.first_seen_at)
        row.set("last_seen_at", extracted.last_seen_at)
        row.set("observations_count", 1)
        row.set("possible_duplicate_group_id", None)
        row.set("exact_content_hash", None)
        row.set("etl_processed_at", etl_processed_at)
        row.set(
            "quality_issues",
            json.dumps(
                [issue.as_dict() for issue in row.quality_issues],
                ensure_ascii=False,
                sort_keys=True,
            ),
        )

        unknown_attrs = set(attributes) - known_attribute_ids()
        for attribute_id in unknown_attrs:
            stats.unmapped_attributes[attribute_id] += 1

        return row.columns, None, stats

    def _assemble_canonical(self, rows: Iterable[dict[str, Any]]) -> pd.DataFrame:
        rows_list = list(rows)
        if not rows_list:
            return pd.DataFrame(columns=list(CANONICAL_COLUMN_ORDER))
        df = pd.DataFrame(rows_list)
        for column in CANONICAL_COLUMN_ORDER:
            if column not in df.columns:
                df[column] = pd.NA
        df = df[list(CANONICAL_COLUMN_ORDER)]

        # Aggregate first/last seen and count per (source, source_item_id) BEFORE
        # selecting a canonical row. Otherwise the selected row would drop the
        # earliest observation timestamp we ever saw.
        agg = (
            df.groupby(["source", "source_item_id"], dropna=False)
            .agg(
                agg_first_seen=("first_seen_at", "min"),
                agg_last_seen=("last_seen_at", "max"),
                agg_count=("source_item_id", "size"),
            )
            .reset_index()
        )

        # Canonical row selection: max(last_updated) → max(last_seen_at) →
        # max(source_run_id) → max(raw_item_path). All ascending sorts then
        # keep="last" pop the winner deterministically.
        df = df.sort_values(
            by=["last_updated", "last_seen_at", "source_run_id", "raw_item_path"],
            ascending=[True, True, True, True],
            na_position="first",
            kind="stable",
        )
        df = df.drop_duplicates(subset=["source", "source_item_id"], keep="last")
        df = df.merge(agg, on=["source", "source_item_id"], how="left")
        df["first_seen_at"] = df["agg_first_seen"]
        df["last_seen_at"] = df["agg_last_seen"]
        df["observations_count"] = df["agg_count"].astype("Int64")
        df = df.drop(columns=["agg_first_seen", "agg_last_seen", "agg_count"])

        df["exact_content_hash"] = df.apply(lambda row: content_hash(row.to_dict()), axis=1)
        df["possible_duplicate_group_id"] = df.apply(
            lambda row: possible_duplicate_key(row.to_dict()), axis=1
        )
        return df.sort_values(by="source_item_id", kind="stable").reset_index(drop=True)

    def _assemble_rejected(self, rejections: list[RowRejection]) -> pd.DataFrame:
        if not rejections:
            return pd.DataFrame(columns=list(REJECTED_COLUMN_ORDER))
        records = [
            {
                "source_item_id": rejection.source_item_id,
                "source_run_id": rejection.source_run_id,
                "raw_item_path": rejection.raw_item_path,
                "rejection_reasons": "|".join(rejection.reasons),
                "raw_category_id": rejection.raw_category_id,
                "raw_currency": rejection.raw_currency,
                "raw_price": rejection.raw_price,
                "raw_operation": rejection.raw_operation,
                "raw_property_type": rejection.raw_property_type,
            }
            for rejection in rejections
        ]
        return pd.DataFrame(records, columns=list(REJECTED_COLUMN_ORDER))

    def _assemble_duplicates(self, canonical: pd.DataFrame) -> pd.DataFrame:
        if canonical.empty or "possible_duplicate_group_id" not in canonical.columns:
            return pd.DataFrame(columns=list(DUPLICATE_CANDIDATE_COLUMN_ORDER))
        grouped = canonical.dropna(subset=["possible_duplicate_group_id"]).groupby(
            "possible_duplicate_group_id"
        )
        rows: list[dict[str, Any]] = []
        for group_id, frame in grouped:
            if len(frame) < 2:
                continue
            for _, row in frame.iterrows():
                rows.append(
                    {
                        "possible_duplicate_group_id": group_id,
                        "source_item_id": row["source_item_id"],
                        "property_type": row.get("property_type"),
                        "neighborhood_normalized": row.get("neighborhood_normalized"),
                        "bedrooms": row.get("bedrooms"),
                        "total_area_m2_bucket": _bucketed_area(row.get("total_area_m2")),
                        "price_usd_bucket": _bucketed_price(row.get("price_usd")),
                        "member_count": int(len(frame)),
                    }
                )
        if not rows:
            return pd.DataFrame(columns=list(DUPLICATE_CANDIDATE_COLUMN_ORDER))
        return pd.DataFrame(rows, columns=list(DUPLICATE_CANDIDATE_COLUMN_ORDER))

    def _assemble_model_ready(self, canonical: pd.DataFrame) -> pd.DataFrame:
        if canonical.empty:
            return pd.DataFrame(columns=list(MODEL_READY_REQUIRED_COLUMNS))
        required = list(MODEL_READY_REQUIRED_COLUMNS)
        df = canonical.copy()
        for column in required:
            df = df[df[column].notna()]
        df = df[df["total_area_m2"] > 0]
        conflict_mask = df["quality_issues"].str.contains(
            "covered_area_greater_than_total", na=False
        ) | df["quality_issues"].str.contains("unsupported_area_unit", na=False)
        df = df[~conflict_mask]
        df = df[[*required, "bathrooms"]]
        df["bedrooms"] = df["bedrooms"].astype("Int64")
        df["bathrooms"] = df["bathrooms"].astype("Int64")
        df["total_area_m2"] = df["total_area_m2"].astype("Float64")
        df["price_usd"] = df["price_usd"].astype("Float64")
        df["date_created"] = pd.to_datetime(df["date_created"], utc=True)
        check_model_ready_leakage(list(df.columns))
        return df.sort_values(by="source_item_id", kind="stable").reset_index(drop=True)

    def _validate_schemas(
        self,
        canonical: pd.DataFrame,
        model_ready: pd.DataFrame,
        rejected: pd.DataFrame,
        duplicate_candidates: pd.DataFrame,
    ) -> None:
        if not canonical.empty:
            CanonicalListingsSchema.validate(canonical, lazy=True)
        if not model_ready.empty:
            if str(model_ready["date_created"].dtype) != "datetime64[ns, UTC]":
                raise ValueError("model_ready date_created must be UTC-aware")
            ModelReadySchema.validate(model_ready, lazy=True)
        if not rejected.empty:
            RejectedListingsSchema.validate(rejected, lazy=True)
        if not duplicate_candidates.empty:
            DuplicateCandidatesSchema.validate(duplicate_candidates, lazy=True)

    def _final_workdir_path(self, started_at: datetime, etl_run_id: str) -> Path:
        timestamp = started_at.strftime("%Y-%m-%dT%H%M%SZ")
        return Path(self._config.output_dir) / f"{timestamp}_{etl_run_id[:8]}"

    def _enforce_strict(
        self,
        *,
        rejected: int,
        unmapped: int,
        invalid_dates: int,
        area_inconsistencies: int,
        rows_with_quality_issues: int,
        unsupported_common_expenses: int,
    ) -> None:
        if any(
            (
                rejected,
                unmapped,
                invalid_dates,
                area_inconsistencies,
                rows_with_quality_issues,
                unsupported_common_expenses,
            )
        ):
            raise StrictQualityGateError(
                rejected_items=rejected,
                unmapped_attributes=unmapped,
                invalid_dates=invalid_dates,
                area_inconsistencies=area_inconsistencies,
                rows_with_quality_issues=rows_with_quality_issues,
                unsupported_common_expenses=unsupported_common_expenses,
            )


@dataclass
class _PerRowStats:
    unmapped_attributes: Counter[str] = None  # type: ignore[assignment]
    area_inconsistencies: int = 0
    invalid_dates: int = 0
    common_expenses_missing: bool = False
    unsupported_common_expenses: bool = False

    def __post_init__(self) -> None:
        if self.unmapped_attributes is None:
            self.unmapped_attributes = Counter()


def _count_rows_with_issues(canonical: pd.DataFrame) -> int:
    if canonical.empty or "quality_issues" not in canonical.columns:
        return 0
    return int(
        canonical["quality_issues"]
        .fillna("[]")
        .apply(lambda v: len(json.loads(v)) if isinstance(v, str) else 0)
        .gt(0)
        .sum()
    )


def _build_rejection(
    extracted: ExtractedItem,
    reasons: tuple[str, ...],
    *,
    raw_category_id: str | None = None,
    raw_currency: str | None = None,
    raw_price: float | None = None,
    raw_operation: str | None = None,
    raw_property_type: str | None = None,
) -> RowRejection:
    return RowRejection(
        source_item_id=extracted.source_item_id,
        source_run_id=extracted.source_run_id,
        raw_item_path=extracted.raw_item_path,
        reasons=reasons,
        raw_category_id=raw_category_id,
        raw_currency=raw_currency,
        raw_price=raw_price,
        raw_operation=raw_operation,
        raw_property_type=raw_property_type,
    )


def _lookup_attribute(
    attributes: dict[str, dict[str, Any]], attribute_id: str
) -> tuple[Any, str | None]:
    attribute = attributes.get(attribute_id)
    if attribute is None:
        return None, None
    value = attribute_value(attribute)
    if isinstance(value, dict):
        amount = value.get("number")
        unit = value.get("unit")
        return amount, unit if isinstance(unit, str) else None
    return value, None


def _attribute_value_str(attributes: dict[str, dict[str, Any]], attribute_id: str) -> str | None:
    attribute = attributes.get(attribute_id)
    if attribute is None:
        return None
    value = attribute.get("value_name") or attribute.get("value_id")
    return str(value) if value else None


def _coerce_number(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _decimal_to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _sum_optional(*values: Any) -> float | None:
    total = Decimal(0)
    any_value = False
    for value in values:
        if value is None:
            continue
        try:
            total += Decimal(str(value))
        except Exception:
            continue
        any_value = True
    return float(total) if any_value else None


def _parse_date(value: Any) -> tuple[datetime | None, str | None]:
    if value is None or not isinstance(value, str):
        return None, "invalid_date" if value is not None else None
    text = value.strip()
    if not text:
        return None, "invalid_date"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None, "invalid_date"
    if parsed.tzinfo is None:
        return None, "timezone_missing"
    return parsed.astimezone(UTC), None


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _bucketed_area(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    try:
        return int(Decimal(str(value)) // Decimal("5"))
    except Exception:
        return None


def _bucketed_price(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    try:
        return int(Decimal(str(value)) // Decimal("50"))
    except Exception:
        return None


# Backwards-compatible import point for other modules or tests that need
# to hash a raw file.
_ = hashlib
