"""Homr evaluation tooling package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("homr")
except PackageNotFoundError:  # pragma: no cover - homr package may not be installed
    __version__ = "0.0.0"

__all__ = ["__version__"]
