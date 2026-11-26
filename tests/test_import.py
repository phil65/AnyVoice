"""Smoke test: the package imports and reports its version."""

import anyvoice


def test_package_imports() -> None:
    """The package can be imported and exposes a version string."""
    assert isinstance(anyvoice.__version__, str)
