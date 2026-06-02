"""Instantiate a model-specific laser controller for a discovered device."""

from __future__ import annotations

from core.models import DiscoveredDevice
from core.tlb8800 import TLB8800Controller

_TLB8800_MODEL_KEYS = ("TLB-8800", "TLB8800")


def supports_model(model: str) -> bool:
    normalized = model.upper().replace(" ", "")
    return any(key.replace("-", "") in normalized.replace("-", "") for key in _TLB8800_MODEL_KEYS)


def create_laser_controller(device: DiscoveredDevice) -> TLB8800Controller:
    """Return a connected-session controller for ``device.model``."""
    if supports_model(device.model):
        return TLB8800Controller()
    raise ValueError(f"No controller registered for model {device.model!r}")
