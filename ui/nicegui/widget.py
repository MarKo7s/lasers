"""NiceGUI laser control widget (embeddable)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from nicegui import run, ui

from core.discovery_service import DiscoveryService
from core.factory import create_laser_controller
from core.models import DiscoveredDevice, StatusMessage
from core.tlb8800 import (
    INTERLOCK_LABELS,
    LOOP_MODE_LABELS,
    MODULATION_OPTIONS,
    POWER_UNIT_OPTIONS,
    SCAN_MODE_OPTIONS,
    TUNING_DOMAIN_OPTIONS,
    ControlBindings,
    NumericBinding,
    TelemetrySnapshot,
    TLB8800Controller,
    bindings_from_specs,
)
from newfocus.tlb8800_utilities.types import (
    ModulationSource,
    PowerUnit,
    ScanMode,
    TuningDomain,
)
from ui.nicegui.theme import apply_laser_theme, laser_header


def _bind_numeric(field: ui.number, binding: NumericBinding) -> None:
    """Apply bounds via NiceGUI's float min/max API (not .props(), which stores strings)."""
    if binding.minimum is not None:
        field.min = float(binding.minimum)
    else:
        field._props.pop("min", None)

    if binding.maximum is not None:
        field.max = float(binding.maximum)
    else:
        field._props.pop("max", None)

    field._props.set_optional("step", float(binding.step))
    field.set_enabled(binding.enabled)
    if binding.value is not None:
        field.set_value(float(binding.value))


def _numeric_value(field: ui.number) -> Optional[float]:
    raw = field.value
    if raw is None or raw == "":
        return None
    return float(raw)


def _section_title(text: str) -> None:
    ui.label(text).classes("laser-section-title q-mt-md q-mb-xs")


class LaserControlWidget:
    """Full laser control panel for NiceGUI applications."""

    def __init__(self, *, parent: Optional[ui.element] = None) -> None:
        self._discovery = DiscoveryService()
        self._controller: Optional[TLB8800Controller] = None
        self._devices: list[DiscoveredDevice] = []
        self._status_lines: list[str] = []
        self._telemetry_timer: Optional[ui.timer] = None
        self._telemetry_running = False
        self._updating_controls = False
        self._switch_handlers_enabled = False
        self._serial_handler_busy = False

        container = parent if parent is not None else ui.column().classes("w-full max-w-3xl mx-auto q-pa-md")
        with container:
            laser_header()
            with ui.card().classes("laser-panel w-full q-pa-md"):
                self._build_discovery()
                self._controls_card = ui.card().classes("laser-panel w-full q-pa-md q-mt-md")
                self._controls_card.set_visibility(False)
                with self._controls_card:
                    self._build_identity()
                    self._build_output()
                    self._build_regulation()
                    self._build_tuning()
                    self._build_scan()
                    self._build_telemetry()
            self._build_status()

        ui.timer(0.05, self._scan_on_load, once=True)

    # --- UI construction ---

    def _build_discovery(self) -> None:
        _section_title("Discovery")
        with ui.row().classes("w-full items-end q-gutter-sm"):
            self._device_select = ui.select(
                label="Available lasers",
                options={},
                with_input=True,
            ).classes("grow")
            self._refresh_btn = ui.button("Refresh", icon="refresh", on_click=self._on_refresh)
            self._connect_btn = ui.button("Connect", icon="link", on_click=self._on_connect)
            self._disconnect_btn = ui.button(
                "Disconnect",
                icon="link_off",
                on_click=self._on_disconnect,
            )
        self._disconnect_btn.set_visibility(False)
        self._discovery_hint = ui.label("Scanning USB ports…").classes("text-grey-6 text-caption")

    def _build_identity(self) -> None:
        _section_title("Instrument")
        self._identity_label = ui.label("—").classes("text-body2")

    def _build_output(self) -> None:
        _section_title("Output & safety")
        with ui.row().classes("items-center q-gutter-lg"):
            self._laser_switch = ui.switch("Laser output", on_change=self._on_laser_output)
            self._interlock_switch = ui.switch(
                "Software interlock (inhibit)",
                on_change=self._on_interlock,
            )
        self._interlock_state_label = ui.label("Interlock: —").classes("text-caption text-grey-5")

    def _build_regulation(self) -> None:
        _section_title("Regulation")
        self._loop_mode_label = ui.label("Loop mode: —").classes("text-caption q-mb-sm")
        with ui.row().classes("items-end q-gutter-md wrap"):
            self._power_input = ui.number("Power setpoint", format="%.3f")
            self._power_unit_select = ui.select(
                label="Power unit",
                options=POWER_UNIT_OPTIONS,
            )
            self._current_input = ui.number("Current (mA)", format="%.2f")
            ui.button("Apply regulation", icon="tune", on_click=self._on_apply_regulation)

    def _build_tuning(self) -> None:
        _section_title("Wavelength tuning")
        with ui.row().classes("items-end q-gutter-md wrap"):
            self._tuning_domain_select = ui.select(
                label="Tuning domain",
                options=TUNING_DOMAIN_OPTIONS,
            )
            self._tune_input = ui.number("Tune setpoint", format="%.4f")
            self._modulation_select = ui.select(
                label="Modulation",
                options=MODULATION_OPTIONS,
            )
            ui.button("Apply tuning", icon="waves", on_click=self._on_apply_tuning)

    def _build_scan(self) -> None:
        _section_title("Scan / sweep")
        with ui.grid(columns=2).classes("w-full q-gutter-sm"):
            self._scan_start_input = ui.number("Scan start", format="%.4f")
            self._scan_stop_input = ui.number("Scan stop", format="%.4f")
            self._scan_speed_input = ui.number("Scan speed", format="%.2f")
            self._scan_cycles_input = ui.number("Scan cycles (-1 = ∞)", format="%.0f")
            self._scan_dwell_input = ui.number("Dwell (ms)", format="%.1f")
            self._scan_step_input = ui.number("Step size", format="%.4f")
            self._scan_mode_select = ui.select(
                label="Scan mode",
                options=SCAN_MODE_OPTIONS,
            )
        self._scan_cycles_count_label = ui.label("Cycles completed: —").classes("text-caption")
        with ui.row().classes("q-gutter-sm q-mt-sm"):
            ui.button("Apply scan params", on_click=self._on_apply_scan_params)
            ui.button("Start scan", icon="play_arrow", color="positive", on_click=self._on_start_scan)
            ui.button("Abort scan", icon="stop", color="negative", on_click=self._on_abort_scan)

    def _build_telemetry(self) -> None:
        _section_title("Telemetry")
        with ui.column().classes("laser-telemetry text-body2"):
            self._temp_diode_label = ui.label("Diode temperature: —")
            self._temp_env_label = ui.label("Environment temperature: —")
            self._temp_reg_label = ui.label("Temperature regulated: —")
            self._hours_label = ui.label("Operating hours: —")

    def _build_status(self) -> None:
        _section_title("Status log")
        self._status_area = ui.textarea(value="").props("readonly outlined autogrow").classes(
            "laser-status-log w-full"
        )
        self._status_area.style("min-height: 6rem; max-height: 12rem")

    # --- Discovery / connection ---

    async def _scan_on_load(self) -> None:
        await self._run_scan()

    async def _on_refresh(self) -> None:
        await self._run_scan()

    async def _run_scan(self) -> None:
        self._refresh_btn.disable()
        self._discovery_hint.set_text("Scanning USB ports…")
        try:
            self._devices = await run.io_bound(self._discovery.scan)
        except Exception as exc:
            self._devices = []
            self._log(StatusMessage.failure(f"Scan failed: {exc}"), "scan")
        finally:
            self._refresh_btn.enable()
        options = {d.port: d.list_label for d in self._devices}
        self._device_select.set_options(options)
        if options:
            first = next(iter(options))
            self._device_select.set_value(first)
            self._discovery_hint.set_text(f"Found {len(options)} laser(s).")
        else:
            self._device_select.set_value(None)
            self._discovery_hint.set_text(
                "No supported lasers found. Check USB cable and supported_models.json."
            )

    async def _on_connect(self) -> None:
        port = self._device_select.value
        if not port:
            self._log(StatusMessage.failure("Select a laser first."), "connect")
            return
        device = next((d for d in self._devices if d.port == port), None)
        if device is None:
            self._log(StatusMessage.failure("Selected port not in scan results."), "connect")
            return
        self._set_discovery_enabled(False)
        self._log(StatusMessage.success(f"Connecting to {port}…"), "connect")
        try:
            self._controller = create_laser_controller(device)
            await run.io_bound(self._controller.connect, port)
        except ValueError as exc:
            self._log(StatusMessage.failure(str(exc)), "connect")
            self._controller = None
            self._set_discovery_enabled(True)
            return
        except Exception as exc:
            self._log(StatusMessage.failure(f"Connect failed: {exc}"), "connect")
            self._controller = None
            self._set_discovery_enabled(True)
            return
        self._controls_card.set_visibility(True)
        self._disconnect_btn.set_visibility(True)
        self._switch_handlers_enabled = False
        self._apply_specs_to_ui()
        self._start_telemetry_timer()
        ui.timer(0.1, lambda: self._enable_switch_handlers(), once=True)
        self._log(StatusMessage.success(f"Connected to {port}."), "connect")

    def _enable_switch_handlers(self) -> None:
        self._switch_handlers_enabled = True

    async def _on_disconnect(self) -> None:
        self._switch_handlers_enabled = False
        self._stop_telemetry_timer()
        if self._controller is not None:
            await run.io_bound(self._controller.disconnect)
        self._controller = None
        self._controls_card.set_visibility(False)
        self._disconnect_btn.set_visibility(False)
        self._set_discovery_enabled(True)
        self._log(StatusMessage.success("Disconnected."), "disconnect")

    def _set_discovery_enabled(self, enabled: bool) -> None:
        self._device_select.set_enabled(enabled)
        self._refresh_btn.set_enabled(enabled)
        self._connect_btn.set_enabled(enabled)

    def _is_connected(self) -> bool:
        return self._controller is not None and self._controller.is_connected

    # --- Specs → UI ---

    def _apply_specs_to_ui(self) -> None:
        specs = self._controller.specs
        bindings = bindings_from_specs(specs)
        self._updating_controls = True
        try:
            identity = specs.identity
            if identity is not None:
                self._identity_label.set_text(
                    f"{identity.manufacturer} {identity.model}  ·  "
                    f"S/N {identity.customer_serial}  ·  FW {identity.firmware_version}  ·  "
                    f"{self._controller.laser.port}"
                )
            else:
                self._identity_label.set_text(f"Port {self._controller.laser.port}")

            if specs.loop_mode is not None:
                self._loop_mode_label.set_text(
                    f"Loop mode: {LOOP_MODE_LABELS.get(int(specs.loop_mode), specs.loop_mode)}"
                )

            _bind_numeric(self._power_input, bindings.power)
            self._power_unit_select.set_enabled(bindings.power_unit.enabled)
            if bindings.power_unit.value is not None:
                self._power_unit_select.set_value(bindings.power_unit.value)

            _bind_numeric(self._current_input, bindings.current)
            _bind_numeric(self._tune_input, bindings.tune)
            self._tuning_domain_select.set_enabled(bindings.tuning_domain.enabled)
            if bindings.tuning_domain.value is not None:
                self._tuning_domain_select.set_value(bindings.tuning_domain.value)

            self._modulation_select.set_enabled(bindings.modulation.enabled)
            if bindings.modulation.value is not None:
                self._modulation_select.set_value(bindings.modulation.value)

            _bind_numeric(self._scan_start_input, bindings.scan_start)
            _bind_numeric(self._scan_stop_input, bindings.scan_stop)
            _bind_numeric(self._scan_speed_input, bindings.scan_speed)
            _bind_numeric(self._scan_cycles_input, bindings.scan_cycles)
            _bind_numeric(self._scan_dwell_input, bindings.scan_dwell_ms)
            _bind_numeric(self._scan_step_input, bindings.scan_step)
            self._scan_mode_select.set_enabled(bindings.scan_mode.enabled)
            if bindings.scan_mode.value is not None:
                self._scan_mode_select.set_value(bindings.scan_mode.value)

            self._laser_switch.set_value(bindings.laser_output)
            self._interlock_switch.set_value(bindings.software_interlock_inhibit)

            if specs.interlock_state is not None:
                label = INTERLOCK_LABELS.get(
                    int(specs.interlock_state),
                    str(specs.interlock_state),
                )
                self._interlock_state_label.set_text(f"Interlock: {label}")

            self._update_telemetry_labels(specs)
        finally:
            self._updating_controls = False

    def _update_telemetry_labels(self, specs) -> None:
        if specs.laser_diode_temperature is not None:
            self._temp_diode_label.set_text(
                f"Diode temperature: {specs.laser_diode_temperature:.2f} °C"
            )
        if specs.environment_temperature is not None:
            self._temp_env_label.set_text(
                f"Environment temperature: {specs.environment_temperature:.2f} °C"
            )
        if specs.temperature_regulated is not None:
            self._temp_reg_label.set_text(
                f"Temperature regulated: {'yes' if specs.temperature_regulated else 'no'}"
            )
        if specs.operating_hours is not None:
            self._hours_label.set_text(f"Operating hours: {specs.operating_hours:.1f} h")
        if specs.scan_cycles_count is not None:
            self._scan_cycles_count_label.set_text(
                f"Cycles completed: {specs.scan_cycles_count}"
            )

    def _update_telemetry_snapshot(self, snap: TelemetrySnapshot) -> None:
        if snap.laser_diode_temperature is not None:
            self._temp_diode_label.set_text(
                f"Diode temperature: {snap.laser_diode_temperature:.2f} °C"
            )
        if snap.environment_temperature is not None:
            self._temp_env_label.set_text(
                f"Environment temperature: {snap.environment_temperature:.2f} °C"
            )
        if snap.temperature_regulated is not None:
            self._temp_reg_label.set_text(
                f"Temperature regulated: {'yes' if snap.temperature_regulated else 'no'}"
            )
        if snap.operating_hours is not None:
            self._hours_label.set_text(f"Operating hours: {snap.operating_hours:.1f} h")
        if snap.scan_cycles_count is not None:
            self._scan_cycles_count_label.set_text(
                f"Cycles completed: {snap.scan_cycles_count}"
            )
        if snap.interlock_state is not None:
            label = INTERLOCK_LABELS.get(snap.interlock_state, str(snap.interlock_state))
            self._interlock_state_label.set_text(f"Interlock: {label}")
        if snap.laser_output is not None and not self._updating_controls:
            self._laser_switch.set_value(bool(snap.laser_output))

    def _start_telemetry_timer(self) -> None:
        self._stop_telemetry_timer()
        self._telemetry_timer = ui.timer(5.0, self._poll_telemetry)

    def _stop_telemetry_timer(self) -> None:
        if self._telemetry_timer is not None:
            self._telemetry_timer.deactivate()
            self._telemetry_timer = None

    async def _poll_telemetry(self) -> None:
        if not self._is_connected():
            return
        if self._telemetry_running:
            return
        self._telemetry_running = True
        try:
            snap = await run.io_bound(self._controller.refresh_telemetry)
            self._update_telemetry_snapshot(snap)
        except Exception as exc:
            self._log(StatusMessage.failure(f"Telemetry refresh failed: {exc}"), "telemetry")
        finally:
            self._telemetry_running = False

    # --- Command handlers ---

    async def _on_laser_output(self, event) -> None:
        if (
            self._updating_controls
            or not self._switch_handlers_enabled
            or self._serial_handler_busy
            or not self._is_connected()
        ):
            return
        self._serial_handler_busy = True
        try:
            enabled = bool(event.value)
            status = await run.io_bound(self._controller.apply_laser_output, enabled)
            self._log(status, "laser output")
            snap = await run.io_bound(self._controller.refresh_telemetry)
            self._updating_controls = True
            try:
                self._update_telemetry_snapshot(snap)
            finally:
                self._updating_controls = False
        finally:
            self._serial_handler_busy = False

    async def _on_interlock(self, event) -> None:
        if (
            self._updating_controls
            or not self._switch_handlers_enabled
            or self._serial_handler_busy
            or not self._is_connected()
        ):
            return
        self._serial_handler_busy = True
        try:
            inhibit = bool(event.value)
            status = await run.io_bound(
                self._controller.apply_software_interlock_inhibit,
                inhibit,
            )
            self._log(status, "software interlock")
            snap = await run.io_bound(self._controller.refresh_telemetry)
            self._updating_controls = True
            try:
                self._update_telemetry_snapshot(snap)
            finally:
                self._updating_controls = False
        finally:
            self._serial_handler_busy = False

    async def _on_apply_regulation(self) -> None:
        if not self._is_connected():
            return
        bindings = self._controller.bindings
        if bindings.power.enabled:
            value = _numeric_value(self._power_input)
            if value is None:
                self._log(StatusMessage.failure("Power setpoint is empty."), "regulation")
                return
            status = await run.io_bound(self._controller.apply_power, value)
            self._log(status, "power")
            if bindings.power_unit.enabled and self._power_unit_select.value is not None:
                unit = PowerUnit(int(self._power_unit_select.value))
                status_u = await run.io_bound(self._controller.apply_power_unit, unit)
                self._log(status_u, "power unit")
        elif bindings.current.enabled:
            value = _numeric_value(self._current_input)
            if value is None:
                self._log(StatusMessage.failure("Current setpoint is empty."), "regulation")
                return
            status = await run.io_bound(self._controller.apply_current, value)
            self._log(status, "current")
        else:
            self._log(StatusMessage.failure("No regulation control available."), "regulation")
            return
        self._apply_specs_to_ui()

    async def _on_apply_tuning(self) -> None:
        if not self._is_connected():
            return
        bindings = self._controller.bindings
        tune_value: Optional[float] = None
        if bindings.tune.enabled:
            tune_value = _numeric_value(self._tune_input)
            if tune_value is None:
                self._log(StatusMessage.failure("Tune setpoint is empty."), "tuning")
                return

        domain: Optional[TuningDomain] = None
        if self._tuning_domain_select.value is not None:
            domain = TuningDomain(int(self._tuning_domain_select.value))

        modulation: Optional[ModulationSource] = None
        if bindings.modulation.enabled and self._modulation_select.value is not None:
            modulation = ModulationSource(int(self._modulation_select.value))

        if domain is None and tune_value is None and modulation is None:
            self._log(StatusMessage.failure("No tuning parameters to apply."), "tuning")
            return

        self._serial_handler_busy = True
        self._log(StatusMessage.success("Applying tuning…"), "tuning")
        try:
            status = await run.io_bound(
                lambda: self._controller.apply_tuning(
                    domain=domain,
                    tune_nm=tune_value,
                    modulation=modulation,
                    wait_tune=True,
                )
            )
            self._log(status, "tuning")
            if status.ok:
                self._switch_handlers_enabled = False
                self._apply_specs_to_ui()
                ui.timer(0.1, lambda: self._enable_switch_handlers(), once=True)
        finally:
            self._serial_handler_busy = False

    async def _on_apply_scan_params(self) -> None:
        if not self._is_connected():
            return
        b = self._controller.bindings
        start = _numeric_value(self._scan_start_input) if b.scan_start.enabled else None
        stop = _numeric_value(self._scan_stop_input) if b.scan_stop.enabled else None
        if start is not None and stop is not None and start > stop:
            self._log(
                StatusMessage.failure(f"Scan start ({start}) must be ≤ scan stop ({stop})."),
                "scan params",
            )
            return
        mode = (
            ScanMode(int(self._scan_mode_select.value))
            if b.scan_mode.enabled and self._scan_mode_select.value is not None
            else None
        )
        cycles_raw = _numeric_value(self._scan_cycles_input)
        cycles_val = int(cycles_raw) if cycles_raw is not None else None
        self._serial_handler_busy = True
        try:
            status = await run.io_bound(
                lambda: self._controller.apply_scan_params(
                    start=start,
                    stop=stop,
                    speed=_numeric_value(self._scan_speed_input) if b.scan_speed.enabled else None,
                    cycles=cycles_val if b.scan_cycles.enabled else None,
                    dwell_ms=_numeric_value(self._scan_dwell_input) if b.scan_dwell_ms.enabled else None,
                    step=_numeric_value(self._scan_step_input) if b.scan_step.enabled else None,
                    mode=mode,
                )
            )
            self._log(status, "scan params")
            if status.ok:
                self._apply_specs_to_ui()
        finally:
            self._serial_handler_busy = False

    async def _on_start_scan(self) -> None:
        if not self._is_connected():
            return
        status = await run.io_bound(self._controller.start_scan)
        self._log(status, "start scan")
        self._apply_specs_to_ui()

    async def _on_abort_scan(self) -> None:
        if not self._is_connected():
            return
        status = await run.io_bound(self._controller.abort_scan)
        self._log(status, "abort scan")
        self._apply_specs_to_ui()

    def shutdown(self) -> None:
        """Release serial port on app exit (Ctrl+C / window close)."""
        self._stop_telemetry_timer()
        controller = self._controller
        if controller is not None and controller.is_connected:
            try:
                controller.disconnect()
            except Exception:
                pass

    def _log(self, status: Optional[StatusMessage], action: str) -> None:
        if status is None:
            status = StatusMessage.failure("No response from device (internal error).")
        stamp = datetime.now().strftime("%H:%M:%S")
        prefix = "OK" if status.ok else "ERR"
        line = f"[{stamp}] {prefix} {action}: {status.summary}"
        if status.command:
            line += f" ({status.command})"
        self._status_lines.append(line)
        if len(self._status_lines) > 80:
            self._status_lines = self._status_lines[-80:]
        self._status_area.set_value("\n".join(self._status_lines))


def create_laser_widget(*, parent: Optional[ui.element] = None) -> LaserControlWidget:
    """Build the laser widget inside ``parent`` or a new top-level column."""
    apply_laser_theme()
    return LaserControlWidget(parent=parent)
