"""Bundle-API version compatibility check.

The serving bundle can declare a ``minimum_api_version`` string in its
``metadata.json``. During startup the API compares its own
``APP_VERSION`` against that requirement and refuses to serve a bundle
that expects a newer API. Missing the field is treated as *no
constraint* so bundles produced before this check landed keep loading.
"""

from __future__ import annotations

from .services.model_loader import LoadedModel


class IncompatibleBundleError(RuntimeError):
    """Raised when the bundle requires a newer API version."""


def _parse(version: str) -> tuple[int, ...]:
    """Best-effort ``(major, minor, patch, ...)`` parser.

    Non-integer suffixes (``"1.0.0-rc1"``) are trimmed off after the
    numeric prefix so simple ``a >= b`` comparisons stay sane. A blank
    string parses to ``(0,)`` — the loosest possible requirement.
    """
    if not version:
        return (0,)
    parts: list[int] = []
    for chunk in str(version).split("."):
        numeric = ""
        for ch in chunk:
            if ch.isdigit():
                numeric += ch
            else:
                break
        if not numeric:
            break
        parts.append(int(numeric))
    return tuple(parts) if parts else (0,)


def verify_bundle_compatibility(loaded: LoadedModel, *, api_version: str) -> None:
    """Raise :class:`IncompatibleBundleError` if the bundle needs a newer API."""
    required = loaded.metadata.get("minimum_api_version")
    if not required:
        return
    if _parse(str(api_version)) < _parse(str(required)):
        raise IncompatibleBundleError(
            f"serving bundle requires API >= {required} but the running API is {api_version}"
        )


__all__ = ["IncompatibleBundleError", "verify_bundle_compatibility"]
