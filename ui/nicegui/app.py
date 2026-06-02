"""Standalone NiceGUI demo for TLB-8800 laser control.

Run from the Laser project root::

    python -m ui.nicegui.app
"""

from __future__ import annotations

import atexit
import sys
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from nicegui import app, ui

from ui.nicegui.widget import LaserControlWidget, create_laser_widget

_active_widget: Optional[LaserControlWidget] = None


@ui.page("/")
def main_page() -> None:
    global _active_widget
    _active_widget = create_laser_widget()


def _cleanup_laser_connection() -> None:
    global _active_widget
    if _active_widget is not None:
        _active_widget.shutdown()
        _active_widget = None


def main() -> None:
    atexit.register(_cleanup_laser_connection)
    app.on_shutdown(_cleanup_laser_connection)
    ui.run(
        title="Laser Control",
        reload=False,
        port=8080,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
