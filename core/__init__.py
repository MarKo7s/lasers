"""Framework-agnostic laser discovery; model-specific logic under subpackages."""

from core.discovery_service import DiscoveryService
from core.factory import create_laser_controller, supports_model
from core.models import DiscoveredDevice, StatusMessage
from core.tlb8800 import (  # noqa: F401 — registers formatters
    TLB8800Controller,
    bindings_from_specs,
)

# Backward-compatible alias for TLB-8800-only callers
LaserController = TLB8800Controller

__all__ = [
    "DiscoveredDevice",
    "DiscoveryService",
    "LaserController",
    "StatusMessage",
    "TLB8800Controller",
    "bindings_from_specs",
    "create_laser_controller",
    "supports_model",
]
