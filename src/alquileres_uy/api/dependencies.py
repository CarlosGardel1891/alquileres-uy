"""FastAPI dependency providers.

Only the bare settings provider at this stage.
"""

from __future__ import annotations

from functools import lru_cache

from .config import ApiSettings


@lru_cache(maxsize=1)
def get_settings() -> ApiSettings:
    """Return a memoized :class:`ApiSettings` instance."""
    return ApiSettings()


__all__ = ["get_settings"]
