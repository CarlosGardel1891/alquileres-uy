"""Runtime configuration for the ingestion layer."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

DEFAULT_SITE_ID = "MLU"
DEFAULT_OUTPUT_DIR = Path("data/raw/mercadolibre")
DEFAULT_DATABASE_PATH = Path("data/ingestion.sqlite")
DEFAULT_MAX_ITEMS = 5000
DEFAULT_REQUESTS_PER_SECOND = 2.0
DEFAULT_REQUEST_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_ATTEMPTS = 5

MAX_MULTIGET_BATCH_SIZE = 20
MAX_SEARCH_PAGE_SIZE = 100
MAX_SEARCH_OFFSET = 1000


@dataclass(frozen=True)
class IngestionConfig:
    """Configuration for a single ingestion invocation.

    All numeric fields are validated in :meth:`__post_init__`. Overrides are
    applied via :meth:`with_overrides` to keep instances immutable.
    """

    site_id: str = DEFAULT_SITE_ID
    output_dir: Path = DEFAULT_OUTPUT_DIR
    database_path: Path = DEFAULT_DATABASE_PATH
    max_items: int = DEFAULT_MAX_ITEMS
    requests_per_second: float = DEFAULT_REQUESTS_PER_SECOND
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    access_token: str | None = None

    def __post_init__(self) -> None:
        if not self.site_id:
            raise ValueError("site_id must be non-empty")
        if self.max_items <= 0:
            raise ValueError("max_items must be positive")
        if self.requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        if self.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")

    def with_overrides(self, **overrides: object) -> IngestionConfig:
        """Return a new config with the given fields overridden."""
        clean: dict[str, object] = {k: v for k, v in overrides.items() if v is not None}
        return replace(self, **clean)  # type: ignore[arg-type]
