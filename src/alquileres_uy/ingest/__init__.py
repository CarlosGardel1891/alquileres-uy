"""Ingestion layer for the alquileres-uy pipeline."""

from .config import IngestionConfig
from .models import SourceGateDecision

__all__ = ["IngestionConfig", "SourceGateDecision"]
