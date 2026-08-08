"""API configuration settings.

Runtime-facing knobs plus the location of the serving bundle the API
should expose. The bundle is loaded once at startup; the actual file
IO lives in :mod:`alquileres_uy.api.services.model_loader`.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from .._version import __version__ as _PACKAGE_VERSION


class ApiSettings(BaseSettings):
    """Environment-driven configuration for the prediction API."""

    APP_NAME: str = "alquileres-uy prediction API"
    # APP_VERSION is anchored to the packaged version so that a wheel /
    # container ships with a single semver number. See _version.py.
    APP_VERSION: str = _PACKAGE_VERSION
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

    # Runtime reliability knobs.
    #
    # ``MAX_CONCURRENT_PREDICTIONS`` caps the number of in-flight
    # predictions via an asyncio semaphore. Requests over the cap wait
    # (they are never rejected) so the model process cannot be
    # oversubscribed.
    #
    # ``PREDICT_TIMEOUT`` (seconds) bounds each individual prediction.
    # When exceeded, the request is cancelled and the client receives
    # HTTP 503 with a ``prediction_timeout`` error code.
    MAX_CONCURRENT_PREDICTIONS: int = 4
    PREDICT_TIMEOUT: float = 5.0

    model_config = SettingsConfigDict(
        env_prefix="ALQUILERES_API_",
        env_file=None,
        case_sensitive=True,
        extra="ignore",
    )


__all__ = ["ApiSettings"]
