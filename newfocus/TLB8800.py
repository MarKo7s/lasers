"""TLB-8800 Venturi swept-wavelength tunable laser driver (manual §5.4)."""

from __future__ import annotations

import time
from typing import Optional, TypeVar, Union

from newfocus.tlb8800_utilities.commands import TLBReadCommands, TLBSetCommands
from newfocus.tlb8800_utilities.errors import (
    CommandResult,
    TLB8800ExecutionError,
    TLB8800ParseError,
    error_description,
    interpret_protocol_response,
    parse_error_codes,
)
from newfocus.tlb8800_utilities.logging_paths import (
    instrument_log_path,
    laser_id_from_idn,
    sanitize_log_id,
)
from newfocus.tlb8800_utilities.protocol import (
    DEFAULT_BAUDRATE,
    DEFAULT_TIMEOUT,
    SerialTransport,
    parse_numeric_response,
)
from newfocus.tlb8800_utilities.session_log import LaserSessionLogger
from newfocus.tlb8800_utilities.spec_fields import ALL_SPEC_FIELDS
from newfocus.tlb8800_utilities.spec_refresh import refresh_laser_specs_fields
from newfocus.tlb8800_utilities.types import LaserIdentity, LaserSpecs, OperationCompleteState

from newfocus.tlb8800_utilities.types import (  # noqa: F401
    FanSpeed,
    InterlockState,
    LoopMode,
    ModulationSource,
    PowerUnit,
    ScanMode,
    TriggerPolarity,
    TuningDomain,
)

T = TypeVar("T")


class TLB8800:
    """
    TLB-8800 laser connection with decoupled read/set command facades.

        laser = TLB8800.connect("COM3")
        laser.read.laser_output()
        laser.set.power(-3)
        laser.ON()
        laser.close()
    """

    MODEL_PREFIX = "TLB-8800"

    def __init__(
        self,
        transport: SerialTransport,
        *,
        identity: Optional[LaserIdentity] = None,
        session_log: Optional[LaserSessionLogger] = None,
    ) -> None:
        self._transport = transport
        self._identity = identity
        self._session_log = session_log
        self._specs: Optional[LaserSpecs] = None
        self.read = TLBReadCommands(self)
        self.set = TLBSetCommands(self)

    @classmethod
    def connect(
        cls,
        port: str,
        *,
        baudrate: int = DEFAULT_BAUDRATE,
        timeout: float = DEFAULT_TIMEOUT,
        enable_log: bool = True,
        refresh_specs: bool = True,
    ) -> "TLB8800":
        """Open serial port; optional session log under ProgramData."""
        transport = SerialTransport(port, baudrate=baudrate, timeout=timeout)
        session_log: Optional[LaserSessionLogger] = None

        if enable_log:
            try:
                transport.flush()
                bootstrap_idn = transport.query("*IDN?", timeout=timeout).strip()
                laser_id = laser_id_from_idn(bootstrap_idn)
            except (TimeoutError, OSError):
                bootstrap_idn = ""
                laser_id = sanitize_log_id(port)

            log_path = instrument_log_path(laser_id)
            session_log = LaserSessionLogger(log_path, port=port, log_id=laser_id)
            if bootstrap_idn:
                session_log.log_read("*IDN?", bootstrap_idn)

        laser = cls(transport, session_log=session_log)
        if refresh_specs:
            laser.refresh_specs()
        return laser

    def set_logger_level(self, level: Union[int, str]) -> int:
        if self._session_log is None:
            raise RuntimeError("Logging is disabled for this connection")
        return self._session_log.set_level(level)

    @property
    def port(self) -> str:
        return self._transport.port

    @property
    def laser_id(self) -> Optional[str]:
        if self._session_log is None:
            return None
        return self._session_log.log_id

    @property
    def log_path(self) -> Optional[str]:
        if self._session_log is None:
            return None
        return str(self._session_log.log_path)

    @property
    def identity(self) -> LaserIdentity:
        if self._identity is None:
            self._identity = self.read.identify()
        return self._identity

    @property
    def specs(self) -> LaserSpecs:
        if self._specs is None:
            raise RuntimeError(
                "Laser specs not loaded; call refresh_specs() or connect(refresh_specs=True)"
            )
        return self._specs

    def refresh_specs_fields(self, *fields: str) -> LaserSpecs:
        """Re-query only the given ``LaserSpecs`` fields and update the cached snapshot."""
        if self._specs is None:
            raise RuntimeError(
                "Laser specs not loaded; call refresh_specs() or connect(refresh_specs=True)"
            )
        self._specs = refresh_laser_specs_fields(self, self._specs, fields)
        return self._specs

    def _initial_specs(self) -> LaserSpecs:
        """Placeholder snapshot before the first field refresh."""
        loop_mode = None
        try:
            loop_mode = self.read.loop_mode()
        except (TLB8800ParseError, TimeoutError, OSError, ValueError):
            pass
        current_control = loop_mode == LoopMode.CONSTANT_CURRENT
        return LaserSpecs(
            current_control=current_control,
            loop_mode=loop_mode,
            identity=None,
            laser_output=None,
            interlock_state=None,
            operation_complete=None,
            power=None,
            power_min=None,
            power_max=None,
            power_unit=None,
            current=None,
            current_max=None,
            tuning_domain=None,
            wavelength_min=None,
            wavelength_max=None,
            tune_setpoint=None,
            modulation_source=None,
            scan_start=None,
            scan_start_acceleration_offset=None,
            scan_stop=None,
            scan_stop_deceleration_offset=None,
            scan_step_size=None,
            scan_mode=None,
            scan_speed=None,
            scan_speed_min=None,
            scan_speed_max=None,
            scan_dwell_time_ms=None,
            scan_cycles=None,
            scan_cycles_count=None,
            laser_diode_temperature_setpoint=None,
            laser_diode_temperature=None,
            environment_temperature=None,
            temperature_regulated=None,
            fan_override=None,
            fan_speed=None,
            trigger_polarity=None,
            trigger_a_enabled=None,
            trigger_b_enabled=None,
            operating_hours=None,
            error_count=None,
            error_codes=None,
        )

    def refresh_specs(self) -> LaserSpecs:
        """Query full laser state; unsupported or failed reads become None."""
        if self._specs is None:
            self._specs = self._initial_specs()
        return self.refresh_specs_fields(*ALL_SPEC_FIELDS)

    def close(self) -> None:
        session_log = self._session_log
        if session_log is not None:
            session_log.close()
            self._session_log = None
        self._transport.close()

    def __enter__(self) -> "TLB8800":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def ON(self, *, clear_interlock: bool = True) -> CommandResult:
        if clear_interlock:
            self.set.software_interlock(False)
        return self.set.laser_output(True)

    def OFF(self) -> CommandResult:
        return self.set.laser_output(False)

    def wait_until_complete(
        self,
        *,
        poll_interval: float = 0.05,
        timeout: float = 120.0,
    ) -> OperationCompleteState:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = OperationCompleteState(int(self.read.operation_complete()))
            if state not in (OperationCompleteState.PENDING, OperationCompleteState.INITIALIZING):
                return state
            time.sleep(poll_interval)
        raise TimeoutError("Timed out waiting for TLB-8800 operation to complete")

    def reboot(self) -> None:
        self._transport.write_command("reboot")
        if self._session_log is not None:
            self._session_log.log_write("reboot", note="no ACK expected")

    def clear_errors(self) -> list[int]:
        return self.read.all_error_codes()

    def raise_if_error(self) -> None:
        for code in self.read.all_error_codes():
            if code != 0:
                raise TLB8800ExecutionError(code, error_description(code))

    def describe_error_code(self, code: int) -> str:
        return error_description(code)

    def _query(self, command: str, *, timeout: Optional[float] = None) -> str:
        response = self._transport.query(command, timeout=timeout)
        if self._session_log is not None:
            self._session_log.log_read(command, response)
        return response

    def _query_numeric(self, command: str, *, timeout: Optional[float] = None) -> Union[int, float]:
        response = self._query(command, timeout=timeout)
        try:
            return parse_numeric_response(response)
        except ValueError as exc:
            raise TLB8800ParseError(response, str(exc)) from exc

    def _query_silent(self, command: str, *, timeout: Optional[float] = None) -> str:
        return self._transport.query(command, timeout=timeout)

    def _command(
        self,
        command: str,
        *,
        timeout: Optional[float] = None,
        fetch_errors: bool = True,
    ) -> CommandResult:
        response = self._transport.query(command, timeout=timeout).strip()
        ok = response == "*"
        message = interpret_protocol_response(response)
        codes: list[int] = []
        if not ok and fetch_errors:
            try:
                raw_err = self._query_silent("err?")
                codes = [c for c in parse_error_codes(raw_err) if c != 0]
            except (ValueError, TimeoutError, OSError):
                pass
        if self._session_log is not None:
            self._session_log.log_set(
                command,
                response,
                error_codes=codes,
                error_messages=tuple(error_description(c) for c in codes),
            )
        return CommandResult(
            command=command,
            response=response,
            ok=ok,
            message=message,
            error_codes=tuple(codes),
            error_messages=tuple(error_description(c) for c in codes),
        )
