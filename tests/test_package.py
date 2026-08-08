import re

import alquileres_uy


def test_package_version_matches_semver() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", alquileres_uy.__version__)


def test_package_version_is_0_10_0() -> None:
    """The current release under development is 0.10.0 (Fase 10)."""

    assert alquileres_uy.__version__ == "0.10.0"
