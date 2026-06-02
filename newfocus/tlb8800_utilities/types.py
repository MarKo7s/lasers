"""Shared types for TLB-series Legacy laser drivers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class OperationCompleteState(IntEnum):
    """Legacy opc? values (manual Table 4)."""

    UNRECOVERABLE_ERROR = -2
    RECOVERABLE_ERROR = -1
    PENDING = 0
    COMPLETE = 1
    INITIALIZING = 2


class InterlockState(IntEnum):
    """int? response values."""

    BOTH_OFF = 0
    SOFTWARE_ACTIVE = 1
    HARDWARE_ACTIVE = 2
    BOTH_ACTIVE = 3


class LoopMode(IntEnum):
    CONSTANT_POWER = 0
    CONSTANT_CURRENT = 1


class PowerUnit(IntEnum):
    DBM = 0
    MW = 1


class TuningDomain(IntEnum):
    WAVELENGTH = 0
    FREQUENCY = 1


class ModulationSource(IntEnum):
    NONE = 0
    COHERENCE_CONTROL = 1
    EXTERNAL_ANALOG = 3


class ScanMode(IntEnum):
    AUTOMATIC_STEP = 1
    UNI_FORWARD = 2
    BI_DIRECTIONAL = 3
    UNI_REVERSE = 4


class TriggerPolarity(IntEnum):
    ACTIVE_LOW = 0
    ACTIVE_HIGH = 1


class FanSpeed(IntEnum):
    OFF = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3


@dataclass(frozen=True)
class LaserIdentity:
    manufacturer: str
    model: str
    customer_serial: str
    nf_serial: str
    firmware_version: str
    fpga_version: str
    raw_idn: str


@dataclass(frozen=True)
class LaserSpecs:
    """Snapshot of laser capabilities and state from Legacy query commands."""

    current_control: bool
    loop_mode: Optional[LoopMode]
    identity: Optional[LaserIdentity]
    laser_output: Optional[bool]
    interlock_state: Optional[InterlockState]
    operation_complete: Optional[int]
    power: Optional[float]
    power_min: Optional[float]
    power_max: Optional[float]
    power_unit: Optional[PowerUnit]
    current: Optional[float]
    current_max: Optional[float]
    tuning_domain: Optional[TuningDomain]
    wavelength_min: Optional[float]
    wavelength_max: Optional[float]
    tune_setpoint: Optional[float]
    modulation_source: Optional[ModulationSource]
    scan_start: Optional[float]
    scan_start_acceleration_offset: Optional[float]
    scan_stop: Optional[float]
    scan_stop_deceleration_offset: Optional[float]
    scan_step_size: Optional[float]
    scan_mode: Optional[ScanMode]
    scan_speed: Optional[float]
    scan_speed_min: Optional[float]
    scan_speed_max: Optional[float]
    scan_dwell_time_ms: Optional[float]
    scan_cycles: Optional[int]
    scan_cycles_count: Optional[int]
    laser_diode_temperature_setpoint: Optional[float]
    laser_diode_temperature: Optional[float]
    environment_temperature: Optional[float]
    temperature_regulated: Optional[bool]
    fan_override: Optional[bool]
    fan_speed: Optional[FanSpeed]
    trigger_polarity: Optional[TriggerPolarity]
    trigger_a_enabled: Optional[bool]
    trigger_b_enabled: Optional[bool]
    operating_hours: Optional[float]
    error_count: Optional[int]
    error_codes: Optional[list[int]]
