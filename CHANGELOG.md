# Changelog

All notable changes to lasers are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [2.0.0] - 2026-09-17

### Added

- `LaserControlWidget(laser)` accepts an already-connected `TLB8800` and starts in the connected control state
- `TLB8800.is_open` and `TLB8800Controller.attach(..., owns_connection=...)`
- `LaserControlWidget.remotecontrol(True/False)` to lock setpoint cells during notebook control
- `LaserControlWidget.sync_gui_panel_to_laser()` to re-query the instrument into the panel
- Example notebook `tests/pyside_widget.ipynb` (empty widget vs discover + pass laser)

### Changed

- **Breaking:** installable import prefix is `laser.*` (`from laser.newfocus import TLB8800`, `from laser.ui.pyside import LaserControlWidget`). Pip name remains `lasers`.
- Top-level `ui`, `core`, `newfocus`, and `discovery` packages are no longer installed.
- Standalone apps: `python -m laser.ui.pyside.app` and `python -m laser.ui.nicegui.app`
- Widget **Disconnect** closes the serial port so Refresh can find the laser again
- Device menu shows a passed-in laser as connected; **Connect** is disabled while connected
- Status hint reads `Connected on COMx` after a successful connect

## [1.0.0] - 2026-08-13

### Added

- Pip packaging (`pyproject.toml`, `lasers` package, `scripts/release.py`)
- PySide6 twin control UI (`ui/pyside`) with background serial jobs and grouped panels
- NiceGUI / PySide: tuning domain toggle (wavelength nm / frequency THz)
- NiceGUI / PySide: “Set center wavelength” (mid of `wmin`/`wmax`)
- NiceGUI / PySide: “Check errors” (`errcnt?`, then `err?` if count > 0)
- Startup USB discovery scan in PySide (parity with NiceGUI)
- Quiet telemetry: successful polls no longer spam the status log

### Fixed

- PySide laser-output / interlock checkboxes always sent OFF (`int` vs `Qt.CheckState`)
- PySide “Set center wavelength” called `apply_tune` with positional `wait` (keyword-only)

### Changed

- Expanded tuning-domain related spec refresh fields
- Discovery can load `supported_models.json` from the `lasers` package data
- Added PySide6 to `requirements.txt` / `environment.yml`
