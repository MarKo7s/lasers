"""Connected laser session: connect, refresh, and apply set commands."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, Iterable, Optional, TypeVar, Union

from newfocus import TLB8800
from newfocus.tlb8800_utilities.spec_fields import (
    TUNING_DOMAIN_SPEC_FIELDS,
)
from newfocus.tlb8800_utilities.types import (
    LaserSpecs,
    ModulationSource,
    PowerUnit,
    ScanMode,
    TuningDomain,
)

from core.models import StatusMessage
from core.tlb8800.control_bindings import bindings_from_specs
from core.tlb8800.models import ControlBindings
from core.tlb8800.status import status_from_command_result

T = TypeVar("T")


@dataclass(frozen=True)
class TelemetrySnapshot:
    laser_diode_temperature: Optional[float] = None
    environment_temperature: Optional[float] = None
    temperature_regulated: Optional[bool] = None
    operating_hours: Optional[float] = None
    scan_cycles_count: Optional[int] = None
    interlock_state: Optional[int] = None
    laser_output: Optional[bool] = None


class TLB8800Controller:
    """Wraps TLB8800 for UI-friendly connect/apply/refresh (thread-safe serial)."""

    def __init__(self) -> None:
        self._laser: Optional[TLB8800] = None
        self._serial_lock = threading.RLock()

    @property
    def is_connected(self) -> bool:
        return self._laser is not None

    @property
    def laser(self) -> TLB8800:
        if self._laser is None:
            raise RuntimeError("Not connected to a laser")
        return self._laser

    @property
    def specs(self) -> LaserSpecs:
        return self.laser.specs

    @property
    def bindings(self) -> ControlBindings:
        return bindings_from_specs(self.specs)

    def _execute_serial(self, _op: str, fn: Callable[[], T]) -> T:
        with self._serial_lock:
            return fn()

    def _refresh_specs_fields(self, fields: Iterable[str]) -> None:
        """Re-query only the given cached ``LaserSpecs`` fields from the instrument."""
        field_list = tuple(fields)
        if field_list:
            self.laser.refresh_specs_fields(*field_list)

    def _disconnect_unlocked(self) -> None:
        if self._laser is not None:
            self._laser.close()
            self._laser = None

    def connect(self, port: str) -> LaserSpecs:
        def work() -> LaserSpecs:
            self._disconnect_unlocked()
            self._laser = TLB8800.connect(port, refresh_specs=True)
            return self.specs

        return self._execute_serial("connect", work)

    def disconnect(self) -> None:
        def work() -> None:
            self._disconnect_unlocked()

        self._execute_serial("disconnect", work)

    def refresh(self) -> LaserSpecs:
        return self._execute_serial("refresh", lambda: self.laser.refresh_specs())

    def refresh_telemetry(self) -> TelemetrySnapshot:
        """Lightweight poll (few queries) for UI timer — avoids full refresh_specs."""

        def work() -> TelemetrySnapshot:
            r = self.laser.read

            def _ro(fn: Callable[[], object]) -> Optional[object]:
                try:
                    return fn()
                except Exception:
                    return None

            interlock = _ro(r.interlock_state)
            return TelemetrySnapshot(
                laser_diode_temperature=_ro(r.laser_diode_temperature),
                environment_temperature=_ro(r.environment_temperature),
                temperature_regulated=_ro(r.temperature_regulated),
                operating_hours=_ro(r.operating_hours),
                scan_cycles_count=_ro(r.scan_cycles_count),
                interlock_state=int(interlock) if interlock is not None else None,
                laser_output=_ro(r.laser_output),
            )

        return self._execute_serial("refresh_telemetry", work)

    def apply_laser_output(self, enabled: bool) -> StatusMessage:
        def work() -> StatusMessage:
            if enabled:
                status = status_from_command_result(
                    self.laser.ON(clear_interlock=False)
                )
            else:
                status = status_from_command_result(self.laser.OFF())
            if status.ok:
                self._refresh_specs_fields(("laser_output", "interlock_state"))
            return status

        return self._execute_serial("laser_output", work)

    def apply_software_interlock_inhibit(self, inhibit: bool) -> StatusMessage:
        def work() -> StatusMessage:
            status = status_from_command_result(
                self.laser.set.software_interlock(inhibit)
            )
            if status.ok:
                self._refresh_specs_fields(("interlock_state",))
            return status

        return self._execute_serial("software_interlock", work)

    def apply_power(self, value: Union[int, float]) -> StatusMessage:
        def work() -> StatusMessage:
            result = self.laser.set.power(value)
            if result.ok:
                self._refresh_specs_fields(("power",))
            return status_from_command_result(result)

        return self._execute_serial("power", work)

    def apply_power_unit(self, unit: PowerUnit) -> StatusMessage:
        def work() -> StatusMessage:
            result = self.laser.set.power_unit(unit)
            if result.ok:
                self._refresh_specs_fields(("power_unit",))
            return status_from_command_result(result)

        return self._execute_serial("power_unit", work)

    def apply_current(self, milliamps: Union[int, float]) -> StatusMessage:
        def work() -> StatusMessage:
            result = self.laser.set.current(milliamps)
            if result.ok:
                self._refresh_specs_fields(("current",))
            return status_from_command_result(result)

        return self._execute_serial("current", work)

    def apply_tuning_domain(self, domain: TuningDomain) -> StatusMessage:
        def work() -> StatusMessage:
            result = self.laser.set.tuning_domain(domain)
            if result.ok:
                self._refresh_specs_fields(TUNING_DOMAIN_SPEC_FIELDS)
            return status_from_command_result(result)

        return self._execute_serial("tuning_domain", work)

    def apply_tune(self, setpoint: Union[int, float], *, wait: bool = True) -> StatusMessage:
        def work() -> StatusMessage:
            result = self.laser.set.tune(setpoint, wait=wait)
            if result.ok:
                self._refresh_specs_fields(("tune_setpoint", "operation_complete"))
            return status_from_command_result(result)

        return self._execute_serial("tune", work)

    def apply_modulation(self, source: ModulationSource) -> StatusMessage:
        def work() -> StatusMessage:
            result = self.laser.set.modulation_source(source)
            if result.ok:
                self._refresh_specs_fields(("modulation_source",))
            return status_from_command_result(result)

        return self._execute_serial("modulation", work)

    def apply_tuning(
        self,
        *,
        domain: Optional[TuningDomain] = None,
        tune_nm: Optional[float] = None,
        modulation: Optional[ModulationSource] = None,
        wait_tune: bool = True,
    ) -> StatusMessage:
        """Apply tuning domain, wavelength, and modulation in one serial session."""

        def work() -> StatusMessage:
            messages: list[str] = []
            ok = True
            command = "apply_tuning"
            specs = self.specs

            failures: list[str] = []

            def _step(name: str, status: StatusMessage) -> None:
                nonlocal ok, command
                if status.ok:
                    messages.append(f"{name}: OK")
                else:
                    ok = False
                    failures.append(f"{name}: {status.summary}")
                    if status.command:
                        command = status.command

            refreshed: set[str] = set()
            if domain is not None:
                current = int(specs.tuning_domain) if specs.tuning_domain is not None else None
                if current != int(domain):
                    domain_status = status_from_command_result(
                        self.laser.set.tuning_domain(domain)
                    )
                    _step("tuning domain", domain_status)
                    if domain_status.ok:
                        refreshed.update(TUNING_DOMAIN_SPEC_FIELDS)
                        self._refresh_specs_fields(TUNING_DOMAIN_SPEC_FIELDS)
                        specs = self.laser.specs

            if tune_nm is not None:
                wl_min = specs.wavelength_min
                wl_max = specs.wavelength_max
                if wl_min is not None and tune_nm < wl_min:
                    return StatusMessage.failure(
                        f"Tune {tune_nm} below minimum {wl_min}",
                        command="wave",
                    )
                if wl_max is not None and tune_nm > wl_max:
                    return StatusMessage.failure(
                        f"Tune {tune_nm} above maximum {wl_max}",
                        command="wave",
                    )
                tune_status = status_from_command_result(
                    self.laser.set.tune(tune_nm, wait=wait_tune)
                )
                _step("tune", tune_status)
                if tune_status.ok:
                    refreshed.update(("tune_setpoint", "operation_complete"))

            if modulation is not None:
                current_mod = (
                    int(specs.modulation_source)
                    if specs.modulation_source is not None
                    else None
                )
                if current_mod != int(modulation):
                    mod_status = status_from_command_result(
                        self.laser.set.modulation_source(modulation)
                    )
                    _step("modulation", mod_status)
                    if mod_status.ok:
                        refreshed.add("modulation_source")

            if not messages:
                return StatusMessage.success("No tuning changes to apply", command=command)

            if refreshed:
                self._refresh_specs_fields(refreshed)

            if failures:
                summary = "; ".join(failures)
            elif ok:
                summary = "; ".join(messages) if len(messages) > 1 else messages[0]
            else:
                summary = "Tuning command failed"
            return StatusMessage(ok=ok, summary=summary, command=command)

        return self._execute_serial("apply_tuning", work)

    def _apply_scan_field(self, result, field: str) -> StatusMessage:
        status = status_from_command_result(result)
        if status.ok:
            self._refresh_specs_fields((field,))
        return status

    def apply_scan_start(self, value: Union[int, float]) -> StatusMessage:
        return self._execute_serial(
            "scan_start",
            lambda: self._apply_scan_field(self.laser.set.scan_start(value), "scan_start"),
        )

    def apply_scan_stop(self, value: Union[int, float]) -> StatusMessage:
        return self._execute_serial(
            "scan_stop",
            lambda: self._apply_scan_field(self.laser.set.scan_stop(value), "scan_stop"),
        )

    def apply_scan_speed(self, speed: Union[int, float]) -> StatusMessage:
        return self._execute_serial(
            "scan_speed",
            lambda: self._apply_scan_field(self.laser.set.scan_speed(speed), "scan_speed"),
        )

    def apply_scan_cycles(self, cycles: int) -> StatusMessage:
        return self._execute_serial(
            "scan_cycles",
            lambda: self._apply_scan_field(self.laser.set.scan_cycles(cycles), "scan_cycles"),
        )

    def apply_scan_dwell(self, dwell_ms: Union[int, float]) -> StatusMessage:
        return self._execute_serial(
            "scan_dwell",
            lambda: self._apply_scan_field(
                self.laser.set.scan_dwell_time_ms(dwell_ms), "scan_dwell_time_ms"
            ),
        )

    def apply_scan_step(self, step: Union[int, float]) -> StatusMessage:
        return self._execute_serial(
            "scan_step",
            lambda: self._apply_scan_field(
                self.laser.set.scan_step_size(step), "scan_step_size"
            ),
        )

    def apply_scan_mode(self, mode: ScanMode) -> StatusMessage:
        return self._execute_serial(
            "scan_mode",
            lambda: self._apply_scan_field(self.laser.set.scan_mode(mode), "scan_mode"),
        )

    def apply_scan_params(
        self,
        *,
        start: Optional[float] = None,
        stop: Optional[float] = None,
        speed: Optional[float] = None,
        cycles: Optional[int] = None,
        dwell_ms: Optional[float] = None,
        step: Optional[float] = None,
        mode: Optional[ScanMode] = None,
    ) -> StatusMessage:
        def work() -> StatusMessage:
            specs = self.specs
            ok = True
            command = "scan params"
            applied = 0
            failures: list[str] = []
            refreshed: set[str] = set()

            def _changed(new: float, old: Optional[float], *, eps: float = 1e-6) -> bool:
                if old is None:
                    return True
                return abs(float(new) - float(old)) > eps

            def _step(name: str, result, *fields: str) -> None:
                nonlocal ok, command, applied

                status = status_from_command_result(result)
                applied += 1
                if status.ok:
                    refreshed.update(fields)
                    return
                ok = False
                if status.command:
                    command = status.command
                failures.append(f"{name}: {status.summary}")

            if start is not None and stop is not None and float(start) > float(stop):
                return StatusMessage.failure(
                    f"Scan start ({start}) must be ≤ scan stop ({stop})",
                    command="scan params",
                )

            current_mode = int(specs.scan_mode) if specs.scan_mode is not None else None
            target_mode = int(mode) if mode is not None else current_mode

            if start is not None and _changed(start, specs.scan_start):
                _step("scan start", self.laser.set.scan_start(start), "scan_start")
            if stop is not None and _changed(stop, specs.scan_stop):
                _step("scan stop", self.laser.set.scan_stop(stop), "scan_stop")
            if speed is not None and _changed(speed, specs.scan_speed):
                if specs.scan_speed_min is not None and speed < specs.scan_speed_min:
                    return StatusMessage.failure(
                        f"Scan speed {speed} below minimum {specs.scan_speed_min}",
                        command="spd",
                    )
                if specs.scan_speed_max is not None and speed > specs.scan_speed_max:
                    return StatusMessage.failure(
                        f"Scan speed {speed} above maximum {specs.scan_speed_max}",
                        command="spd",
                    )
                _step("scan speed", self.laser.set.scan_speed(speed), "scan_speed")
            if dwell_ms is not None and _changed(dwell_ms, specs.scan_dwell_time_ms):
                if dwell_ms < 0:
                    return StatusMessage.failure(
                        f"Dwell must be ≥ 0 (got {dwell_ms})",
                        command="dwl",
                    )
                _step(
                    "scan dwell",
                    self.laser.set.scan_dwell_time_ms(dwell_ms),
                    "scan_dwell_time_ms",
                )
            if cycles is not None and _changed(float(cycles), float(specs.scan_cycles or 0), eps=0.5):
                _step("scan cycles", self.laser.set.scan_cycles(cycles), "scan_cycles")
            if mode is not None and current_mode != int(mode):
                mode_result = self.laser.set.scan_mode(mode)
                _step("scan mode", mode_result, "scan_mode")
                if "scan_mode" in refreshed:
                    self._refresh_specs_fields(("scan_mode",))
                    refreshed.discard("scan_mode")
                    specs = self.laser.specs
                    current_mode = int(mode)
                    target_mode = current_mode

            if step is not None and _changed(step, specs.scan_step_size):
                if step <= 0:
                    return StatusMessage.failure(
                        f"Scan step must be > 0 (got {step})",
                        command="step",
                    )
                if target_mode != int(ScanMode.AUTOMATIC_STEP):
                    return StatusMessage.failure(
                        "Scan step size only applies when scan mode is Automatic step",
                        command="scan params",
                    )
                _step("scan step", self.laser.set.scan_step_size(step), "scan_step_size")

            if applied == 0:
                return StatusMessage.success("No scan parameter changes to apply", command=command)

            if refreshed:
                self._refresh_specs_fields(refreshed)
            if failures:
                summary = "; ".join(failures)
            else:
                summary = f"Applied {applied} scan parameter(s) successfully."
            return StatusMessage(ok=ok, summary=summary, command=command)

        return self._execute_serial("scan_params", work)

    def start_scan(self, *, wait: bool = False) -> StatusMessage:
        def work() -> StatusMessage:
            result = self.laser.set.start_scan(wait=wait)
            if result.ok:
                self._refresh_specs_fields(("scan_cycles_count", "operation_complete"))
            return status_from_command_result(result)

        return self._execute_serial("start_scan", work)

    def abort_scan(self) -> StatusMessage:
        def work() -> StatusMessage:
            result = self.laser.set.abort_scan()
            if result.ok:
                self._refresh_specs_fields(("scan_cycles_count", "operation_complete"))
            return status_from_command_result(result)

        return self._execute_serial("abort_scan", work)
