# PySide laser widget (planned)

A Qt/PySide control panel will mirror the NiceGUI layout and bind to the shared **`core`** package:

- `DiscoveryService` — USB scan and device list
- `create_laser_controller(device)` — pick a model-specific controller (TLB-8800 today)
- `core.tlb8800.TLB8800Controller` — connect, refresh, apply commands
- `bindings_from_specs()` — enable/disable fields and min/max bounds

Long-running serial I/O should run on a `QThread` (or `QRunnable`) with results delivered via signals, using the same `StatusMessage` type for the status log.

See `ui/nicegui/widget.py` for the reference UI sections and interaction rules (immediate toggles vs Apply buttons).
