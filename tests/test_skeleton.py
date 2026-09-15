"""Skeleton test: the package imports and exposes a version."""

import manc


def test_package_has_version() -> None:
    assert isinstance(manc.__version__, str)
    assert manc.__version__
