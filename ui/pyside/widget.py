"""PySide6 twin widget for Laser control.

This widget mirrors the structure and behavior of the NiceGUI panel, using:
- shared `core/` and existing `TLB8800Controller`
- a background runner to keep UI responsive

It is intentionally self-contained in `ui/pyside/`.
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
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.discovery_service import DiscoveryService
from core.factory import create_laser_controller
from core.models import DiscoveredDevice, StatusMessage
from core.tlb8800 import (
    INTERLOCK_LABELS,
    LOOP_MODE_LABELS,
    MODULATION_OPTIONS,
    POWER_UNIT_OPTIONS,
    SCAN_MODE_OPTIONS,
    TRIGGER_POLARITY_OPTIONS,
    TUNING_DOMAIN_OPTIONS,
    bindings_from_specs,
    scan_bound_label,
    scan_speed_label,
    scan_step_label,
    tune_setpoint_label,
)
from core.tlb8800.models import ControlBindings
from newfocus.tlb8800_utilities.types import (
    ModulationSource,
    PowerUnit,
    ScanMode,
    TriggerPolarity,
    TuningDomain,
)

from ui.pyside.controller_runner import ControllerRunner, Job
from ui.pyside.ui_helpers import (
    apply_numeric_binding_double,
    apply_numeric_binding_int,
    apply_select_binding,
    make_group,
    set_field_expanding,
)


def ensure_qapp() -> QApplication:
    """Create/reuse QApplication (works for normal Python and many notebook setups)."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


class LaserControlWidget(QWidget):
    """Full laser control widget (PySide6)."""

    _TELEMETRY_INTERVAL_MS = 5000

    def __init__(self, *, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._discovery = DiscoveryService()
        self._controller = None
        self._devices: list[DiscoveredDevice] = []

        self._runner = ControllerRunner()
        self._runner.finished.connect(self._on_job_finished)

        self._serial_busy = False
        self._updating_controls = False
        self._telemetry_running = False

        self._build_ui()

        self._telemetry_timer = QTimer(self)
        self._telemetry_timer.timeout.connect(self._schedule_telemetry_refresh)
        self._telemetry_timer.setInterval(self._TELEMETRY_INTERVAL_MS)

        self._set_controls_enabled(False)

        # Match NiceGUI: scan USB ports once shortly after the widget is shown.
        QTimer.singleShot(50, self._on_refresh)

    def shutdown(self) -> None:
        self._telemetry_timer.stop()
        self._runner.shutdown()

    # --- UI construction ---

    def _build_ui(self) -> None:
        root = QVBoxLayout()
        root.setSpacing(10)
        self.setLayout(root)

        # Discovery (top, not grouped)
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

        # --- Laser status ---
        status_box, status_layout = make_group("Laser status")
        assert isinstance(status_layout, QVBoxLayout)
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
        status_layout.addLayout(output_row)
        status_layout.addWidget(self._interlock_state_label)
        status_layout.addWidget(self._loop_mode_label)
        root.addWidget(status_box)

        # --- Power / current ---
        power_box, power_grid = make_group("Power / current", grid=True)
        assert isinstance(power_grid, QGridLayout)
        self._regulation_power_spin = QDoubleSpinBox()
        self._regulation_power_spin.setDecimals(3)
        self._regulation_power_spin.setSingleStep(0.01)
        self._regulation_power_spin.setMaximum(1e9)
        set_field_expanding(self._regulation_power_spin)

        self._power_unit_combo = QComboBox()
        for k, label in POWER_UNIT_OPTIONS.items():
            self._power_unit_combo.addItem(label, k)
        set_field_expanding(self._power_unit_combo)
        self._power_unit_combo.setMinimumWidth(90)

        self._regulation_current_spin = QDoubleSpinBox()
        self._regulation_current_spin.setDecimals(2)
        self._regulation_current_spin.setSingleStep(0.1)
        self._regulation_current_spin.setMaximum(1e9)
        set_field_expanding(self._regulation_current_spin)

        self._apply_regulation_btn = QPushButton("Apply regulation")

        power_grid.addWidget(QLabel("Power setpoint"), 0, 0)
        power_grid.addWidget(self._regulation_power_spin, 0, 1)
        power_grid.addWidget(QLabel("Unit"), 0, 2)
        power_grid.addWidget(self._power_unit_combo, 0, 3)
        power_grid.addWidget(QLabel("Current (mA)"), 1, 0)
        power_grid.addWidget(self._regulation_current_spin, 1, 1)
        power_grid.setColumnStretch(1, 1)
        power_grid.setColumnStretch(3, 1)

        power_btns = QHBoxLayout()
        power_btns.addStretch(1)
        power_btns.addWidget(self._apply_regulation_btn)
        power_grid.addLayout(power_btns, 2, 0, 1, 4)
        root.addWidget(power_box)

        # --- Tuning ---
        tuning_box, tuning_grid = make_group("Tuning", grid=True)
        assert isinstance(tuning_grid, QGridLayout)

        self._tuning_domain_combo = QComboBox()
        for k, label in TUNING_DOMAIN_OPTIONS.items():
            self._tuning_domain_combo.addItem(label, k)
        set_field_expanding(self._tuning_domain_combo)

        self._tune_label = QLabel(tune_setpoint_label(TuningDomain.WAVELENGTH))
        self._tune_spin = QDoubleSpinBox()
        self._tune_spin.setDecimals(4)
        self._tune_spin.setSingleStep(0.001)
        self._tune_spin.setMaximum(1e12)
        self._tune_spin.setValue(0.0)
        set_field_expanding(self._tune_spin)

        self._modulation_combo = QComboBox()
        for k, label in MODULATION_OPTIONS.items():
            self._modulation_combo.addItem(label, k)
        set_field_expanding(self._modulation_combo)

        self._apply_tuning_btn = QPushButton("Apply tuning")
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
        tuning_btns.addWidget(self._apply_tuning_btn)
        tuning_grid.addLayout(tuning_btns, 3, 0, 1, 4)
        root.addWidget(tuning_box)

        # --- Scan / sweep ---
        scan_box, scan_grid = make_group("Scan / sweep", grid=True)
        assert isinstance(scan_grid, QGridLayout)

        self._scan_start_label = QLabel(scan_bound_label("Scan start", TuningDomain.WAVELENGTH))
        self._scan_start_spin = QDoubleSpinBox()
        self._scan_start_spin.setDecimals(4)
        self._scan_start_spin.setSingleStep(0.001)
        self._scan_start_spin.setMaximum(1e12)
        set_field_expanding(self._scan_start_spin)

        self._scan_stop_label = QLabel(scan_bound_label("Scan stop", TuningDomain.WAVELENGTH))
        self._scan_stop_spin = QDoubleSpinBox()
        self._scan_stop_spin.setDecimals(4)
        self._scan_stop_spin.setSingleStep(0.001)
        self._scan_stop_spin.setMaximum(1e12)
        set_field_expanding(self._scan_stop_spin)

        self._scan_speed_label = QLabel(scan_speed_label(TuningDomain.WAVELENGTH))
        self._scan_speed_spin = QSpinBox()
        self._scan_speed_spin.setSingleStep(1)
        self._scan_speed_spin.setMaximum(1_000_000_000)
        set_field_expanding(self._scan_speed_spin)

        self._scan_cycles_spin = QSpinBox()
        self._scan_cycles_spin.setSingleStep(1)
        self._scan_cycles_spin.setMinimum(-1)
        self._scan_cycles_spin.setMaximum(1_000_000)
        set_field_expanding(self._scan_cycles_spin)

        self._scan_dwell_spin = QDoubleSpinBox()
        self._scan_dwell_spin.setDecimals(1)
        self._scan_dwell_spin.setSingleStep(1.0)
        self._scan_dwell_spin.setMaximum(1e9)
        set_field_expanding(self._scan_dwell_spin)

        self._scan_step_label = QLabel(scan_step_label(TuningDomain.WAVELENGTH))
        self._scan_step_spin = QDoubleSpinBox()
        self._scan_step_spin.setDecimals(4)
        self._scan_step_spin.setSingleStep(0.001)
        self._scan_step_spin.setMaximum(1e9)
        set_field_expanding(self._scan_step_spin)

        self._scan_mode_combo = QComboBox()
        for k, label in SCAN_MODE_OPTIONS.items():
            self._scan_mode_combo.addItem(label, k)
        set_field_expanding(self._scan_mode_combo)

        self._trigger_polarity_combo = QComboBox()
        for k, label in TRIGGER_POLARITY_OPTIONS.items():
            self._trigger_polarity_combo.addItem(label, k)
        set_field_expanding(self._trigger_polarity_combo)

        self._apply_scan_params_btn = QPushButton("Apply scan params")
        self._start_scan_btn = QPushButton("Start scan")
        self._abort_scan_btn = QPushButton("Abort scan")

        scan_grid.addWidget(self._scan_start_label, 0, 0)
        scan_grid.addWidget(self._scan_start_spin, 0, 1)
        scan_grid.addWidget(self._scan_stop_label, 0, 2)
        scan_grid.addWidget(self._scan_stop_spin, 0, 3)

        scan_grid.addWidget(self._scan_speed_label, 1, 0)
        scan_grid.addWidget(self._scan_speed_spin, 1, 1)
        scan_grid.addWidget(QLabel("Scan cycles (-1 = ∞)"), 1, 2)
        scan_grid.addWidget(self._scan_cycles_spin, 1, 3)

        scan_grid.addWidget(QLabel("Dwell (ms)"), 2, 0)
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
        scan_btns.addWidget(self._apply_scan_params_btn)
        scan_btns.addWidget(self._start_scan_btn)
        scan_btns.addWidget(self._abort_scan_btn)
        scan_grid.addLayout(scan_btns, 5, 0, 1, 4)
        root.addWidget(scan_box)

        # --- Telemetry ---
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

        # --- Status log ---
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

        # Wire events
        self._refresh_btn.clicked.connect(self._on_refresh)
        self._connect_btn.clicked.connect(self._on_connect)
        self._disconnect_btn.clicked.connect(self._on_disconnect)

        self._laser_output_checkbox.stateChanged.connect(self._on_laser_output_changed)
        self._interlock_inhibit_checkbox.stateChanged.connect(
            self._on_interlock_inhibit_changed
        )
        self._check_errors_btn.clicked.connect(self._on_check_errors)

        self._apply_regulation_btn.clicked.connect(self._on_apply_regulation)
        self._tuning_domain_combo.currentIndexChanged.connect(self._on_tuning_domain_change)

        self._apply_tuning_btn.clicked.connect(self._on_apply_tuning)
        self._center_tune_btn.clicked.connect(self._on_set_center_wavelength)

        self._apply_scan_params_btn.clicked.connect(self._on_apply_scan_params)
        self._start_scan_btn.clicked.connect(self._on_start_scan)
        self._abort_scan_btn.clicked.connect(self._on_abort_scan)

    def _set_controls_enabled(self, enabled: bool) -> None:
        self._connect_btn.setEnabled(enabled)
        self._disconnect_btn.setEnabled(enabled)
        self._laser_output_checkbox.setEnabled(enabled)
        self._interlock_inhibit_checkbox.setEnabled(enabled)
        self._check_errors_btn.setEnabled(enabled)

        self._apply_regulation_btn.setEnabled(enabled)
        self._tuning_domain_combo.setEnabled(enabled)
        self._tune_spin.setEnabled(enabled)
        self._modulation_combo.setEnabled(enabled)
        self._apply_tuning_btn.setEnabled(enabled)
        self._center_tune_btn.setEnabled(enabled)

        for w in (
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
            self._apply_scan_params_btn,
            self._start_scan_btn,
            self._abort_scan_btn,
        ):
            w.setEnabled(enabled)

        self._refresh_btn.setEnabled(True)

    # --- Jobs ---

    def _start_job(self, action: str, fn, *args, **kwargs) -> None:
        if self._serial_busy:
            return
        self._serial_busy = True
        self._runner.request_run.emit(Job(action=action, fn=fn, args=args, kwargs=kwargs))

    def _on_job_finished(self, action: str, status: StatusMessage, payload) -> None:
        self._serial_busy = False
        if action == "telemetry":
            self._telemetry_running = False

        if not status.ok:
            self._log(status, action)
            return

        # Successful telemetry/scan: update UI quietly (no status-log spam).
        if action == "telemetry":
            self._update_telemetry_from_snapshot(payload)
            return

        if action == "scan":
            self._discovery_hint.setText(f"Found {len(payload or [])} laser(s).")
            self._devices = list(payload or [])
            self._device_select.clear()
            for d in self._devices:
                self._device_select.addItem(d.list_label)
            self._connect_btn.setEnabled(len(self._devices) > 0)
            self._disconnect_btn.setEnabled(False)
            return

        self._log(status, action)

        if action == "connect":
            if payload is not None:
                self._controller = payload
            self._set_controls_enabled(True)
            self._apply_specs_to_ui()
            self._telemetry_timer.start()
            return

        if action == "disconnect":
            self._telemetry_timer.stop()
            self._controller = None
            self._set_controls_enabled(False)
            self._discovery_hint.setText("Disconnected.")
            return

        if self._controller is not None and action in {
            "laser_output",
            "software_interlock",
            "regulation",
            "tuning_domain",
            "tuning",
            "center wavelength",
            "scan params",
            "start scan",
            "abort scan",
        }:
            self._apply_specs_to_ui()

    # --- UI actions ---

    def _on_refresh(self) -> None:
        self._discovery_hint.setText("Scanning USB ports…")
        self._start_job("scan", self._discovery.scan, None)

    def _on_connect(self) -> None:
        if self._serial_busy:
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

        def _disconnect():
            controller = self._controller
            controller.disconnect()
            return True

        self._start_job("disconnect", _disconnect)
        self._set_controls_enabled(False)

    def _on_check_errors(self) -> None:
        if not self._controller or self._serial_busy:
            return
        self._start_job("errors", self._controller.check_errors)

    def _on_laser_output_changed(self, state: int) -> None:
        if self._updating_controls or not self._controller or self._serial_busy:
            return
        # stateChanged emits int; Qt.Checked is CheckState and does not == int in PySide6.
        enabled = Qt.CheckState(state) == Qt.CheckState.Checked
        self._start_job(
            "laser_output",
            self._controller.apply_laser_output,
            enabled,
        )

    def _on_interlock_inhibit_changed(self, state: int) -> None:
        if self._updating_controls or not self._controller or self._serial_busy:
            return
        inhibit = Qt.CheckState(state) == Qt.CheckState.Checked
        self._start_job(
            "software_interlock",
            self._controller.apply_software_interlock_inhibit,
            inhibit,
        )

    def _on_apply_regulation(self) -> None:
        if not self._controller or self._serial_busy:
            return
        bindings: ControlBindings = bindings_from_specs(self._controller.specs)

        if bindings.power.enabled:
            value = float(self._regulation_power_spin.value())
            unit_val = int(self._power_unit_combo.currentData())
            unit = PowerUnit(unit_val) if bindings.power_unit.enabled else None

            def _apply():
                status = self._controller.apply_power(value)
                if not status.ok:
                    return status
                if unit is not None:
                    return self._controller.apply_power_unit(unit)
                return status

            self._start_job("regulation", _apply)
        elif bindings.current.enabled:
            value = float(self._regulation_current_spin.value())

            def _apply():
                return self._controller.apply_current(value)

            self._start_job("regulation", _apply)
        else:
            self._log(StatusMessage.failure("No regulation control available."), "regulation")

    def _on_tuning_domain_change(self, _idx: int) -> None:
        if self._updating_controls or not self._controller or self._serial_busy:
            return
        if self._tuning_domain_combo.currentIndex() < 0:
            return
        domain = TuningDomain(int(self._tuning_domain_combo.currentData()))
        previous = (
            int(self._controller.specs.tuning_domain)
            if self._controller.specs.tuning_domain is not None
            else int(TuningDomain.WAVELENGTH)
        )
        if int(domain) == previous:
            return

        self._start_job("tuning_domain", self._controller.apply_tuning_domain, domain)

    def _on_apply_tuning(self) -> None:
        if not self._controller or self._serial_busy:
            return
        bindings = bindings_from_specs(self._controller.specs)

        tune_nm: Optional[float] = None
        if bindings.tune.enabled:
            tune_nm = float(self._tune_spin.value())

        modulation: Optional[ModulationSource] = None
        if bindings.modulation.enabled and self._modulation_combo.currentIndex() >= 0:
            modulation = ModulationSource(int(self._modulation_combo.currentData()))

        if tune_nm is None and modulation is None:
            self._log(StatusMessage.failure("No tuning parameters to apply."), "tuning")
            return

        def _apply():
            return self._controller.apply_tuning(
                tune_nm=tune_nm,
                modulation=modulation,
                wait_tune=True,
            )

        self._start_job("tuning", _apply)

    def _on_set_center_wavelength(self) -> None:
        if not self._controller or self._serial_busy:
            return
        specs = self._controller.specs
        if specs.wavelength_min is None or specs.wavelength_max is None:
            self._log(
                StatusMessage.failure("Wavelength range not available (wmin?/wmax? missing)."),
                "center wavelength",
            )
            return
        center = (specs.wavelength_min + specs.wavelength_max) / 2.0
        # wait is keyword-only on apply_tune
        self._start_job("center wavelength", self._controller.apply_tune, center, wait=True)

    def _collect_scan_params_from_ui(self, *, omit_step: bool) -> tuple[Optional[StatusMessage], dict]:
        if not self._controller:
            return StatusMessage.failure("Not connected."), {}

        b = bindings_from_specs(self._controller.specs)

        start = float(self._scan_start_spin.value()) if b.scan_start.enabled else None
        stop = float(self._scan_stop_spin.value()) if b.scan_stop.enabled else None
        if start is not None and stop is not None and start > stop:
            return StatusMessage.failure(
                f"Scan start ({start}) must be ≤ scan stop ({stop}).",
                command="scan params",
            ), {}

        mode = None
        if b.scan_mode.enabled and self._scan_mode_combo.currentIndex() >= 0:
            mode = ScanMode(int(self._scan_mode_combo.currentData()))

        trigger_polarity = None
        if b.trigger_polarity.enabled and self._trigger_polarity_combo.currentIndex() >= 0:
            trigger_polarity = TriggerPolarity(int(self._trigger_polarity_combo.currentData()))

        step = None
        if not omit_step and b.scan_step.enabled:
            step = float(self._scan_step_spin.value())

        cycles = int(self._scan_cycles_spin.value()) if b.scan_cycles.enabled else None
        dwell_ms = float(self._scan_dwell_spin.value()) if b.scan_dwell_ms.enabled else None
        speed = float(self._scan_speed_spin.value()) if b.scan_speed.enabled else None

        return None, {
            "start": start,
            "stop": stop,
            "speed": speed,
            "cycles": cycles,
            "dwell_ms": dwell_ms,
            "step": step,
            "mode": mode,
            "trigger_polarity": trigger_polarity,
        }

    def _on_apply_scan_params(self) -> None:
        if not self._controller or self._serial_busy:
            return
        error, kwargs = self._collect_scan_params_from_ui(omit_step=False)
        if error is not None:
            self._log(error, "scan params")
            return
        self._start_job("scan params", self._controller.apply_scan_params, **kwargs)

    def _on_start_scan(self) -> None:
        if not self._controller or self._serial_busy:
            return
        error, kwargs = self._collect_scan_params_from_ui(omit_step=True)
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
        if not self._controller or self._serial_busy:
            return
        self._start_job("abort scan", self._controller.abort_scan)

    def _schedule_telemetry_refresh(self) -> None:
        if self._controller is None or self._telemetry_running or self._serial_busy:
            return
        self._telemetry_running = True

        def _telemetry():
            return self._controller.refresh_telemetry()

        self._start_job("telemetry", _telemetry)

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

        self._updating_controls = True
        try:
            if specs.loop_mode is not None:
                self._loop_mode_label.setText(
                    f"Loop mode: {LOOP_MODE_LABELS.get(int(specs.loop_mode), specs.loop_mode)}"
                )

            apply_numeric_binding_double(
                self._regulation_power_spin,
                bindings.power,
                decimals=3,
            )
            self._power_unit_combo.setEnabled(bindings.power_unit.enabled)
            apply_select_binding(self._power_unit_combo, bindings.power_unit)

            apply_numeric_binding_double(
                self._regulation_current_spin,
                bindings.current,
                decimals=2,
            )

            self._tune_spin.setEnabled(bindings.tune.enabled)
            apply_numeric_binding_double(self._tune_spin, bindings.tune, decimals=4)

            self._modulation_combo.setEnabled(bindings.modulation.enabled)
            apply_select_binding(self._modulation_combo, bindings.modulation)

            self._tuning_domain_combo.blockSignals(True)
            for i in range(self._tuning_domain_combo.count()):
                if int(self._tuning_domain_combo.itemData(i)) == int(domain):
                    self._tuning_domain_combo.setCurrentIndex(i)
                    break
            self._tuning_domain_combo.blockSignals(False)

            self._tune_label.setText(tune_setpoint_label(domain))
            self._scan_start_label.setText(scan_bound_label("Scan start", domain))
            self._scan_stop_label.setText(scan_bound_label("Scan stop", domain))
            self._scan_speed_label.setText(scan_speed_label(domain))
            self._scan_step_label.setText(scan_step_label(domain))

            apply_numeric_binding_double(
                self._scan_start_spin,
                bindings.scan_start,
                decimals=4,
            )
            apply_numeric_binding_double(
                self._scan_stop_spin,
                bindings.scan_stop,
                decimals=4,
            )
            apply_numeric_binding_int(self._scan_speed_spin, bindings.scan_speed)
            apply_numeric_binding_int(self._scan_cycles_spin, bindings.scan_cycles)
            apply_numeric_binding_double(self._scan_dwell_spin, bindings.scan_dwell_ms, decimals=1)
            apply_numeric_binding_double(self._scan_step_spin, bindings.scan_step, decimals=4)

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
        try:
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
                self._cycles_completed_label.setText(
                    f"Cycles completed: {snap.scan_cycles_count}"
                )
        except Exception:
            return

    def _log(self, status: StatusMessage, action: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        prefix = "OK" if status.ok else "ERR"
        line = f"[{stamp}] {prefix} {action}: {status.summary}"
        if status.command:
            line += f" ({status.command})"
        current = self._status_area.toPlainText().strip()
        new_value = line if not current else f"{current}\n{line}"
        lines = new_value.splitlines()[-80:]
        self._status_area.setPlainText("\n".join(lines))


def create_laser_widget(parent: Optional[QWidget] = None) -> LaserControlWidget:
    """Factory used by both standalone app and Jupyter embedding."""
    ensure_qapp()
    return LaserControlWidget(parent=parent)
