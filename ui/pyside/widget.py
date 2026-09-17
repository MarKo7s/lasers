"""PySide6 twin of the NiceGUI laser control panel.

Uses the shared `core/` controller. Serial I/O runs on a background thread.
Numeric fields and dropdowns commit live; the widget then shows instrument readback.
"""

from __future__ import annotations

import sys
from datetime import datetime
from typing import Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from laser.core.discovery_service import DiscoveryService
from laser.core.factory import create_laser_controller
from laser.core.idn_registry import display_id_from_idn
from laser.core.models import DiscoveredDevice, StatusMessage
from laser.core.tlb8800 import (
    INTERLOCK_LABELS,
    LOOP_MODE_LABELS,
    MODULATION_OPTIONS,
    POWER_UNIT_OPTIONS,
    SCAN_MODE_OPTIONS,
    TRIGGER_POLARITY_OPTIONS,
    TUNING_DOMAIN_OPTIONS,
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
from laser.core.tlb8800.models import ControlBindings
from laser.newfocus import TLB8800
from laser.newfocus.tlb8800_utilities.types import (
    ModulationSource,
    PowerUnit,
    ScanMode,
    TriggerPolarity,
    TuningDomain,
)

from laser.ui.pyside.controller_runner import ControllerRunner, Job
from laser.ui.pyside.ui_helpers import (
    apply_numeric_binding,
    apply_select_binding,
    fill_combo,
    make_click_spin,
    make_group,
    set_field_expanding,
)

# Live numeric commits: (action key, spin attribute, controller method, integer?).
_NUMERIC_COMMITS = (
    ("power", "_regulation_power_spin", "apply_power", False),
    ("current", "_regulation_current_spin", "apply_current", False),
    ("tune", "_tune_spin", "apply_tune", False),
    ("scan_start", "_scan_start_spin", "apply_scan_start", False),
    ("scan_stop", "_scan_stop_spin", "apply_scan_stop", False),
    ("scan_speed", "_scan_speed_spin", "apply_scan_speed", True),
    ("scan_cycles", "_scan_cycles_spin", "apply_scan_cycles", True),
    ("scan_dwell", "_scan_dwell_spin", "apply_scan_dwell", False),
    ("scan_step", "_scan_step_spin", "apply_scan_step", False),
)

_LIVE_NUMERIC = frozenset(key for key, _attr, _apply, _as_int in _NUMERIC_COMMITS)
_NO_SPECS_REFRESH = frozenset({"telemetry", "scan", "connect", "disconnect", "errors", "sync"})


def ensure_qapp() -> QApplication:
    """Create/reuse QApplication (works for normal Python and many notebook setups)."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


class LaserControlWidget(QWidget):
    """Full laser control widget (PySide6)."""

    _TELEMETRY_INTERVAL_MS = 5000

    def __init__(
        self,
        laser: Optional[TLB8800] = None,
        *,
        parent: Optional[QWidget] = None,
    ) -> None:
        ensure_qapp()
        super().__init__(parent)
        self._discovery = DiscoveryService()
        self._controller = None
        self._devices: list[DiscoveredDevice] = []

        self._runner = ControllerRunner()
        self._runner.finished.connect(self._on_job_finished)

        self._serial_busy = False
        self._updating_controls = False
        self._remote_control = False
        self._telemetry_running = False
        self._pending_commits: dict[str, object] = {}
        self._commit_timers: dict[str, QTimer] = {}

        self._build_ui()

        self._telemetry_timer = QTimer(self)
        self._telemetry_timer.timeout.connect(self._schedule_telemetry_refresh)
        self._telemetry_timer.setInterval(self._TELEMETRY_INTERVAL_MS)

        if laser is not None and laser.is_open:
            self._adopt_connected_laser(laser)
        else:
            self._set_controls_enabled(False)
            QTimer.singleShot(50, self._on_refresh)

    @property
    def laser(self) -> Optional[TLB8800]:
        if self._controller is None or not self._controller.is_connected:
            return None
        return self._controller.laser

    def _adopt_connected_laser(self, laser: TLB8800) -> None:
        controller = TLB8800Controller()
        # Widget Disconnect must close the port so Refresh can probe it again.
        controller.attach(laser, owns_connection=True)
        self._controller = controller
        self._set_controls_enabled(True)
        self._show_connected_device_in_menu()
        self._discovery_hint.setText(self._connected_hint())
        self._apply_specs_to_ui()
        self._telemetry_timer.start()

    def _device_from_connected_laser(self) -> Optional[DiscoveredDevice]:
        if not self._is_laser_connected():
            return None
        laser = self._controller.laser
        identity = None
        try:
            identity = laser.specs.identity
        except Exception:
            identity = None
        if identity is None:
            try:
                identity = laser.identity
            except Exception:
                identity = None
        raw = identity.raw_idn if identity is not None else ""
        model = identity.model if identity is not None else "TLB-8800"
        return DiscoveredDevice(
            port=laser.port,
            model=model,
            raw_idn=raw,
            display_id=display_id_from_idn(model, raw),
        )

    def _fill_device_combo(
        self,
        devices: list[DiscoveredDevice],
        *,
        select_port: Optional[str] = None,
    ) -> None:
        self._devices = list(devices)
        self._device_select.clear()
        selected = 0
        for i, device in enumerate(self._devices):
            self._device_select.addItem(device.list_label)
            if select_port and device.port == select_port:
                selected = i
        if self._devices:
            self._device_select.setCurrentIndex(selected)

    def _show_connected_device_in_menu(self) -> None:
        device = self._device_from_connected_laser()
        if device is None:
            return
        self._fill_device_combo([device], select_port=device.port)

    def shutdown(self) -> None:
        self._telemetry_timer.stop()
        self._runner.shutdown()

    # --- UI construction ---

    def _build_ui(self) -> None:
        root = QVBoxLayout()
        root.setSpacing(10)
        self.setLayout(root)

        discovery_row = QHBoxLayout()
        self._device_select = QComboBox()
        set_field_expanding(self._device_select)
        self._refresh_btn = QPushButton("Refresh")
        self._connect_btn = QPushButton("Connect")
        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.setEnabled(False)
        discovery_row.addWidget(QLabel("Available lasers:"))
        discovery_row.addWidget(self._device_select, 1)
        discovery_row.addWidget(self._refresh_btn)
        discovery_row.addWidget(self._connect_btn)
        discovery_row.addWidget(self._disconnect_btn)
        root.addLayout(discovery_row)
        self._discovery_hint = QLabel("Scanning USB ports…")
        root.addWidget(self._discovery_hint)

        status_box, status_layout = make_group("Laser status")
        assert isinstance(status_layout, QVBoxLayout)
        self._identity_label = QLabel("—")
        self._identity_label.setWordWrap(True)
        self._laser_output_checkbox = QCheckBox("Laser output")
        self._interlock_inhibit_checkbox = QCheckBox("Software interlock (inhibit)")
        self._check_errors_btn = QPushButton("Check errors")
        self._interlock_state_label = QLabel("Interlock: —")
        self._loop_mode_label = QLabel("Loop mode: —")
        output_row = QHBoxLayout()
        output_row.addWidget(self._laser_output_checkbox)
        output_row.addWidget(self._interlock_inhibit_checkbox)
        output_row.addWidget(self._check_errors_btn)
        output_row.addStretch(1)
        status_layout.addWidget(self._identity_label)
        status_layout.addLayout(output_row)
        status_layout.addWidget(self._interlock_state_label)
        status_layout.addWidget(self._loop_mode_label)
        root.addWidget(status_box)

        power_box, power_grid = make_group("Power / current", grid=True)
        assert isinstance(power_grid, QGridLayout)
        self._power_label = QLabel("Power setpoint")
        self._regulation_power_spin = make_click_spin(decimals=3, click_step=0.01, maximum=1e9)
        self._power_unit_combo = QComboBox()
        fill_combo(self._power_unit_combo, POWER_UNIT_OPTIONS)
        set_field_expanding(self._power_unit_combo)
        self._power_unit_combo.setMinimumWidth(90)
        self._current_label = QLabel("Current (mA)")
        self._regulation_current_spin = make_click_spin(decimals=2, click_step=0.1, maximum=1e9)
        power_grid.addWidget(self._power_label, 0, 0)
        power_grid.addWidget(self._regulation_power_spin, 0, 1)
        power_grid.addWidget(QLabel("Unit"), 0, 2)
        power_grid.addWidget(self._power_unit_combo, 0, 3)
        power_grid.addWidget(self._current_label, 1, 0)
        power_grid.addWidget(self._regulation_current_spin, 1, 1)
        power_grid.setColumnStretch(1, 1)
        power_grid.setColumnStretch(3, 1)
        root.addWidget(power_box)

        self._tuning_box, tuning_grid = make_group("Wavelength tuning", grid=True)
        assert isinstance(tuning_grid, QGridLayout)
        self._tuning_domain_combo = QComboBox()
        fill_combo(self._tuning_domain_combo, TUNING_DOMAIN_OPTIONS)
        set_field_expanding(self._tuning_domain_combo)
        self._tune_label = QLabel(tune_setpoint_label(TuningDomain.WAVELENGTH))
        self._tune_spin = make_click_spin(decimals=4, click_step=1.0, maximum=1e12, value=0.0)
        self._modulation_combo = QComboBox()
        fill_combo(self._modulation_combo, MODULATION_OPTIONS)
        set_field_expanding(self._modulation_combo)
        self._center_tune_btn = QPushButton("Set center wavelength")
        tuning_grid.addWidget(QLabel("Tuning domain"), 0, 0)
        tuning_grid.addWidget(self._tuning_domain_combo, 0, 1, 1, 3)
        tuning_grid.addWidget(self._tune_label, 1, 0)
        tuning_grid.addWidget(self._tune_spin, 1, 1, 1, 3)
        tuning_grid.addWidget(QLabel("Modulation"), 2, 0)
        tuning_grid.addWidget(self._modulation_combo, 2, 1, 1, 3)
        tuning_grid.setColumnStretch(1, 1)
        tuning_btns = QHBoxLayout()
        tuning_btns.addStretch(1)
        tuning_btns.addWidget(self._center_tune_btn)
        tuning_grid.addLayout(tuning_btns, 3, 0, 1, 4)
        root.addWidget(self._tuning_box)

        scan_box, scan_grid = make_group("Scan / sweep", grid=True)
        assert isinstance(scan_grid, QGridLayout)
        domain = TuningDomain.WAVELENGTH
        click = tune_click_step(domain)
        self._scan_start_label = QLabel(scan_bound_label("Scan start", domain))
        self._scan_start_spin = make_click_spin(decimals=4, click_step=click, maximum=1e12)
        self._scan_stop_label = QLabel(scan_bound_label("Scan stop", domain))
        self._scan_stop_spin = make_click_spin(decimals=4, click_step=click, maximum=1e12)
        self._scan_speed_label = QLabel(scan_speed_label(domain))
        self._scan_speed_spin = make_click_spin(decimals=0, click_step=1.0, maximum=1_000_000_000)
        self._scan_cycles_label = QLabel("Scan cycles (-1 = ∞)")
        self._scan_cycles_spin = make_click_spin(
            decimals=0, click_step=1.0, minimum=-1, maximum=1_000_000
        )
        self._scan_dwell_label = QLabel("Dwell (ms)")
        self._scan_dwell_spin = make_click_spin(decimals=3, click_step=1.0, maximum=1e9)
        self._scan_step_label = QLabel(scan_step_label(domain))
        self._scan_step_spin = make_click_spin(decimals=4, click_step=click, maximum=1e9)
        self._scan_mode_combo = QComboBox()
        fill_combo(self._scan_mode_combo, SCAN_MODE_OPTIONS)
        set_field_expanding(self._scan_mode_combo)
        self._trigger_polarity_combo = QComboBox()
        fill_combo(self._trigger_polarity_combo, TRIGGER_POLARITY_OPTIONS)
        set_field_expanding(self._trigger_polarity_combo)
        self._start_scan_btn = QPushButton("Start scan")
        self._abort_scan_btn = QPushButton("Abort scan")
        scan_grid.addWidget(self._scan_start_label, 0, 0)
        scan_grid.addWidget(self._scan_start_spin, 0, 1)
        scan_grid.addWidget(self._scan_stop_label, 0, 2)
        scan_grid.addWidget(self._scan_stop_spin, 0, 3)
        scan_grid.addWidget(self._scan_speed_label, 1, 0)
        scan_grid.addWidget(self._scan_speed_spin, 1, 1)
        scan_grid.addWidget(self._scan_cycles_label, 1, 2)
        scan_grid.addWidget(self._scan_cycles_spin, 1, 3)
        scan_grid.addWidget(self._scan_dwell_label, 2, 0)
        scan_grid.addWidget(self._scan_dwell_spin, 2, 1)
        scan_grid.addWidget(self._scan_step_label, 2, 2)
        scan_grid.addWidget(self._scan_step_spin, 2, 3)
        scan_grid.addWidget(QLabel("Scan mode"), 3, 0)
        scan_grid.addWidget(self._scan_mode_combo, 3, 1, 1, 3)
        scan_grid.addWidget(QLabel("Trigger polarity"), 4, 0)
        scan_grid.addWidget(self._trigger_polarity_combo, 4, 1, 1, 3)
        scan_grid.setColumnStretch(1, 1)
        scan_grid.setColumnStretch(3, 1)
        scan_btns = QHBoxLayout()
        scan_btns.addStretch(1)
        scan_btns.addWidget(self._start_scan_btn)
        scan_btns.addWidget(self._abort_scan_btn)
        scan_grid.addLayout(scan_btns, 5, 0, 1, 4)
        root.addWidget(scan_box)

        telem_box, telem_layout = make_group("Telemetry")
        assert isinstance(telem_layout, QVBoxLayout)
        self._temp_diode_label = QLabel("Diode temperature: —")
        self._temp_env_label = QLabel("Environment temperature: —")
        self._temp_reg_label = QLabel("Temperature regulated: —")
        self._hours_label = QLabel("Operating hours: —")
        self._cycles_completed_label = QLabel("Cycles completed: —")
        for label in (
            self._temp_diode_label,
            self._temp_env_label,
            self._temp_reg_label,
            self._hours_label,
            self._cycles_completed_label,
        ):
            telem_layout.addWidget(label)
        root.addWidget(telem_box)

        log_box, log_layout = make_group("Status log")
        assert isinstance(log_layout, QVBoxLayout)
        self._status_area = QTextEdit()
        self._status_area.setReadOnly(True)
        self._status_area.setMinimumHeight(120)
        self._status_area.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        log_layout.addWidget(self._status_area)
        root.addWidget(log_box, 1)

        self._refresh_btn.clicked.connect(self._on_refresh)
        self._connect_btn.clicked.connect(self._on_connect)
        self._disconnect_btn.clicked.connect(self._on_disconnect)
        self._laser_output_checkbox.stateChanged.connect(self._on_laser_output_changed)
        self._interlock_inhibit_checkbox.stateChanged.connect(self._on_interlock_inhibit_changed)
        self._check_errors_btn.clicked.connect(self._on_check_errors)
        self._tuning_domain_combo.currentIndexChanged.connect(
            lambda: self._commit_combo(
                self._tuning_domain_combo,
                TuningDomain,
                "tuning_domain",
                "apply_tuning_domain",
                "tuning_domain",
                default=int(TuningDomain.WAVELENGTH),
            )
        )
        self._modulation_combo.currentIndexChanged.connect(
            lambda: self._commit_combo(
                self._modulation_combo,
                ModulationSource,
                "modulation_source",
                "apply_modulation",
                "modulation",
            )
        )
        self._power_unit_combo.currentIndexChanged.connect(
            lambda: self._commit_combo(
                self._power_unit_combo,
                PowerUnit,
                "power_unit",
                "apply_power_unit",
                "power_unit",
            )
        )
        self._center_tune_btn.clicked.connect(self._on_set_center_wavelength)
        self._wire_live_commits()
        self._scan_mode_combo.currentIndexChanged.connect(
            lambda: self._commit_combo(
                self._scan_mode_combo,
                ScanMode,
                "scan_mode",
                "apply_scan_mode",
                "scan_mode",
            )
        )
        self._trigger_polarity_combo.currentIndexChanged.connect(
            lambda: self._commit_combo(
                self._trigger_polarity_combo,
                TriggerPolarity,
                "trigger_polarity",
                "apply_trigger_polarity",
                "trigger_polarity",
            )
        )
        self._start_scan_btn.clicked.connect(self._on_start_scan)
        self._abort_scan_btn.clicked.connect(self._on_abort_scan)

    def _set_controls_enabled(self, enabled: bool) -> None:
        for widget in (
            self._laser_output_checkbox,
            self._interlock_inhibit_checkbox,
            self._check_errors_btn,
            self._tuning_domain_combo,
            self._tune_spin,
            self._modulation_combo,
            self._center_tune_btn,
            self._regulation_power_spin,
            self._power_unit_combo,
            self._regulation_current_spin,
            self._scan_start_spin,
            self._scan_stop_spin,
            self._scan_speed_spin,
            self._scan_cycles_spin,
            self._scan_dwell_spin,
            self._scan_step_spin,
            self._scan_mode_combo,
            self._trigger_polarity_combo,
            self._start_scan_btn,
            self._abort_scan_btn,
        ):
            widget.setEnabled(enabled)
        self._refresh_btn.setEnabled(True)
        self._apply_connection_buttons()

    def _apply_connection_buttons(self) -> None:
        if self._remote_control:
            self._connect_btn.setEnabled(False)
            self._disconnect_btn.setEnabled(False)
            return
        connected = self._is_laser_connected()
        self._connect_btn.setEnabled((not connected) and len(self._devices) > 0)
        self._disconnect_btn.setEnabled(connected)

    def _connected_hint(self) -> str:
        if not self._is_laser_connected():
            return "Disconnected."
        return f"Connected on {self._controller.laser.port}."

    def _is_laser_connected(self) -> bool:
        return self._controller is not None and self._controller.is_connected

    def remotecontrol(self, enabled: bool) -> None:
        """Lock setpoint cells while the notebook drives ``laser`` (``True``), or unlock (``False``)."""
        self._remote_control = bool(enabled)
        if enabled:
            self._set_controls_enabled(False)
            return
        if self._is_laser_connected():
            self._set_controls_enabled(True)
            self.sync_gui_panel_to_laser()

    def sync_gui_panel_to_laser(self) -> None:
        """Re-query the instrument and fill the panel (call after programmatic ``laser.set.*``)."""
        if not self._is_laser_connected():
            return
        if self._serial_busy:
            self._pending_commits["sync"] = self.sync_gui_panel_to_laser
            return
        self._start_job("sync", self._controller.refresh)

    # --- Jobs ---

    def _start_job(self, action: str, fn, *args, **kwargs) -> None:
        if self._serial_busy:
            return
        self._serial_busy = True
        self._runner.request_run.emit(Job(action=action, fn=fn, args=args, kwargs=kwargs))

    def _flush_pending_commit(self) -> None:
        if not self._pending_commits or self._serial_busy:
            return
        _key, fn = next(iter(self._pending_commits.items()))
        self._pending_commits.pop(_key)
        fn()

    def _on_job_finished(self, action: str, status: StatusMessage, payload) -> None:
        self._serial_busy = False
        try:
            self._handle_job_finished(action, status, payload)
        finally:
            self._flush_pending_commit()

    def _handle_job_finished(self, action: str, status: StatusMessage, payload) -> None:
        if action == "telemetry":
            self._telemetry_running = False

        if not status.ok:
            self._log(status, action)
            # Keep the typed value on a failed live numeric write (same as NiceGUI).
            if (
                self._controller is not None
                and action not in _NO_SPECS_REFRESH
                and action not in _LIVE_NUMERIC
            ):
                self._apply_specs_to_ui()
            return

        if action == "telemetry":
            self._update_telemetry_from_snapshot(payload)
            return

        if action == "scan":
            devices = list(payload or [])
            current = self._device_from_connected_laser()
            if current is not None and not any(d.port == current.port for d in devices):
                devices.insert(0, current)
            select_port = current.port if current is not None else None
            self._fill_device_combo(devices, select_port=select_port)
            if self._is_laser_connected():
                self._discovery_hint.setText(self._connected_hint())
            else:
                self._discovery_hint.setText(f"Found {len(devices)} laser(s).")
            self._apply_connection_buttons()
            return

        if action == "sync":
            if self._is_laser_connected():
                self._apply_specs_to_ui()
            return

        self._log(status, action)

        if action == "connect":
            if payload is not None:
                self._controller = payload
            self._set_controls_enabled(True)
            self._show_connected_device_in_menu()
            self._discovery_hint.setText(self._connected_hint())
            self._apply_specs_to_ui()
            self._telemetry_timer.start()
            return

        if action == "disconnect":
            self._telemetry_timer.stop()
            self._controller = None
            self._remote_control = False
            self._set_controls_enabled(False)
            self._discovery_hint.setText("Disconnected.")
            self._on_refresh()
            return

        if self._controller is not None and action not in _NO_SPECS_REFRESH:
            self._apply_specs_to_ui()

    # --- Discovery ---

    def _on_refresh(self) -> None:
        self._discovery_hint.setText("Scanning USB ports…")
        self._start_job("scan", self._discovery.scan, None)

    def _on_connect(self) -> None:
        if self._serial_busy or self._remote_control:
            return
        if self._device_select.currentIndex() < 0:
            self._log(StatusMessage.failure("Select a laser first."), "connect")
            return
        device = self._devices[self._device_select.currentIndex()]
        self._discovery_hint.setText(f"Connecting to {device.port}…")

        def _connect():
            controller = create_laser_controller(device)
            controller.connect(device.port)
            return controller

        self._start_job("connect", _connect)

    def _on_disconnect(self) -> None:
        if self._controller is None:
            return
        if self._serial_busy:
            self._pending_commits["disconnect"] = self._on_disconnect
            return

        def _disconnect():
            self._controller.disconnect()
            return True

        self._start_job("disconnect", _disconnect)

    def _on_check_errors(self) -> None:
        if not self._controller or self._serial_busy or self._remote_control:
            return
        self._start_job("errors", self._controller.check_errors)

    def _on_laser_output_changed(self, state: int) -> None:
        if self._updating_controls or self._remote_control or not self._controller or self._serial_busy:
            return
        enabled = Qt.CheckState(state) == Qt.CheckState.Checked
        self._start_job("laser_output", self._controller.apply_laser_output, enabled)

    def _on_interlock_inhibit_changed(self, state: int) -> None:
        if self._updating_controls or self._remote_control or not self._controller or self._serial_busy:
            return
        inhibit = Qt.CheckState(state) == Qt.CheckState.Checked
        self._start_job(
            "software_interlock",
            self._controller.apply_software_interlock_inhibit,
            inhibit,
        )

    # --- Live numeric / enum commits ---

    def _wire_live_commits(self) -> None:
        for key, attr, _apply, _as_int in _NUMERIC_COMMITS:
            getattr(self, attr).editingFinished.connect(
                lambda k=key: self._debounce_commit(k)
            )

    def _debounce_commit(self, key: str) -> None:
        if self._updating_controls or self._remote_control:
            return
        timer = self._commit_timers.get(key)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            self._commit_timers[key] = timer
        try:
            timer.timeout.disconnect()
        except TypeError:
            pass
        timer.timeout.connect(lambda k=key: self._commit_numeric(k))
        timer.start(250)

    def _commit_numeric(self, key: str) -> None:
        if self._updating_controls or self._remote_control or not self._controller:
            return
        if self._serial_busy:
            self._pending_commits[key] = lambda k=key: self._commit_numeric(k)
            return
        for item_key, attr, apply_name, as_integer in _NUMERIC_COMMITS:
            if item_key == key:
                break
        else:
            return
        spin = getattr(self, attr)
        raw = spin.typed_value()
        value: int | float = int(round(raw)) if as_integer else raw
        apply = getattr(self._controller, apply_name)
        kwargs = {"wait": True} if apply_name == "apply_tune" else {}
        self._start_job(key, apply, value, **kwargs)

    def _commit_combo(
        self,
        combo: QComboBox,
        enum_cls,
        spec_attr: str,
        apply_name: str,
        action: str,
        *,
        default: int | None = None,
    ) -> None:
        if self._updating_controls or self._remote_control or not self._controller or self._serial_busy:
            return
        if combo.currentIndex() < 0:
            return
        value = enum_cls(int(combo.currentData()))
        current = getattr(self._controller.specs, spec_attr, None)
        previous = int(current) if current is not None else default
        if previous is not None and int(value) == previous:
            return
        self._start_job(action, getattr(self._controller, apply_name), value)

    def _on_set_center_wavelength(self) -> None:
        if not self._controller or self._serial_busy or self._remote_control:
            return
        specs = self._controller.specs
        if specs.wavelength_min is None or specs.wavelength_max is None:
            self._log(
                StatusMessage.failure("Wavelength range not available (wmin?/wmax? missing)."),
                "center wavelength",
            )
            return
        center = (specs.wavelength_min + specs.wavelength_max) / 2.0
        self._start_job("center wavelength", self._controller.apply_tune, center, wait=True)

    def _collect_scan_params_from_ui(self) -> tuple[Optional[StatusMessage], dict]:
        if not self._controller:
            return StatusMessage.failure("Not connected."), {}

        bindings = bindings_from_specs(self._controller.specs)
        start = float(self._scan_start_spin.value()) if bindings.scan_start.enabled else None
        stop = float(self._scan_stop_spin.value()) if bindings.scan_stop.enabled else None
        if start is not None and stop is not None and start > stop:
            return StatusMessage.failure(
                f"Scan start ({start}) must be ≤ scan stop ({stop}).",
                command="scan params",
            ), {}

        mode = None
        if bindings.scan_mode.enabled and self._scan_mode_combo.currentIndex() >= 0:
            mode = ScanMode(int(self._scan_mode_combo.currentData()))
        trigger_polarity = None
        if (
            bindings.trigger_polarity.enabled
            and self._trigger_polarity_combo.currentIndex() >= 0
        ):
            trigger_polarity = TriggerPolarity(int(self._trigger_polarity_combo.currentData()))

        return None, {
            "start": start,
            "stop": stop,
            "speed": (
                float(self._scan_speed_spin.value()) if bindings.scan_speed.enabled else None
            ),
            "cycles": (
                int(self._scan_cycles_spin.value()) if bindings.scan_cycles.enabled else None
            ),
            "dwell_ms": (
                float(self._scan_dwell_spin.value()) if bindings.scan_dwell_ms.enabled else None
            ),
            "step": float(self._scan_step_spin.value()) if bindings.scan_step.enabled else None,
            "mode": mode,
            "trigger_polarity": trigger_polarity,
        }

    def _on_start_scan(self) -> None:
        if not self._controller or self._serial_busy or self._remote_control:
            return
        error, kwargs = self._collect_scan_params_from_ui()
        if error is not None:
            self._log(error, "start scan")
            return

        def _start():
            apply_status = self._controller.apply_scan_params(**kwargs)
            if not apply_status.ok:
                return apply_status
            return self._controller.start_scan()

        self._start_job("start scan", _start)

    def _on_abort_scan(self) -> None:
        if not self._controller or self._serial_busy or self._remote_control:
            return
        self._start_job("abort scan", self._controller.abort_scan)

    def _schedule_telemetry_refresh(self) -> None:
        if self._controller is None or self._telemetry_running or self._serial_busy:
            return
        self._telemetry_running = True
        self._start_job("telemetry", self._controller.refresh_telemetry)

    # --- Specs ↔ UI ---

    def _apply_specs_to_ui(self) -> None:
        if self._controller is None:
            return

        specs = self._controller.specs
        bindings: ControlBindings = bindings_from_specs(specs)
        domain = (
            specs.tuning_domain
            if specs.tuning_domain is not None
            else TuningDomain.WAVELENGTH
        )
        click_step = tune_click_step(domain)

        self._updating_controls = True
        try:
            self._identity_label.setText(
                identity_display(specs.identity, self._controller.laser.port)
            )
            self._tuning_box.setTitle(
                "Frequency tuning" if is_frequency_domain(domain) else "Wavelength tuning"
            )
            if specs.loop_mode is not None:
                self._loop_mode_label.setText(
                    f"Loop mode: {LOOP_MODE_LABELS.get(int(specs.loop_mode), specs.loop_mode)}"
                )

            self._power_label.setText(numeric_field_label("Power setpoint", bindings.power))
            apply_numeric_binding(
                self._regulation_power_spin, bindings.power, decimals=3, click_step=0.01
            )
            apply_select_binding(self._power_unit_combo, bindings.power_unit)

            self._current_label.setText(numeric_field_label("Current (mA)", bindings.current))
            apply_numeric_binding(
                self._regulation_current_spin, bindings.current, decimals=2, click_step=0.1
            )

            apply_select_binding(self._tuning_domain_combo, bindings.tuning_domain)
            self._tune_label.setText(
                numeric_field_label(tune_setpoint_label(domain), bindings.tune)
            )
            apply_numeric_binding(
                self._tune_spin, bindings.tune, decimals=4, click_step=click_step
            )
            apply_select_binding(self._modulation_combo, bindings.modulation)

            self._scan_start_label.setText(
                numeric_field_label(scan_bound_label("Scan start", domain), bindings.scan_start)
            )
            self._scan_stop_label.setText(
                numeric_field_label(scan_bound_label("Scan stop", domain), bindings.scan_stop)
            )
            self._scan_speed_label.setText(
                numeric_field_label(
                    scan_speed_label(domain), bindings.scan_speed, as_integer=True
                )
            )
            self._scan_cycles_label.setText(
                numeric_field_label(
                    "Scan cycles (-1 = ∞)", bindings.scan_cycles, as_integer=True
                )
            )
            self._scan_dwell_label.setText(
                numeric_field_label("Dwell (ms)", bindings.scan_dwell_ms)
            )
            self._scan_step_label.setText(
                numeric_field_label(scan_step_label(domain), bindings.scan_step)
            )
            apply_numeric_binding(
                self._scan_start_spin, bindings.scan_start, decimals=4, click_step=click_step
            )
            apply_numeric_binding(
                self._scan_stop_spin, bindings.scan_stop, decimals=4, click_step=click_step
            )
            apply_numeric_binding(
                self._scan_speed_spin, bindings.scan_speed, decimals=0, click_step=1.0
            )
            apply_numeric_binding(
                self._scan_cycles_spin, bindings.scan_cycles, decimals=0, click_step=1.0
            )
            apply_numeric_binding(
                self._scan_dwell_spin, bindings.scan_dwell_ms, decimals=3, click_step=1.0
            )
            apply_numeric_binding(
                self._scan_step_spin, bindings.scan_step, decimals=4, click_step=click_step
            )
            apply_select_binding(self._scan_mode_combo, bindings.scan_mode)
            apply_select_binding(self._trigger_polarity_combo, bindings.trigger_polarity)

            self._laser_output_checkbox.setChecked(bool(bindings.laser_output))
            self._interlock_inhibit_checkbox.setChecked(bool(bindings.software_interlock_inhibit))
            if specs.interlock_state is not None:
                label = INTERLOCK_LABELS.get(int(specs.interlock_state), str(specs.interlock_state))
                self._interlock_state_label.setText(f"Interlock: {label}")
            if specs.scan_cycles_count is not None:
                self._cycles_completed_label.setText(f"Cycles completed: {specs.scan_cycles_count}")
        finally:
            self._updating_controls = False

    def _update_telemetry_from_snapshot(self, snap) -> None:
        if snap is None:
            return
        if getattr(snap, "laser_diode_temperature", None) is not None:
            self._temp_diode_label.setText(
                f"Diode temperature: {snap.laser_diode_temperature:.2f} °C"
            )
        if getattr(snap, "environment_temperature", None) is not None:
            self._temp_env_label.setText(
                f"Environment temperature: {snap.environment_temperature:.2f} °C"
            )
        if getattr(snap, "temperature_regulated", None) is not None:
            self._temp_reg_label.setText(
                f"Temperature regulated: {'yes' if snap.temperature_regulated else 'no'}"
            )
        if getattr(snap, "operating_hours", None) is not None:
            self._hours_label.setText(f"Operating hours: {snap.operating_hours:.1f} h")
        if getattr(snap, "scan_cycles_count", None) is not None:
            self._cycles_completed_label.setText(f"Cycles completed: {snap.scan_cycles_count}")
        if getattr(snap, "interlock_state", None) is not None:
            label = INTERLOCK_LABELS.get(int(snap.interlock_state), str(snap.interlock_state))
            self._interlock_state_label.setText(f"Interlock: {label}")
        if getattr(snap, "laser_output", None) is not None:
            self._updating_controls = True
            try:
                self._laser_output_checkbox.setChecked(bool(snap.laser_output))
            finally:
                self._updating_controls = False

    def _log(self, status: StatusMessage, action: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        prefix = "OK" if status.ok else "ERR"
        line = f"[{stamp}] {prefix} {action}: {status.summary}"
        if status.command:
            line += f" ({status.command})"
        current = self._status_area.toPlainText().strip()
        new_value = line if not current else f"{current}\n{line}"
        self._status_area.setPlainText("\n".join(new_value.splitlines()[-80:]))


def create_laser_widget(
    laser: Optional[TLB8800] = None,
    *,
    parent: Optional[QWidget] = None,
) -> LaserControlWidget:
    """Factory used by both standalone app and Jupyter embedding."""
    ensure_qapp()
    return LaserControlWidget(laser, parent=parent)
