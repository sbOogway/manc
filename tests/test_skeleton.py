"""Skeleton tests: the two packages import and expose a version."""

import manc
import manc_formulas


def test_app_package_has_version() -> None:
    assert isinstance(manc.__version__, str)
    assert manc.__version__


def test_formulas_package_has_version() -> None:
    assert isinstance(manc_formulas.__version__, str)
    assert manc_formulas.__version__
