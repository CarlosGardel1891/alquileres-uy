"""Application lifespan.

Runs a startup + shutdown pair with no side effects. Later subphases
will attach the serving-bundle loader and cache here; at this stage
we deliberately keep it empty.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

_LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Async lifespan with startup + shutdown hooks."""
    _LOGGER.info("api startup")
    try:
        yield
    finally:
        _LOGGER.info("api shutdown")


__all__ = ["lifespan"]
