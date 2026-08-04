"""Runtime configuration for the ETL pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_OUTPUT_DIR = Path("data/processed")


@dataclass(frozen=True)
class EtlConfig:
    """Configuration for a single ETL invocation."""

    input_run_dirs: tuple[Path, ...]
    exchange_rate_path: Path
    output_dir: Path = DEFAULT_OUTPUT_DIR
    neighborhood_aliases_path: Path | None = None
    gate_approval_path: Path | None = None
    fixture_mode: bool = False
    dry_run: bool = False
    strict: bool = False

    def __post_init__(self) -> None:
        if not self.input_run_dirs:
            raise ValueError("EtlConfig requires at least one input run directory")

    @property
    def data_mode(self) -> str:
        from .models import DATA_MODE_FIXTURE, DATA_MODE_REAL

        return DATA_MODE_FIXTURE if self.fixture_mode else DATA_MODE_REAL
