"""Map LaserSpecs to UI control enablement and numeric bounds."""

from __future__ import annotations

from newfocus.tlb8800_utilities.types import LaserSpecs, ScanMode, TuningDomain

from core.tlb8800.models import ControlBindings, NumericBinding, SelectBinding


def _numeric(
    *,
    enabled: bool,
    value,
    minimum,
    maximum,
    step: float = 0.001,
) -> NumericBinding:
    return NumericBinding(
        enabled=enabled,
        value=float(value) if value is not None else None,
        minimum=float(minimum) if minimum is not None else None,
        maximum=float(maximum) if maximum is not None else None,
        step=step,
    )


def _select(*, enabled: bool, value) -> SelectBinding:
    return SelectBinding(
        enabled=enabled,
        value=int(value) if value is not None else None,
    )


def bindings_from_specs(specs: LaserSpecs) -> ControlBindings:
    wl_min = specs.wavelength_min
    wl_max = specs.wavelength_max
    has_wl_range = wl_min is not None and wl_max is not None

    power_enabled = (
        not specs.current_control
        and specs.power_min is not None
        and specs.power_max is not None
    )
    current_enabled = specs.current_control and specs.current_max is not None

    scan_speed_enabled = (
        specs.scan_speed_min is not None and specs.scan_speed_max is not None
    )

    return ControlBindings(
        power=_numeric(
            enabled=power_enabled,
            value=specs.power,
            minimum=specs.power_min,
            maximum=specs.power_max,
            step=0.01,
        ),
        power_unit=_select(
            enabled=power_enabled and specs.power_unit is not None,
            value=int(specs.power_unit) if specs.power_unit is not None else None,
        ),
        current=_numeric(
            enabled=current_enabled,
            value=specs.current,
            minimum=0.0 if current_enabled else None,
            maximum=specs.current_max,
            step=0.1,
        ),
        tune=_numeric(
            enabled=has_wl_range,
            value=specs.tune_setpoint,
            minimum=wl_min,
            maximum=wl_max,
            step=0.001,
        ),
        tuning_domain=_select(
            enabled=True,
            value=int(specs.tuning_domain)
            if specs.tuning_domain is not None
            else int(TuningDomain.WAVELENGTH),
        ),
        modulation=_select(
            enabled=specs.modulation_source is not None,
            value=int(specs.modulation_source)
            if specs.modulation_source is not None
            else None,
        ),
        scan_start=_numeric(
            enabled=has_wl_range,
            value=specs.scan_start,
            minimum=wl_min,
            maximum=wl_max,
            step=0.001,
        ),
        scan_stop=_numeric(
            enabled=has_wl_range,
            value=specs.scan_stop,
            minimum=wl_min,
            maximum=wl_max,
            step=0.001,
        ),
        scan_speed=_numeric(
            enabled=scan_speed_enabled,
            value=specs.scan_speed,
            minimum=specs.scan_speed_min,
            maximum=specs.scan_speed_max,
            step=0.1,
        ),
        scan_cycles=_numeric(
            enabled=specs.scan_cycles is not None,
            value=float(specs.scan_cycles) if specs.scan_cycles is not None else None,
            minimum=-1.0,
            maximum=1_000_000.0,
            step=1.0,
        ),
        scan_dwell_ms=_numeric(
            enabled=specs.scan_dwell_time_ms is not None,
            value=specs.scan_dwell_time_ms,
            minimum=0.0,
            maximum=None,
            step=1.0,
        ),
        scan_step=_numeric(
            enabled=specs.scan_step_size is not None,
            value=specs.scan_step_size,
            minimum=0.0,
            maximum=None,
            step=0.001,
        ),
        scan_mode=_select(
            enabled=specs.scan_mode is not None,
            value=int(specs.scan_mode)
            if specs.scan_mode is not None
            else int(ScanMode.UNI_FORWARD),
        ),
        laser_output=bool(specs.laser_output) if specs.laser_output is not None else False,
        software_interlock_inhibit=(
            specs.interlock_state is not None
            and int(specs.interlock_state) in (1, 3)
        ),
    )
