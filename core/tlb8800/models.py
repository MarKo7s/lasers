"""TLB-8800 UI binding models derived from LaserSpecs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class NumericBinding:
    enabled: bool
    value: Optional[float]
    minimum: Optional[float]
    maximum: Optional[float]
    step: float = 0.001


@dataclass(frozen=True)
class SelectBinding:
    enabled: bool
    value: Optional[int]


@dataclass(frozen=True)
class ControlBindings:
    """UI enable/disable state and bounds derived from LaserSpecs."""

    power: NumericBinding
    power_unit: SelectBinding
    current: NumericBinding
    tune: NumericBinding
    tuning_domain: SelectBinding
    modulation: SelectBinding
    scan_start: NumericBinding
    scan_stop: NumericBinding
    scan_speed: NumericBinding
    scan_cycles: NumericBinding
    scan_dwell_ms: NumericBinding
    scan_step: NumericBinding
    scan_mode: SelectBinding
    laser_output: bool
    software_interlock_inhibit: bool
