"""API configuration settings.

Only runtime-facing knobs at this stage. No model-related fields on
purpose — those arrive in a later subphase along with the serving
bundle loader.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    """Environment-driven configuration for the prediction API."""

    APP_NAME: str = "alquileres-uy prediction API"
    APP_VERSION: str = "0.1.0"
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_prefix="ALQUILERES_API_",
        env_file=None,
        case_sensitive=True,
        extra="ignore",
    )


__all__ = ["ApiSettings"]
