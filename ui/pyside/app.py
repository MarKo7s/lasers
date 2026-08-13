"""Standalone PySide6 demo for the Laser control widget.

Run from the Laser project root::

    python -m ui.pyside.app

Or run this file directly (path bootstrap included).
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from PySide6.QtWidgets import QMainWindow

from ui.pyside.widget import create_laser_widget, ensure_qapp


def main() -> None:
    ensure_qapp()
    widget = create_laser_widget()
    window = QMainWindow()
    window.setWindowTitle("Laser Control (PySide6)")
    window.setCentralWidget(widget)
    window.resize(1100, 900)
    window.show()
    app = ensure_qapp()
    app.exec()


if __name__ == "__main__":
    main()
