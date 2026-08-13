"""Human-readable labels for TLB-8800 instrument enums (UI dropdowns)."""

from __future__ import annotations

from newfocus.tlb8800_utilities.types import (
    ModulationSource,
    PowerUnit,
    ScanMode,
    TriggerPolarity,
    TuningDomain,
)

TUNING_DOMAIN_OPTIONS: dict[int, str] = {
    int(TuningDomain.WAVELENGTH): "Wavelength (nm)",
    int(TuningDomain.FREQUENCY): "Frequency (THz)",
}


def is_frequency_domain(domain: TuningDomain | int | None) -> bool:
    return domain is not None and int(domain) == int(TuningDomain.FREQUENCY)


def tuning_value_unit(domain: TuningDomain | int | None) -> str:
    return "THz" if is_frequency_domain(domain) else "nm"


def tune_setpoint_label(domain: TuningDomain | int | None) -> str:
    return f"Tune setpoint ({tuning_value_unit(domain)})"


def scan_bound_label(name: str, domain: TuningDomain | int | None) -> str:
    return f"{name} ({tuning_value_unit(domain)})"


def scan_speed_label(domain: TuningDomain | int | None) -> str:
    if is_frequency_domain(domain):
        return "Scan speed (THz/s)"
    return "Scan speed (nm/s)"


def scan_step_label(domain: TuningDomain | int | None) -> str:
    return f"Step size ({tuning_value_unit(domain)})"

SCAN_MODE_OPTIONS: dict[int, str] = {
    int(ScanMode.AUTOMATIC_STEP): "Automatic step",
    int(ScanMode.UNI_FORWARD): "Unidirectional forward",
    int(ScanMode.BI_DIRECTIONAL): "Bidirectional",
    int(ScanMode.UNI_REVERSE): "Unidirectional reverse",
}

TRIGGER_POLARITY_OPTIONS: dict[int, str] = {
    int(TriggerPolarity.ACTIVE_LOW): "Active low",
    int(TriggerPolarity.ACTIVE_HIGH): "Active high",
}

POWER_UNIT_OPTIONS: dict[int, str] = {
    int(PowerUnit.DBM): "dBm",
    int(PowerUnit.MW): "mW",
}

MODULATION_OPTIONS: dict[int, str] = {
    int(ModulationSource.NONE): "None",
    int(ModulationSource.COHERENCE_CONTROL): "Coherence control",
    int(ModulationSource.EXTERNAL_ANALOG): "External analog",
}

LOOP_MODE_LABELS: dict[int, str] = {
    0: "Constant power",
    1: "Constant current",
}

INTERLOCK_LABELS: dict[int, str] = {
    0: "Off (ready)",
    1: "Software interlock active",
    2: "Hardware interlock active",
    3: "Software and hardware active",
}

