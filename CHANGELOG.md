# Changelog

All notable changes to lasers are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
