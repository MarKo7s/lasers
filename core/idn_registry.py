"""Model-specific *IDN? display formatters for discovery."""

from __future__ import annotations

from typing import Callable

_IdnFormatter = Callable[[str], str]
_formatters: list[tuple[str, _IdnFormatter]] = []


def register_idn_formatter(model_substring: str, formatter: _IdnFormatter) -> None:
    """Register ``formatter(raw_idn)`` when ``model_substring`` appears in the model name."""
    _formatters.append((model_substring, formatter))


def display_id_from_idn(model: str, raw_idn: str) -> str:
    for key, formatter in _formatters:
        if key in model:
            return formatter(raw_idn)
    text = raw_idn.strip()
    if len(text) > 48:
        return text[:45] + "..."
    return text or "Unknown"
