"""lasers package metadata + convenience exports."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("lasers")
except PackageNotFoundError:  # running from source without install
    __version__ = "1.0.0"

