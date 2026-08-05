"""Central configuration and constants for the training pipeline.

Every magic string (feature names, artifact filenames, versions) lives
here so downstream modules cannot silently drift out of sync with each
other. The :class:`TrainingConfig` dataclass validates the arguments
that arrive via the CLI before anything is loaded from disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# ---- schema / feature contract ---------------------------------------
SUPPORTED_ETL_SCHEMA_VERSIONS: tuple[str, ...] = ("1.0.0",)
TARGET_COLUMN: str = "price_usd"

REQUIRED_MODEL_READY_COLUMNS: tuple[str, ...] = (
    "source_item_id",
    "property_type",
    "neighborhood_normalized",
    "bedrooms",
    "total_area_m2",
    "price_usd",
    "date_created",
)
OPTIONAL_MODEL_READY_COLUMNS: tuple[str, ...] = ("bathrooms",)

NUMERIC_FEATURES: tuple[str, ...] = ("bedrooms", "bathrooms", "total_area_m2")
CATEGORICAL_FEATURES: tuple[str, ...] = ("neighborhood_normalized", "property_type")
FEATURE_COLUMNS: tuple[str, ...] = NUMERIC_FEATURES + CATEGORICAL_FEATURES

FORBIDDEN_FEATURE_COLUMNS: tuple[str, ...] = (
    "price_usd",
    "price_per_m2",
    "price_bucket",
    "total_monthly_cost_usd",
    "source_item_id",
    "date_created",
)

# ---- model registry --------------------------------------------------
MODEL_NAMES: tuple[str, ...] = ("baseline", "linear", "lightgbm", "torch")
CLASSICAL_MODEL_NAMES: tuple[str, ...] = ("baseline", "linear", "lightgbm")
SERVING_ELIGIBLE_MODEL_NAMES: tuple[str, ...] = CLASSICAL_MODEL_NAMES

# ---- split defaults --------------------------------------------------
DEFAULT_TRAIN_FRACTION: float = 0.70
DEFAULT_VALIDATION_FRACTION: float = 0.15
DEFAULT_TEST_FRACTION: float = 0.15
SPLIT_ALGORITHM_VERSION: str = "temporal-grouped-v1"

# ---- training defaults -----------------------------------------------
DEFAULT_SEED: int = 42
DEFAULT_MAX_EPOCHS: int = 200
DEFAULT_PATIENCE: int = 15

# ---- artifact filenames ---------------------------------------------
BUNDLE_VERSION: str = "1.0.0"
SERVING_BUNDLE_DIRNAME: str = "serving_bundle"
PLOTS_DIRNAME: str = "plots"
MODELS_DIRNAME: str = "models"
ARTIFACT_SIZE_LIMIT_BYTES: int = 50 * 1024 * 1024


class TrainingConfigError(ValueError):
    """Raised when :class:`TrainingConfig` receives an invalid argument."""


@dataclass(frozen=True)
class TrainingConfig:
    """Validated training-pipeline configuration."""

    etl_run_dir: Path
    output_dir: Path
    fixture_mode: bool
    dry_run: bool = False
    include_torch: bool = False
    etl_approval_path: Path | None = None
    seed: int = DEFAULT_SEED
    train_fraction: float = DEFAULT_TRAIN_FRACTION
    validation_fraction: float = DEFAULT_VALIDATION_FRACTION
    test_fraction: float = DEFAULT_TEST_FRACTION
    max_epochs: int = DEFAULT_MAX_EPOCHS
    patience: int = DEFAULT_PATIENCE
    torch_batch_size: int = 32
    ridge_alphas: tuple[float, ...] = field(default_factory=lambda: (0.1, 1.0, 10.0))

    def __post_init__(self) -> None:
        if not isinstance(self.seed, int):
            raise TrainingConfigError("seed must be an integer")
        for fraction, name in (
            (self.train_fraction, "train_fraction"),
            (self.validation_fraction, "validation_fraction"),
            (self.test_fraction, "test_fraction"),
        ):
            if not (0.0 < fraction < 1.0):
                raise TrainingConfigError(f"{name} must be strictly between 0 and 1")
        total = self.train_fraction + self.validation_fraction + self.test_fraction
        if abs(total - 1.0) > 1e-6:
            raise TrainingConfigError(
                f"train/validation/test fractions must sum to 1.0, got {total}"
            )
        if self.max_epochs <= 0:
            raise TrainingConfigError("max_epochs must be positive")
        if self.patience <= 0:
            raise TrainingConfigError("patience must be positive")
        if self.torch_batch_size <= 0:
            raise TrainingConfigError("torch_batch_size must be positive")
        if not self.etl_run_dir.is_dir():
            raise TrainingConfigError(f"etl_run_dir does not exist: {self.etl_run_dir}")
        if self.fixture_mode and self.etl_approval_path is not None:
            raise TrainingConfigError("fixture mode does not accept --etl-approval; drop the flag")
        if not self.fixture_mode and self.etl_approval_path is None:
            raise TrainingConfigError(
                "real mode requires --etl-approval pointing to ETL_PRODUCTION_VALIDATED"
            )
        if self.etl_approval_path is not None and not self.etl_approval_path.is_file():
            raise TrainingConfigError(f"etl approval file does not exist: {self.etl_approval_path}")


__all__ = [
    "ARTIFACT_SIZE_LIMIT_BYTES",
    "BUNDLE_VERSION",
    "CATEGORICAL_FEATURES",
    "CLASSICAL_MODEL_NAMES",
    "DEFAULT_MAX_EPOCHS",
    "DEFAULT_PATIENCE",
    "DEFAULT_SEED",
    "DEFAULT_TEST_FRACTION",
    "DEFAULT_TRAIN_FRACTION",
    "DEFAULT_VALIDATION_FRACTION",
    "FEATURE_COLUMNS",
    "FORBIDDEN_FEATURE_COLUMNS",
    "MODELS_DIRNAME",
    "MODEL_NAMES",
    "NUMERIC_FEATURES",
    "OPTIONAL_MODEL_READY_COLUMNS",
    "PLOTS_DIRNAME",
    "REQUIRED_MODEL_READY_COLUMNS",
    "SERVING_BUNDLE_DIRNAME",
    "SERVING_ELIGIBLE_MODEL_NAMES",
    "SPLIT_ALGORITHM_VERSION",
    "SUPPORTED_ETL_SCHEMA_VERSIONS",
    "TARGET_COLUMN",
    "TrainingConfig",
    "TrainingConfigError",
]
