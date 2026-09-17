"""Standalone NiceGUI demo for TLB-8800 laser control.

Run from the Laser project root (editable install)::

    python -m laser.ui.nicegui.app
"""

from __future__ import annotations

import atexit
from typing import Optional

from nicegui import app, ui

from laser.ui.nicegui.widget import LaserControlWidget, create_laser_widget

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
