"""Reproducible model training pipeline for alquileres-uy.

This package implements Fase 3: read a validated ETL run, split it
temporally, train four candidate models (baseline / Ridge / LightGBM /
PyTorch), score them, and publish an atomic bundle of artifacts.

Fase 3 is contract-first. Nothing here processes real MercadoLibre
data — the real path stays blocked until an explicit
``ETL_PRODUCTION_VALIDATED`` approval is provided.
"""

from __future__ import annotations

__all__: list[str] = []
