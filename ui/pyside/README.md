# PySide laser widget

Qt/PySide control panel bound to `laser.core` and `laser.newfocus.TLB8800`.

```python
from laser.ui.pyside import LaserControlWidget
from laser.newfocus import TLB8800

widget = LaserControlWidget()              # discovery + Connect
widget = LaserControlWidget(laser)         # already connected
```

- `DiscoveryService` — USB scan and device list
- `create_laser_controller(device)` — model-specific controller (TLB-8800 today)
- `laser.core.tlb8800.TLB8800Controller` — connect, attach, refresh, apply commands
- `bindings_from_specs()` — enable/disable fields and min/max bounds

Serial I/O runs on a background `QThread`. Numeric fields commit live (Enter, blur, or step arrows).

Standalone: `python -m laser.ui.pyside.app`

Jupyter: `tests/pyside_widget.ipynb` (`%gui qt`). Passing a notebook `TLB8800` shows it in the device menu as connected. **Disconnect** closes that session so Refresh can probe the port again.

After notebook `laser.set.*` calls:

```python
gui.remotecontrol(True)     # disable current / sweep / other cells
laser.set.current(80)
gui.sync_gui_panel_to_laser()
gui.remotecontrol(False)    # unlock and sync
```
