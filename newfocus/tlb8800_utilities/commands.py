"""TLB-series Legacy read (query) and set command facades."""

from __future__ import annotations

from typing import Union

from newfocus.tlb8800_utilities.errors import CommandResult, TLB8800ParseError, parse_error_codes
from newfocus.tlb8800_utilities.idn import parse_idn
from newfocus.tlb8800_utilities.types import (
    FanSpeed,
    InterlockState,
    LaserIdentity,
    LoopMode,
    ModulationSource,
    PowerUnit,
    ScanMode,
    TriggerPolarity,
    TuningDomain,
)

class TLBReadCommands:
    """Legacy read/query commands (``laser.read.<name>()``)."""

    __slots__ = ("_laser",)

    def __init__(self, laser: "TLB8800") -> None:
        self._laser = laser

    # --- Identification & system ---

    def identify(self) -> LaserIdentity:
        raw = self._laser._query("id?")
        parsed = parse_idn(raw)
        if parsed is None:
            raise TLB8800ParseError(raw, "response is not a valid New Focus IDN string")
        return LaserIdentity(
            manufacturer=parsed["manufacturer"],
            model=parsed["model"],
            customer_serial=parsed["customer_serial"],
            nf_serial=parsed["nf_serial"],
            firmware_version=parsed["firmware_version"],
            fpga_version=parsed["fpga_version"],
            raw_idn=parsed["raw_idn"],
        )

    def operation_complete(self) -> int:
        return int(self._laser._query_numeric("opc?"))

    def interlock_state(self) -> InterlockState:
        return InterlockState(int(self._laser._query_numeric("int?")))

    def laser_output(self) -> bool:
        return bool(int(self._laser._query_numeric("laz?")))

    def loop_mode(self) -> LoopMode:
        return LoopMode(int(self._laser._query_numeric("loop?")))

    # --- Power ---

    def power_max(self) -> float:
        return float(self._laser._query_numeric("pmax?"))

    def power_min(self) -> float:
        return float(self._laser._query_numeric("pmin?"))

    def power(self) -> float:
        return float(self._laser._query_numeric("pwr?"))

    def power_unit(self) -> PowerUnit:
        return PowerUnit(int(self._laser._query_numeric("pwru?")))

    # --- Current ---

    def current(self) -> float:
        return float(self._laser._query_numeric("crnt?"))

    def current_max(self) -> float:
        return float(self._laser._query_numeric("crntmax?"))

    # --- Wavelength / frequency ---

    def tuning_domain(self) -> TuningDomain:
        return TuningDomain(int(self._laser._query_numeric("unit?")))

    def wavelength_max(self) -> float:
        return float(self._laser._query_numeric("wmax?"))

    def wavelength_min(self) -> float:
        return float(self._laser._query_numeric("wmin?"))

    def tune_setpoint(self) -> float:
        return float(self._laser._query_numeric("wave?"))

    # --- Modulation ---

    def modulation_source(self) -> ModulationSource:
        return ModulationSource(int(self._laser._query_numeric("sms?")))

    # --- Scan ---

    def scan_start(self) -> float:
        return float(self._laser._query_numeric("str?"))

    def scan_start_acceleration_offset(self) -> float:
        return float(self._laser._query_numeric("staccoff?"))

    def scan_stop(self) -> float:
        return float(self._laser._query_numeric("stop?"))

    def scan_stop_deceleration_offset(self) -> float:
        return float(self._laser._query_numeric("stdecoff?"))

    def scan_step_size(self) -> float:
        return float(self._laser._query_numeric("step?"))

    def scan_mode(self) -> ScanMode:
        return ScanMode(int(self._laser._query_numeric("mode?")))

    def scan_speed_max(self) -> float:
        return float(self._laser._query_numeric("spmax?"))

    def scan_speed_min(self) -> float:
        return float(self._laser._query_numeric("spmin?"))

    def scan_speed(self) -> float:
        return float(self._laser._query_numeric("spd?"))

    def scan_dwell_time_ms(self) -> float:
        return float(self._laser._query_numeric("dwl?"))

    def scan_cycles(self) -> int:
        return int(self._laser._query_numeric("num?"))

    def scan_cycles_count(self) -> int:
        return int(self._laser._query_numeric("cnt?"))

    # --- Temperature & cooling ---

    def laser_diode_temperature_setpoint(self) -> float:
        return float(self._laser._query_numeric("tset?"))

    def laser_diode_temperature(self) -> float:
        return float(self._laser._query_numeric("tmp?"))

    def environment_temperature(self) -> float:
        return float(self._laser._query_numeric("tmpe?"))

    def temperature_regulated(self) -> bool:
        return bool(int(self._laser._query_numeric("treg?")))

    def fan_override(self) -> bool:
        return bool(int(self._laser._query_numeric("for?")))

    def fan_speed(self) -> FanSpeed:
        return FanSpeed(int(self._laser._query_numeric("fspd?")))

    # --- Triggers ---

    def trigger_polarity(self) -> TriggerPolarity:
        return TriggerPolarity(int(self._laser._query_numeric("trpol?")))

    def trigger_a_enabled(self) -> bool:
        return int(self._laser._query_numeric("traen?")) == 0

    def trigger_b_enabled(self) -> bool:
        return int(self._laser._query_numeric("trben?")) == 0

    # --- Lifetime ---

    def operating_hours(self) -> float:
        return float(self._laser._query_numeric("ophours?"))

    # --- Errors ---

    def error_count(self) -> int:
        return int(self._laser._query_numeric("errcnt?"))

    def all_error_codes(self) -> list[int]:
        return parse_error_codes(self._laser._query("err?"))


class TLBSetCommands:
    """Legacy set commands (``laser.set.<name>()``) — returns CommandResult, does not raise on &, !, #."""

    __slots__ = ("_laser",)

    def __init__(self, laser: "TLB8800") -> None:
        self._laser = laser

    def software_interlock(self, inhibit: bool) -> CommandResult:
        """``int 1`` inhibits laser; ``int 0`` allows operation."""
        return self._laser._command(f"int {1 if inhibit else 0}")

    def laser_output(self, enabled: bool) -> CommandResult:
        return self._laser._command(f"laz {1 if enabled else 0}")

    def power(self, value: Union[int, float]) -> CommandResult:
        return self._laser._command(f"pwr {value}")

    def power_unit(self, unit: PowerUnit) -> CommandResult:
        return self._laser._command(f"pwru {int(unit)}")

    def current(self, milliamps: Union[int, float]) -> CommandResult:
        return self._laser._command(f"crnt {milliamps}")

    def tuning_domain(self, domain: TuningDomain) -> CommandResult:
        return self._laser._command(f"unit {int(domain)}")

    def tune(self, setpoint: Union[int, float], *, wait: bool = True) -> CommandResult:
        result = self._laser._command(f"wave {setpoint}")
        if wait and result.ok:
            self._laser.wait_until_complete()
        return result

    def modulation_source(self, source: ModulationSource) -> CommandResult:
        return self._laser._command(f"sms {int(source)}")

    def scan_start(self, setpoint: Union[int, float]) -> CommandResult:
        return self._laser._command(f"str {setpoint}")

    def scan_start_acceleration_offset(self, offset: Union[int, float]) -> CommandResult:
        return self._laser._command(f"staccoff {offset}")

    def scan_stop(self, setpoint: Union[int, float]) -> CommandResult:
        return self._laser._command(f"stop {setpoint}")

    def scan_stop_deceleration_offset(self, offset: Union[int, float]) -> CommandResult:
        return self._laser._command(f"stdecoff {offset}")

    def scan_step_size(self, step: Union[int, float]) -> CommandResult:
        return self._laser._command(f"step {step}")

    def scan_mode(self, mode: ScanMode) -> CommandResult:
        return self._laser._command(f"mode {int(mode)}")

    def scan_speed(self, speed: Union[int, float]) -> CommandResult:
        return self._laser._command(f"spd {speed}")

    def scan_dwell_time_ms(self, dwell_ms: Union[int, float]) -> CommandResult:
        return self._laser._command(f"dwl {dwell_ms}")

    def scan_cycles(self, cycles: int) -> CommandResult:
        """Use ``cycles=-1`` for infinite iterations."""
        return self._laser._command(f"num {cycles}")

    def start_scan(self, *, wait: bool = False) -> CommandResult:
        result = self._laser._command("scan")
        if wait and result.ok:
            self._laser.wait_until_complete()
        return result

    def abort_scan(self) -> CommandResult:
        return self._laser._command("abort")

    def next_scan_step(self) -> CommandResult:
        return self._laser._command("next")

    def trigger_polarity(self, polarity: TriggerPolarity) -> CommandResult:
        return self._laser._command(f"trpol {int(polarity)}")

    def trigger_a_enabled(self, enabled: bool) -> CommandResult:
        return self._laser._command(f"traen {0 if enabled else 1}")

    def trigger_b_enabled(self, enabled: bool) -> CommandResult:
        return self._laser._command(f"trben {0 if enabled else 1}")

    def preset(self) -> CommandResult:
        return self._laser._command("rst")
