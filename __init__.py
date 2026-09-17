"""lasers distribution metadata + convenience exports.

Import prefix after install: ``laser`` (pip name remains ``lasers``).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("lasers")
except PackageNotFoundError:  # running from source without install
    __version__ = "2.0.0"
