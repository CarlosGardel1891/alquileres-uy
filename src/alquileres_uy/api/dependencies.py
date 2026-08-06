"""FastAPI dependency providers.

Only the bare settings provider at this stage.
"""

from __future__ import annotations

from .config import ApiSettings


def get_settings() -> ApiSettings:
    return ApiSettings()


__all__ = ["get_settings"]
