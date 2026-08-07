"""Model-info router.

The endpoint is registered but intentionally returns 501 — later
subphases will replace this with the real serving-bundle metadata.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

router = APIRouter()


@router.get("/model-info")
async def model_info() -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Not Implemented",
    )


__all__ = ["router"]
