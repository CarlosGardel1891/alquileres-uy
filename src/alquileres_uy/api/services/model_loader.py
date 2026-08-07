"""Serving-bundle loader for the prediction API.

Wraps :func:`alquileres_uy.models.serving.load_serving_bundle` so the
API layer has a small, testable surface: give it a path, get back a
:class:`LoadedModel` or a :class:`ModelUnavailableError`. It never
trains, never recomputes features, never touches the raw ETL —
everything downstream operates on the already-validated bundle.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alquileres_uy.models.serving import ServingBundleError, load_serving_bundle


class ModelUnavailableError(RuntimeError):
    """Raised when the configured serving bundle cannot be loaded."""


@dataclass(frozen=True)
class LoadedModel:
    """A validated serving bundle in memory.

    ``feature_order`` is the authoritative, ordered list of feature
    names the model expects at inference time. It is sourced from the
    bundle's ``metadata.json.feature_list`` — never reconstructed in
    code — so the API stays decoupled from any particular model's
    feature set.
    """

    model: Any
    metadata: dict[str, Any]
    bundle_path: Path
    feature_order: tuple[str, ...]

    @property
    def version(self) -> str:
        return str(self.metadata.get("bundle_version", "0.0.0"))

    @property
    def model_type(self) -> str:
        return str(self.metadata.get("model_type", "unknown"))

    @property
    def training_run_id(self) -> str:
        return str(self.metadata.get("training_run_id", ""))


class ModelLoader:
    """Locate and load a serving bundle on demand."""

    def __init__(self, *, bundle_path: Path, allow_fixture: bool = False) -> None:
        self._bundle_path = Path(bundle_path)
        self._allow_fixture = bool(allow_fixture)

    @property
    def bundle_path(self) -> Path:
        return self._bundle_path

    def load(self) -> LoadedModel:
        """Load the configured bundle. Raise :class:`ModelUnavailableError`."""
        if not self._bundle_path.exists():
            raise ModelUnavailableError(f"serving bundle not found at {self._bundle_path!s}")
        if not self._bundle_path.is_dir():
            raise ModelUnavailableError(
                f"serving bundle path must be a directory, got {self._bundle_path!s}"
            )
        try:
            payload = load_serving_bundle(self._bundle_path, allow_fixture=self._allow_fixture)
        except ServingBundleError as exc:
            message = str(exc)
            if "fixture" in message.lower() and not self._allow_fixture:
                raise ModelUnavailableError(
                    f"serving bundle at {self._bundle_path!s} is a fixture bundle "
                    "and ALLOW_FIXTURE_MODEL is disabled; set "
                    "ALQUILERES_API_ALLOW_FIXTURE_MODEL=true only in dev/test"
                ) from exc
            raise ModelUnavailableError(
                f"serving bundle at {self._bundle_path!s} is invalid: {exc}"
            ) from exc

        metadata = payload["metadata"]
        feature_list = metadata.get("feature_list")
        if not isinstance(feature_list, list) or not feature_list:
            raise ModelUnavailableError(
                f"serving bundle at {self._bundle_path!s} is missing the feature contract "
                "(metadata.feature_list must be a non-empty list)"
            )
        if not all(isinstance(name, str) and name for name in feature_list):
            raise ModelUnavailableError(
                f"serving bundle at {self._bundle_path!s} has an invalid feature contract "
                "(metadata.feature_list entries must be non-empty strings)"
            )
        return LoadedModel(
            model=payload["model"],
            metadata=metadata,
            bundle_path=self._bundle_path,
            feature_order=tuple(feature_list),
        )


__all__ = ["LoadedModel", "ModelLoader", "ModelUnavailableError"]
