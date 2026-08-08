"""``GET /build`` — expose baked-in build metadata.

Reads ``build_info.json`` via :mod:`alquileres_uy.api.build_info`.
Nothing is hard-coded at request time; if the file is missing the
loader returns a synthetic payload marked with ``"unknown"`` fields so
the shape stays stable.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..build_info import get_build_info

router = APIRouter()


@router.get("/build")
async def build() -> dict[str, str]:
    return get_build_info()


__all__ = ["router"]
