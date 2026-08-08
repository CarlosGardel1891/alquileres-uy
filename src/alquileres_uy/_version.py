"""Single source of truth for the ``alquileres-uy`` version string.

Every other version reference in the code base — the package's
``__version__`` attribute, the API's ``APP_VERSION`` setting, the
Docker image label, the CI ``release-check`` job, the release script
— must ultimately resolve to this module. ``pyproject.toml`` reads
this attribute at build time (``[tool.setuptools.dynamic]``), so
bumping the number here bumps the wheel, the sdist, the API and the
Docker image in one commit.

Format: ``MAJOR.MINOR.PATCH`` (semver 2.0.0). Pre-release and build
metadata are not used.
"""

from __future__ import annotations

__version__ = "0.10.0"

__all__ = ["__version__"]
