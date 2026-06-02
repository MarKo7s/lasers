"""TLB-8800 controller, UI bindings, and discovery helpers."""

from __future__ import annotations

from core.idn_registry import register_idn_formatter
from core.tlb8800.control_bindings import bindings_from_specs
from core.tlb8800.enums_ui import (
    INTERLOCK_LABELS,
    LOOP_MODE_LABELS,
    MODULATION_OPTIONS,
    POWER_UNIT_OPTIONS,
    SCAN_MODE_OPTIONS,
    TUNING_DOMAIN_OPTIONS,
)
from core.tlb8800.idn import display_id_from_idn as tlb8800_display_id_from_idn
from core.tlb8800.laser_controller import TLB8800Controller, TelemetrySnapshot
from core.tlb8800.models import ControlBindings, NumericBinding, SelectBinding
from core.tlb8800.status import status_from_command_result

register_idn_formatter("TLB-8800", tlb8800_display_id_from_idn)

__all__ = [
    "ControlBindings",
    "INTERLOCK_LABELS",
    "LOOP_MODE_LABELS",
    "MODULATION_OPTIONS",
    "NumericBinding",
    "POWER_UNIT_OPTIONS",
    "SCAN_MODE_OPTIONS",
    "TLB8800Controller",
    "TelemetrySnapshot",
    "TUNING_DOMAIN_OPTIONS",
    "bindings_from_specs",
    "status_from_command_result",
]
