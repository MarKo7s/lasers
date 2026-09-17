"""NiceGUI laser control widget (embeddable)."""

from __future__ import annotations

from datetime import datetime
from typing import Awaitable, Callable, Optional

from nicegui import run, ui

from laser.core.discovery_service import DiscoveryService
from laser.core.factory import create_laser_controller
from laser.core.models import DiscoveredDevice, StatusMessage
from laser.core.tlb8800 import (
    INTERLOCK_LABELS,
    LOOP_MODE_LABELS,
    MODULATION_OPTIONS,
    POWER_UNIT_OPTIONS,
    SCAN_MODE_OPTIONS,
    TRIGGER_POLARITY_OPTIONS,
    TUNING_DOMAIN_OPTIONS,
    ControlBindings,
    NumericBinding,
    TelemetrySnapshot,
    TLB8800Controller,
    bindings_from_specs,
    identity_display,
    is_frequency_domain,
    numeric_field_label,
    scan_bound_label,
    scan_speed_label,
    scan_step_label,
    tune_click_step,
    tune_setpoint_label,
)
from laser.newfocus.tlb8800_utilities.types import (
    ModulationSource,
    PowerUnit,
    ScanMode,
    TriggerPolarity,
    TuningDomain,
)
from laser.ui.nicegui.theme import apply_laser_theme, laser_header


def _clamp_float(value: float, minimum: Optional[float], maximum: Optional[float]) -> float:
    if minimum is not None and value < minimum:
        value = float(minimum)
    if maximum is not None and value > maximum:
        value = float(maximum)
    return value


def _notify_nudge(field) -> None:
    callback = getattr(field, "_laser_on_nudge", None)
    if callable(callback):
        callback()


def _format_float_text(value: float, *, as_integer: bool = False) -> str:
    if as_integer:
        return str(int(round(float(value))))
    text = f"{float(value):.6f}".rstrip("0").rstrip(".")
    return text or "0"


def _parse_float_text(raw: object) -> Optional[float]:
    if raw is None or raw == "":
        return None
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _attach_text_float_clickers(field: ui.input, *, click_step: float = 1.0) -> ui.input:
    """Same arrows on every numeric cell: type any float; buttons/keys change by click_step."""
    field._laser_click_step = click_step  # type: ignore[attr-defined]
    field.classes("laser-float-number")

    def _step(sign: int) -> None:
        current = _parse_float_text(field.value) or 0.0
        delta = sign * float(getattr(field, "_laser_click_step", 1.0))
        new = _clamp_float(
            current + delta,
            getattr(field, "_laser_min", None),
            getattr(field, "_laser_max", None),
        )
        as_integer = bool(getattr(field, "_laser_integer", False))
        if as_integer:
            new = float(int(round(new)))
        field.set_value(_format_float_text(new, as_integer=as_integer))
        _notify_nudge(field)

    field.on("keydown.up.prevent", lambda _e: _step(1))
    field.on("keydown.down.prevent", lambda _e: _step(-1))
    with field.add_slot("append"):
        with ui.column().classes("laser-step-btns q-gutter-none"):
            ui.button(icon="arrow_drop_up", on_click=lambda: _step(1)).props(
                "flat dense round size=xs"
            )
            ui.button(icon="arrow_drop_down", on_click=lambda: _step(-1)).props(
                "flat dense round size=xs"
            )
    return field


def _make_numeric_field(label: str, *, click_step: float = 1.0) -> ui.input:
    return _attach_text_float_clickers(
        ui.input(label).props("outlined stack-label").classes("w-full"),
        click_step=click_step,
    )


def _bind_text_float(
    field: ui.input,
    binding: NumericBinding,
    *,
    label: str,
    click_step: float,
    sync_value: bool = True,
    as_integer: bool = False,
) -> None:
    field.set_enabled(binding.enabled)
    field.set_label(numeric_field_label(label, binding, as_integer=as_integer))
    field._laser_click_step = click_step  # type: ignore[attr-defined]
    field._laser_min = binding.minimum  # type: ignore[attr-defined]
    field._laser_max = binding.maximum  # type: ignore[attr-defined]
    field._laser_integer = as_integer  # type: ignore[attr-defined]
    if not sync_value:
        return
    if binding.value is not None:
        field.set_value(_format_float_text(binding.value, as_integer=as_integer))
    elif not binding.enabled:
        field.set_value("")


def _integer_value(field: ui.input) -> Optional[int]:
    raw = _numeric_value(field)
    if raw is None:
        return None
    return int(round(raw))


def _numeric_value(field: ui.input) -> Optional[float]:
    raw = field.value
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


async def _read_float_from_dom(field: ui.input) -> Optional[float]:
    """Read the live <input> text so a commit does not use a stale value."""
    try:
        raw = await ui.run_javascript(
            f"""
            const el = getHtmlElement({field.id});
            if (!el) return null;
            const input = el.querySelector("input");
            return (input ?? el).value ?? null;
            """
        )
    except Exception:
        raw = None
    if raw is None:
        return _numeric_value(field)
    if str(raw).strip() == "":
        return None
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return _numeric_value(field)


def _section_title(text: str) -> ui.label:
    return ui.label(text).classes("laser-section-title q-mt-md q-mb-xs")


class LaserControlWidget:
    """Full laser control panel for NiceGUI applications."""

    _NUMERIC_COMMITS = (
        # key, log action, field, binding, apply, spec readback, integer?
        ("power", "power", "_power_input", "power", "apply_power", "power", False),
        ("current", "current", "_current_input", "current", "apply_current", "current", False),
        ("tune", "tune", "_tune_input", "tune", "apply_tune", "tune_setpoint", False),
        ("scan_start", "scan start", "_scan_start_input", "scan_start", "apply_scan_start", "scan_start", False),
        ("scan_stop", "scan stop", "_scan_stop_input", "scan_stop", "apply_scan_stop", "scan_stop", False),
        ("scan_speed", "scan speed", "_scan_speed_input", "scan_speed", "apply_scan_speed", "scan_speed", True),
        ("scan_cycles", "scan cycles", "_scan_cycles_input", "scan_cycles", "apply_scan_cycles", "scan_cycles", True),
        ("scan_dwell", "scan dwell", "_scan_dwell_input", "scan_dwell_ms", "apply_scan_dwell", "scan_dwell_time_ms", False),
        ("scan_step", "scan step", "_scan_step_input", "scan_step", "apply_scan_step", "scan_step_size", False),
    )

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
        self._commit_timers: dict[str, ui.timer] = {}
        self._pending_commits: dict[str, Callable[[], Awaitable[None]]] = {}

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
            self._check_errors_btn = ui.button(
                "Check errors",
                icon="bug_report",
                on_click=self._on_check_errors,
            ).props("outline")
        self._interlock_state_label = ui.label("Interlock: —").classes("text-caption text-grey-5")

    def _build_regulation(self) -> None:
        _section_title("Regulation")
        self._loop_mode_label = ui.label("Loop mode: —").classes("text-caption q-mb-sm")
        with ui.grid(columns=2).classes("w-full q-gutter-sm laser-regulation"):
            self._power_input = _make_numeric_field("Power setpoint", click_step=0.01)
            self._power_unit_select = (
                ui.select(
                    label="Power unit",
                    options=POWER_UNIT_OPTIONS,
                )
                .props("outlined stack-label")
                .classes("w-full")
            )
            self._current_input = _make_numeric_field("Current (mA)", click_step=0.1)

    def _build_tuning(self) -> None:
        self._tuning_section_title = _section_title("Tuning")
        self._tuning_domain_toggle = (
            ui.toggle(
                TUNING_DOMAIN_OPTIONS,
                value=int(TuningDomain.WAVELENGTH),
                on_change=self._on_tuning_domain_change,
            )
            .props("spread toggle-color=primary no-caps")
            .classes("w-full")
        )
        with ui.grid(columns=2).classes("w-full q-gutter-sm laser-tuning"):
            self._tune_input = _make_numeric_field("Tune setpoint")
            self._modulation_select = (
                ui.select(
                    label="Modulation",
                    options=MODULATION_OPTIONS,
                )
                .props("outlined stack-label")
                .classes("w-full")
            )
            with ui.row().classes("w-full items-center"):
                ui.button(
                    "Set center wavelength",
                    icon="vertical_align_center",
                    on_click=self._on_set_center_wavelength,
                )

    def _build_scan(self) -> None:
        _section_title("Scan / sweep")
        field_props = "outlined stack-label"
        with ui.grid(columns=2).classes("w-full q-gutter-sm laser-regulation"):
            self._scan_start_input = _make_numeric_field("Scan start")
            self._scan_stop_input = _make_numeric_field("Scan stop")
            self._scan_speed_input = _make_numeric_field("Scan speed")
            self._scan_cycles_input = _make_numeric_field("Scan cycles (-1 = ∞)")
            self._scan_dwell_input = _make_numeric_field("Dwell (ms)")
            self._scan_step_input = _make_numeric_field("Step size")
            self._scan_mode_select = (
                ui.select(label="Scan mode", options=SCAN_MODE_OPTIONS)
                .props(field_props)
                .classes("w-full")
            )
            self._trigger_polarity_select = (
                ui.select(label="Trigger polarity", options=TRIGGER_POLARITY_OPTIONS)
                .props(field_props)
                .classes("w-full")
            )
        self._wire_live_commits()
        self._scan_cycles_count_label = ui.label("Cycles completed: —").classes("text-caption")
        with ui.row().classes("q-gutter-sm q-mt-sm"):
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

    def _wire_live_commits(self) -> None:
        for key, _action, attr, *_rest in self._NUMERIC_COMMITS:
            self._wire_live_numeric(getattr(self, attr), key)
        self._power_unit_select.on_value_change(self._on_power_unit_change)
        self._modulation_select.on_value_change(self._on_modulation_change)
        self._scan_mode_select.on_value_change(self._on_scan_mode_change)
        self._trigger_polarity_select.on_value_change(self._on_trigger_polarity_change)

    def _wire_live_numeric(self, field, key: str) -> None:
        def _kick(_e=None) -> None:
            self._schedule_commit(key)

        field.on("blur", _kick)
        field.on("keydown.enter", _kick)
        field._laser_on_nudge = _kick  # type: ignore[attr-defined]

    def _schedule_commit(self, key: str) -> None:
        old = self._commit_timers.pop(key, None)
        if old is not None:
            old.deactivate()

        async def _run() -> None:
            self._commit_timers.pop(key, None)
            await self._run_commit(key)

        self._commit_timers[key] = ui.timer(0.25, _run, once=True)

    async def _run_commit(self, key: str) -> None:
        if (
            self._updating_controls
            or not self._switch_handlers_enabled
            or not self._is_connected()
        ):
            return
        if self._serial_handler_busy:
            self._pending_commits[key] = lambda k=key: self._commit_named(k)
            return
        await self._commit_named(key)
        await self._drain_pending_commits()

    async def _drain_pending_commits(self) -> None:
        while self._pending_commits and not self._serial_handler_busy:
            if not self._is_connected():
                self._pending_commits.clear()
                return
            _key, fn = next(iter(self._pending_commits.items()))
            self._pending_commits.pop(_key)
            await fn()

    async def _commit_numeric(
        self,
        *,
        action: str,
        field,
        binding: NumericBinding,
        apply,
        readback,
        as_integer: bool = False,
    ) -> bool:
        raw = await _read_float_from_dom(field)
        if raw is None:
            return False
        value = _clamp_float(raw, binding.minimum, binding.maximum)
        sent: int | float = int(round(value)) if as_integer else value
        self._serial_handler_busy = True
        try:
            status = await run.io_bound(apply, sent)
            self._log(status, action)
            if not status.ok:
                return False
            latest = readback()
            self._updating_controls = True
            try:
                if latest is not None:
                    field.set_value(
                        _format_float_text(float(latest), as_integer=as_integer)
                    )
            finally:
                self._updating_controls = False
            return True
        finally:
            self._serial_handler_busy = False

    async def _commit_named(self, key: str) -> None:
        if not self._is_connected():
            return
        controller = self._controller
        for item_key, action, attr, binding_attr, apply_name, spec_attr, as_integer in self._NUMERIC_COMMITS:
            if item_key == key:
                break
        else:
            return
        apply = getattr(controller, apply_name)
        if apply_name == "apply_tune":
            apply = lambda v: controller.apply_tune(v, wait=True)
        elif apply_name == "apply_scan_cycles":
            apply = lambda v: controller.apply_scan_cycles(int(v))
        wrote = await self._commit_numeric(
            action=action,
            field=getattr(self, attr),
            binding=getattr(controller.bindings, binding_attr),
            apply=apply,
            readback=lambda: getattr(controller.specs, spec_attr),
            as_integer=as_integer,
        )
        if wrote and key in {"power", "current"}:
            self._updating_controls = True
            try:
                self._sync_regulation_from_specs()
            finally:
                self._updating_controls = False

    def _sync_regulation_from_specs(self) -> None:
        specs = self._controller.specs
        bindings = bindings_from_specs(specs)
        if specs.loop_mode is not None:
            self._loop_mode_label.set_text(
                f"Loop mode: {LOOP_MODE_LABELS.get(int(specs.loop_mode), specs.loop_mode)}"
            )
        _bind_text_float(
            self._power_input,
            bindings.power,
            label="Power setpoint",
            click_step=0.01,
        )
        self._power_unit_select.set_enabled(bindings.power_unit.enabled)
        if bindings.power_unit.value is not None:
            self._power_unit_select.set_value(bindings.power_unit.value)
        _bind_text_float(
            self._current_input,
            bindings.current,
            label="Current (mA)",
            click_step=0.1,
        )

    def _tuning_domain_from_ui(self) -> TuningDomain:
        raw = self._tuning_domain_toggle.value
        if raw is not None:
            return TuningDomain(int(raw))
        if self._is_connected() and self._controller.specs.tuning_domain is not None:
            return self._controller.specs.tuning_domain
        return TuningDomain.WAVELENGTH

    def _sync_tuning_domain_labels(self, domain: TuningDomain) -> None:
        title = "Frequency tuning" if is_frequency_domain(domain) else "Wavelength tuning"
        self._tuning_section_title.set_text(title)

    def _bind_tuning_and_scan_labels(
        self,
        bindings: ControlBindings,
        domain: TuningDomain,
    ) -> None:
        self._sync_tuning_domain_labels(domain)
        click = tune_click_step(domain)
        _bind_text_float(
            self._tune_input,
            bindings.tune,
            label=tune_setpoint_label(domain),
            click_step=click,
        )
        _bind_text_float(
            self._scan_start_input,
            bindings.scan_start,
            label=scan_bound_label("Scan start", domain),
            click_step=click,
        )
        _bind_text_float(
            self._scan_stop_input,
            bindings.scan_stop,
            label=scan_bound_label("Scan stop", domain),
            click_step=click,
        )
        _bind_text_float(
            self._scan_speed_input,
            bindings.scan_speed,
            label=scan_speed_label(domain),
            click_step=1.0,
            as_integer=True,
        )
        _bind_text_float(
            self._scan_step_input,
            bindings.scan_step,
            label=scan_step_label(domain),
            click_step=click,
        )
        _bind_text_float(
            self._scan_dwell_input,
            bindings.scan_dwell_ms,
            label="Dwell (ms)",
            click_step=1.0,
        )
        _bind_text_float(
            self._scan_cycles_input,
            bindings.scan_cycles,
            label="Scan cycles (-1 = ∞)",
            click_step=1.0,
            as_integer=True,
        )

    def _update_scan_cycles_label(self, specs) -> None:
        if specs.scan_cycles_count is not None:
            self._scan_cycles_count_label.set_text(
                f"Cycles completed: {specs.scan_cycles_count}"
            )

    def _sync_scan_fields_from_specs(self) -> None:
        """Refresh scan/sweep controls from cached specs."""
        specs = self._controller.specs
        bindings = bindings_from_specs(specs)
        domain = (
            specs.tuning_domain
            if specs.tuning_domain is not None
            else self._tuning_domain_from_ui()
        )
        self._updating_controls = True
        try:
            self._bind_tuning_and_scan_labels(bindings, domain)
            self._scan_mode_select.set_enabled(bindings.scan_mode.enabled)
            if bindings.scan_mode.value is not None:
                self._scan_mode_select.set_value(bindings.scan_mode.value)
            self._trigger_polarity_select.set_enabled(bindings.trigger_polarity.enabled)
            if bindings.trigger_polarity.value is not None:
                self._trigger_polarity_select.set_value(bindings.trigger_polarity.value)
            self._update_scan_cycles_label(specs)
        finally:
            self._updating_controls = False

    async def _collect_scan_params_from_ui(
        self,
    ) -> tuple[Optional[StatusMessage], dict[str, object]]:
        b = self._controller.bindings
        start = await _read_float_from_dom(self._scan_start_input) if b.scan_start.enabled else None
        stop = await _read_float_from_dom(self._scan_stop_input) if b.scan_stop.enabled else None
        if start is not None and stop is not None and start > stop:
            return (
                StatusMessage.failure(
                    f"Scan start ({start}) must be ≤ scan stop ({stop})."
                ),
                {},
            )
        mode = (
            ScanMode(int(self._scan_mode_select.value))
            if b.scan_mode.enabled and self._scan_mode_select.value is not None
            else None
        )
        trigger_polarity = (
            TriggerPolarity(int(self._trigger_polarity_select.value))
            if b.trigger_polarity.enabled and self._trigger_polarity_select.value is not None
            else None
        )
        cycles_raw = _numeric_value(self._scan_cycles_input)
        cycles_val = int(cycles_raw) if cycles_raw is not None else None
        step = (
            await _read_float_from_dom(self._scan_step_input)
            if b.scan_step.enabled
            else None
        )
        return None, {
            "start": start,
            "stop": stop,
            "speed": _integer_value(self._scan_speed_input) if b.scan_speed.enabled else None,
            "cycles": cycles_val if b.scan_cycles.enabled else None,
            "dwell_ms": (
                await _read_float_from_dom(self._scan_dwell_input)
                if b.scan_dwell_ms.enabled
                else None
            ),
            "step": step,
            "mode": mode,
            "trigger_polarity": trigger_polarity,
        }

    # --- Specs → UI ---

    def _apply_specs_to_ui(self) -> None:
        specs = self._controller.specs
        bindings = bindings_from_specs(specs)
        domain = (
            specs.tuning_domain
            if specs.tuning_domain is not None
            else TuningDomain.WAVELENGTH
        )
        self._updating_controls = True
        try:
            identity = specs.identity
            self._identity_label.set_text(
                identity_display(identity, self._controller.laser.port)
            )
            self._sync_regulation_from_specs()
            self._tuning_domain_toggle.set_enabled(bindings.tuning_domain.enabled)
            if bindings.tuning_domain.value is not None:
                self._tuning_domain_toggle.set_value(bindings.tuning_domain.value)

            self._bind_tuning_and_scan_labels(bindings, domain)

            self._modulation_select.set_enabled(bindings.modulation.enabled)
            if bindings.modulation.value is not None:
                self._modulation_select.set_value(bindings.modulation.value)
            self._scan_mode_select.set_enabled(bindings.scan_mode.enabled)
            if bindings.scan_mode.value is not None:
                self._scan_mode_select.set_value(bindings.scan_mode.value)
            self._trigger_polarity_select.set_enabled(bindings.trigger_polarity.enabled)
            if bindings.trigger_polarity.value is not None:
                self._trigger_polarity_select.set_value(bindings.trigger_polarity.value)
            self._update_scan_cycles_label(specs)

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
            self._update_scan_cycles_label(specs)

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

    async def _on_check_errors(self) -> None:
        if self._serial_handler_busy or not self._is_connected():
            return
        self._serial_handler_busy = True
        try:
            status = await run.io_bound(self._controller.check_errors)
            self._log(status, "errors")
        finally:
            self._serial_handler_busy = False

    async def _commit_enum(
        self,
        event,
        *,
        action: str,
        enum_cls,
        spec_attr: str,
        apply_name: str,
        select,
        default: int | None = None,
    ) -> None:
        if (
            self._updating_controls
            or not self._switch_handlers_enabled
            or self._serial_handler_busy
            or not self._is_connected()
            or event.value is None
        ):
            return
        value = enum_cls(int(event.value))
        current = getattr(self._controller.specs, spec_attr)
        previous = int(current) if current is not None else default
        if previous is not None and int(value) == previous:
            return
        self._serial_handler_busy = True
        try:
            status = await run.io_bound(getattr(self._controller, apply_name), value)
            self._log(status, action)
            self._updating_controls = True
            try:
                latest = getattr(self._controller.specs, spec_attr)
                if latest is not None:
                    select.set_value(int(latest))
                elif previous is not None:
                    select.set_value(previous)
            finally:
                self._updating_controls = False
        finally:
            self._serial_handler_busy = False
        await self._drain_pending_commits()

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

    async def _on_power_unit_change(self, event) -> None:
        await self._commit_enum(
            event,
            action="power unit",
            enum_cls=PowerUnit,
            spec_attr="power_unit",
            apply_name="apply_power_unit",
            select=self._power_unit_select,
        )

    async def _on_tuning_domain_change(self, event) -> None:
        if (
            self._updating_controls
            or not self._switch_handlers_enabled
            or self._serial_handler_busy
            or not self._is_connected()
        ):
            return
        domain = TuningDomain(int(event.value))
        previous = (
            int(self._controller.specs.tuning_domain)
            if self._controller.specs.tuning_domain is not None
            else int(TuningDomain.WAVELENGTH)
        )
        if int(domain) == previous:
            return

        self._serial_handler_busy = True
        try:
            status = await run.io_bound(self._controller.apply_tuning_domain, domain)
            self._log(status, "tuning domain")
            if status.ok:
                self._apply_specs_to_ui()
            else:
                self._updating_controls = True
                try:
                    self._tuning_domain_toggle.set_value(previous)
                finally:
                    self._updating_controls = False
        finally:
            self._serial_handler_busy = False

    async def _on_set_center_wavelength(self) -> None:
        if not self._is_connected():
            return
        specs = self._controller.specs
        if specs.wavelength_min is None or specs.wavelength_max is None:
            self._log(
                StatusMessage.failure(
                    "Wavelength range not available (wmin?/wmax? missing)."
                ),
                "center wavelength",
            )
            return

        center = (specs.wavelength_min + specs.wavelength_max) / 2.0
        self._serial_handler_busy = True
        self._log(StatusMessage.success("Setting center wavelength…"), "center wavelength")
        try:
            status = await run.io_bound(
                lambda: self._controller.apply_tune(center, wait=True)
            )
            self._log(status, "center wavelength")
            if status.ok:
                self._apply_specs_to_ui()
        finally:
            self._serial_handler_busy = False

    async def _on_modulation_change(self, event) -> None:
        await self._commit_enum(
            event,
            action="modulation",
            enum_cls=ModulationSource,
            spec_attr="modulation_source",
            apply_name="apply_modulation",
            select=self._modulation_select,
        )

    async def _on_scan_mode_change(self, event) -> None:
        await self._commit_enum(
            event,
            action="scan mode",
            enum_cls=ScanMode,
            spec_attr="scan_mode",
            apply_name="apply_scan_mode",
            select=self._scan_mode_select,
        )

    async def _on_trigger_polarity_change(self, event) -> None:
        await self._commit_enum(
            event,
            action="trigger polarity",
            enum_cls=TriggerPolarity,
            spec_attr="trigger_polarity",
            apply_name="apply_trigger_polarity",
            select=self._trigger_polarity_select,
        )

    async def _on_start_scan(self) -> None:
        if not self._is_connected():
            return
        self._serial_handler_busy = True
        try:
            error, kwargs = await self._collect_scan_params_from_ui()
            if error is not None:
                self._log(error, "start scan")
                return
            apply_status = await run.io_bound(
                lambda: self._controller.apply_scan_params(**kwargs)
            )
            if not apply_status.ok:
                self._log(apply_status, "start scan")
                return
            self._sync_scan_fields_from_specs()
            status = await run.io_bound(self._controller.start_scan)
            self._log(status, "start scan")
            if status.ok:
                self._update_scan_cycles_label(self._controller.specs)
        finally:
            self._serial_handler_busy = False

    async def _on_abort_scan(self) -> None:
        if not self._is_connected():
            return
        status = await run.io_bound(self._controller.abort_scan)
        self._log(status, "abort scan")
        if status.ok:
            self._update_scan_cycles_label(self._controller.specs)

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
