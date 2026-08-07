"""Version endpoint.

Reads what the bundle already declares — never reconstructs the values.
Fields come from ``metadata.json`` (via :class:`LoadedModel.metadata`)
and the bundle's own ``model_artifact_sha256`` (which the loader
already verified against the on-disk file at startup).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from ..dependencies import get_settings

router = APIRouter()


@router.get("/version")
async def version(request: Request) -> dict[str, str]:
    loaded_model = getattr(request.app.state, "loaded_model", None)
    if loaded_model is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model is not available",
        )
    metadata = loaded_model.metadata
    settings = get_settings()
    return {
        "api_version": settings.APP_VERSION,
        "model_version": str(metadata.get("bundle_version", "")),
        "model_type": str(metadata.get("model_type", "")),
        "trained_at": str(metadata.get("trained_at", "")),
        "bundle_sha256": str(metadata.get("model_artifact_sha256", "")),
    }


__all__ = ["router"]
