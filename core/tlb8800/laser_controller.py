"""Connected laser session: connect, refresh, and apply set commands."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, Iterable, Optional, TypeVar, Union

from laser.newfocus import TLB8800
from laser.newfocus.tlb8800_utilities.spec_fields import (
    TUNING_DOMAIN_SPEC_FIELDS,
)
from laser.newfocus.tlb8800_utilities.types import (
    LaserSpecs,
    ModulationSource,
    PowerUnit,
    ScanMode,
    TriggerPolarity,
    TuningDomain,
)

from laser.core.models import StatusMessage
from laser.core.tlb8800.control_bindings import bindings_from_specs
from laser.core.tlb8800.models import ControlBindings
from laser.core.tlb8800.status import status_from_command_result

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
        self._owns_connection = True

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
            if self._owns_connection:
                self._laser.close()
            self._laser = None
            self._owns_connection = True

    def attach(self, laser: TLB8800, *, owns_connection: bool = False) -> LaserSpecs:
        """Wrap an already-open ``TLB8800`` without opening a new port."""

        def work() -> LaserSpecs:
            self._disconnect_unlocked()
            if not laser.is_open:
                raise RuntimeError("Laser is not connected")
            self._laser = laser
            self._owns_connection = owns_connection
            try:
                _ = laser.specs
            except RuntimeError:
                laser.refresh_specs()
            return self.specs

        return self._execute_serial("attach", work)

    def connect(self, port: str) -> LaserSpecs:
        def work() -> LaserSpecs:
            self._disconnect_unlocked()
            self._laser = TLB8800.connect(port, refresh_specs=True)
            self._owns_connection = True
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

    def check_errors(self) -> StatusMessage:
        """Query ``errcnt?``; if count > 0, read and clear ``err?`` with descriptions."""

        def work() -> StatusMessage:
            from laser.newfocus.tlb8800_utilities.errors import error_description

            try:
                count = int(self.laser.read.error_count())
            except Exception as exc:
                return StatusMessage.failure(f"errcnt? failed: {exc}", command="errcnt?")

            if count <= 0:
                return StatusMessage.success("No errors (errcnt=0)", command="errcnt?")

            try:
                codes = [c for c in self.laser.read.all_error_codes() if c != 0]
            except Exception as exc:
                return StatusMessage.failure(
                    f"errcnt={count} but err? failed: {exc}",
                    command="err?",
                )

            if not codes:
                return StatusMessage.success(
                    f"errcnt={count} but err? returned no non-zero codes",
                    command="err?",
                )

            parts = [f"{c}: {error_description(c)}" for c in codes]
            return StatusMessage.failure(
                f"errcnt={count} — " + "; ".join(parts),
                command="err?",
            )

        return self._execute_serial("check_errors", work)

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
                self._refresh_specs_fields(("power", "loop_mode"))
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
                self._refresh_specs_fields(("current", "loop_mode"))
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
            value = float(setpoint)
            wl_min = self.specs.wavelength_min
            wl_max = self.specs.wavelength_max
            if wl_min is not None and value < wl_min:
                return StatusMessage.failure(
                    f"Tune {value} below minimum {wl_min}",
                    command="wave",
                )
            if wl_max is not None and value > wl_max:
                return StatusMessage.failure(
                    f"Tune {value} above maximum {wl_max}",
                    command="wave",
                )
            result = self.laser.set.tune(value, wait=wait)
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
        speed_int = int(round(float(speed)))
        return self._execute_serial(
            "scan_speed",
            lambda: self._apply_scan_field(self.laser.set.scan_speed(speed_int), "scan_speed"),
        )

    def apply_scan_cycles(self, cycles: int) -> StatusMessage:
        return self._execute_serial(
            "scan_cycles",
            lambda: self._apply_scan_field(self.laser.set.scan_cycles(cycles), "scan_cycles"),
        )

    def apply_scan_dwell(self, dwell_ms: Union[int, float]) -> StatusMessage:
        def work() -> StatusMessage:
            value = float(dwell_ms)
            if value < 0:
                return StatusMessage.failure(
                    f"Dwell must be ≥ 0 (got {value})",
                    command="dwl",
                )
            return self._apply_scan_field(
                self.laser.set.scan_dwell_time_ms(value), "scan_dwell_time_ms"
            )

        return self._execute_serial("scan_dwell", work)

    def apply_scan_step(self, step: Union[int, float]) -> StatusMessage:
        def work() -> StatusMessage:
            value = float(step)
            if value <= 0:
                return StatusMessage.failure(
                    f"Scan step must be > 0 (got {value})",
                    command="step",
                )
            return self._apply_scan_field(
                self.laser.set.scan_step_size(value), "scan_step_size"
            )

        return self._execute_serial("scan_step", work)

    def apply_scan_mode(self, mode: ScanMode) -> StatusMessage:
        return self._execute_serial(
            "scan_mode",
            lambda: self._apply_scan_field(self.laser.set.scan_mode(mode), "scan_mode"),
        )

    def apply_trigger_polarity(self, polarity: TriggerPolarity) -> StatusMessage:
        return self._execute_serial(
            "trigger_polarity",
            lambda: self._apply_scan_field(
                self.laser.set.trigger_polarity(polarity), "trigger_polarity"
            ),
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
        trigger_polarity: Optional[TriggerPolarity] = None,
    ) -> StatusMessage:
        def work() -> StatusMessage:
            specs = self.specs
            ok = True
            command = "scan params"
            applied = 0
            failures: list[str] = []
            refreshed: set[str] = set()

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

            if start is not None:
                _step("scan start", self.laser.set.scan_start(start), "scan_start")
            if stop is not None:
                _step("scan stop", self.laser.set.scan_stop(stop), "scan_stop")
            if speed is not None:
                speed_int = int(round(float(speed)))
                if specs.scan_speed_min is not None and speed_int < specs.scan_speed_min:
                    return StatusMessage.failure(
                        f"Scan speed {speed_int} below minimum {specs.scan_speed_min}",
                        command="spd",
                    )
                if specs.scan_speed_max is not None and speed_int > specs.scan_speed_max:
                    return StatusMessage.failure(
                        f"Scan speed {speed_int} above maximum {specs.scan_speed_max}",
                        command="spd",
                    )
                _step("scan speed", self.laser.set.scan_speed(speed_int), "scan_speed")
            if dwell_ms is not None:
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
            if cycles is not None:
                _step("scan cycles", self.laser.set.scan_cycles(cycles), "scan_cycles")
            if mode is not None:
                _step("scan mode", self.laser.set.scan_mode(mode), "scan_mode")
            if trigger_polarity is not None:
                _step(
                    "trigger polarity",
                    self.laser.set.trigger_polarity(trigger_polarity),
                    "trigger_polarity",
                )
            if step is not None:
                if step <= 0:
                    return StatusMessage.failure(
                        f"Scan step must be > 0 (got {step})",
                        command="step",
                    )
                _step("scan step", self.laser.set.scan_step_size(step), "scan_step_size")

            if applied == 0:
                return StatusMessage.success("No scan parameters provided", command=command)

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
