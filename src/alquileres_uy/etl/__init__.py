"""ETL pipeline for alquileres-uy raw ingestion runs.

The ETL turns per-run raw MercadoLibre responses (as persisted by the
Fase 1 ingestion) into three deterministic Parquet datasets:

- ``listings.parquet`` — canonical listings that survive the scope
  gate (monthly rental of apartment or house in Montevideo).
- ``model_ready.parquet`` — a stricter subset with the fields the
  training phase will actually need.
- ``rejected_listings.parquet`` — every rejected listing with the
  ``rejection_reasons`` that explain why.

``duplicate_candidates.parquet`` complements the canonical dataset
with conservative same-listing groupings across agencies (never
deleted, only tagged).

Every run emits ``etl_summary.json``, ``data_quality_report.json``,
``unmapped_attributes.json`` and ``lineage.json`` for traceability.
"""

from .config import EtlConfig
from .models import ETL_SCHEMA_VERSION

__all__ = ["ETL_SCHEMA_VERSION", "EtlConfig"]
