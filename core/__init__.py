"""Framework-agnostic laser discovery; model-specific logic under subpackages."""



from laser.core.discovery_service import DiscoveryService

from laser.core.factory import create_laser_controller, supports_model

from laser.core.models import DiscoveredDevice, StatusMessage

from laser.core.tlb8800 import (  # noqa: F401 — registers formatters

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


