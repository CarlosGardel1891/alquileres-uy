"""API configuration settings.

Runtime-facing knobs plus the location of the serving bundle the API
should expose. The bundle is loaded once at startup; the actual file
IO lives in :mod:`alquileres_uy.api.services.model_loader`.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    """Environment-driven configuration for the prediction API."""

    APP_NAME: str = "alquileres-uy prediction API"
    APP_VERSION: str = "0.1.0"
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # Location of the trained serving bundle produced by Fase 3
    # (scripts/train_models.py → <output-dir>/<ts>_<id>/serving_bundle/).
    MODEL_BUNDLE_PATH: Path = Path("artifacts/models/latest/serving_bundle")
    # Fixture bundles carry `deployable: false` by contract. Dev / test
    # setups can flip this to True to consume them; production must
    # never enable it.
    ALLOW_FIXTURE_MODEL: bool = False

    # Runtime knobs consumed by scripts/run_api.py (uvicorn) so ops
    # can tune the deployment via environment variables only.
    REQUEST_TIMEOUT: int = 30  # seconds; passed to uvicorn --timeout-keep-alive
    MAX_WORKERS: int = 1  # single-process default; scale horizontally

    # Prometheus observability. Enabled by default; disabling turns the
    # metrics middleware into a no-op and hides the /metrics endpoint.
    ENABLE_METRICS: bool = True
    METRICS_PATH: str = "/metrics"

    model_config = SettingsConfigDict(
        env_prefix="ALQUILERES_API_",
        env_file=None,
        case_sensitive=True,
        extra="ignore",
    )


__all__ = ["ApiSettings"]
