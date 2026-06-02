"""Partial refresh of :class:`LaserSpecs` from Legacy query commands."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Iterable, Optional, TypeVar

from newfocus.tlb8800_utilities.errors import TLB8800ParseError
from newfocus.tlb8800_utilities.spec_fields import ALL_SPEC_FIELDS, DERIVED_SPEC_FIELDS, SpecField
from newfocus.tlb8800_utilities.types import LaserSpecs, LoopMode

T = TypeVar("T")


def _read_optional(laser: Any, fn: Callable[[], T]) -> Optional[T]:
    try:
        return fn()
    except (TLB8800ParseError, TimeoutError, OSError, ValueError):
        return None


def _refresh_loop_mode(laser: Any) -> dict[str, Any]:
    r = laser.read
    loop_mode = _read_optional(laser, r.loop_mode)
    current_control = loop_mode == LoopMode.CONSTANT_CURRENT
    updates: dict[str, Any] = {
        "loop_mode": loop_mode,
        "current_control": current_control,
    }
    if current_control:
        updates["power"] = None
        updates["power_unit"] = None
    else:
        updates["power"] = _read_optional(laser, r.power)
        updates["power_unit"] = _read_optional(laser, r.power_unit)
    return updates


def _field_readers(laser: Any) -> dict[SpecField, Callable[[], dict[str, Any]]]:
    r = laser.read

    def _single(name: SpecField, reader: Callable[[], Any]) -> Callable[[], dict[str, Any]]:
        return lambda: {name: _read_optional(laser, reader)}

    readers: dict[SpecField, Callable[[], dict[str, Any]]] = {
        "loop_mode": lambda: _refresh_loop_mode(laser),
        "identity": lambda: _refresh_identity(laser),
        "laser_output": _single("laser_output", r.laser_output),
        "interlock_state": _single("interlock_state", r.interlock_state),
        "operation_complete": _single("operation_complete", r.operation_complete),
        "power": _single("power", r.power),
        "power_min": _single("power_min", r.power_min),
        "power_max": _single("power_max", r.power_max),
        "power_unit": _single("power_unit", r.power_unit),
        "current": _single("current", r.current),
        "current_max": _single("current_max", r.current_max),
        "tuning_domain": _single("tuning_domain", r.tuning_domain),
        "wavelength_min": _single("wavelength_min", r.wavelength_min),
        "wavelength_max": _single("wavelength_max", r.wavelength_max),
        "tune_setpoint": _single("tune_setpoint", r.tune_setpoint),
        "modulation_source": _single("modulation_source", r.modulation_source),
        "scan_start": _single("scan_start", r.scan_start),
        "scan_start_acceleration_offset": _single(
            "scan_start_acceleration_offset", r.scan_start_acceleration_offset
        ),
        "scan_stop": _single("scan_stop", r.scan_stop),
        "scan_stop_deceleration_offset": _single(
            "scan_stop_deceleration_offset", r.scan_stop_deceleration_offset
        ),
        "scan_step_size": _single("scan_step_size", r.scan_step_size),
        "scan_mode": _single("scan_mode", r.scan_mode),
        "scan_speed": _single("scan_speed", r.scan_speed),
        "scan_speed_min": _single("scan_speed_min", r.scan_speed_min),
        "scan_speed_max": _single("scan_speed_max", r.scan_speed_max),
        "scan_dwell_time_ms": _single("scan_dwell_time_ms", r.scan_dwell_time_ms),
        "scan_cycles": _single("scan_cycles", r.scan_cycles),
        "scan_cycles_count": _single("scan_cycles_count", r.scan_cycles_count),
        "laser_diode_temperature_setpoint": _single(
            "laser_diode_temperature_setpoint", r.laser_diode_temperature_setpoint
        ),
        "laser_diode_temperature": _single("laser_diode_temperature", r.laser_diode_temperature),
        "environment_temperature": _single("environment_temperature", r.environment_temperature),
        "temperature_regulated": _single("temperature_regulated", r.temperature_regulated),
        "fan_override": _single("fan_override", r.fan_override),
        "fan_speed": _single("fan_speed", r.fan_speed),
        "trigger_polarity": _single("trigger_polarity", r.trigger_polarity),
        "trigger_a_enabled": _single("trigger_a_enabled", r.trigger_a_enabled),
        "trigger_b_enabled": _single("trigger_b_enabled", r.trigger_b_enabled),
        "operating_hours": _single("operating_hours", r.operating_hours),
        "error_count": _single("error_count", r.error_count),
        "error_codes": _single("error_codes", r.all_error_codes),
    }
    return readers


def _refresh_identity(laser: Any) -> dict[str, Any]:
    identity = _read_optional(laser, laser.read.identify)
    if identity is not None:
        laser._identity = identity
    return {"identity": identity}


def refresh_laser_specs_fields(
    laser: Any,
    specs: LaserSpecs,
    fields: Iterable[str],
) -> LaserSpecs:
    """Re-query only the given ``LaserSpecs`` fields and merge into ``specs``."""
    requested = {f for f in fields if f not in DERIVED_SPEC_FIELDS}
    unknown = requested - set(ALL_SPEC_FIELDS)
    if unknown:
        raise ValueError(f"Unknown LaserSpecs field(s): {sorted(unknown)}")

    if not requested:
        return specs

    readers = _field_readers(laser)
    updates: dict[str, Any] = {}
    for name in requested:
        updates.update(readers[name]())

    return replace(specs, **updates)
