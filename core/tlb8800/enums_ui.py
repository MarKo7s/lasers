"""Human-readable labels for TLB-8800 instrument enums (UI dropdowns)."""

from __future__ import annotations

from newfocus.tlb8800_utilities.types import (
    ModulationSource,
    PowerUnit,
    ScanMode,
    TuningDomain,
)

TUNING_DOMAIN_OPTIONS: dict[int, str] = {
    int(TuningDomain.WAVELENGTH): "Wavelength (nm)",
    int(TuningDomain.FREQUENCY): "Frequency",
}

SCAN_MODE_OPTIONS: dict[int, str] = {
    int(ScanMode.AUTOMATIC_STEP): "Automatic step",
    int(ScanMode.UNI_FORWARD): "Unidirectional forward",
    int(ScanMode.BI_DIRECTIONAL): "Bidirectional",
    int(ScanMode.UNI_REVERSE): "Unidirectional reverse",
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
