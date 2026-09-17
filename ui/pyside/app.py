"""Standalone PySide6 demo for the Laser control widget.

Run from the Laser project root (editable install)::

    python -m laser.ui.pyside.app
"""

from __future__ import annotations

from PySide6.QtWidgets import QMainWindow

from laser.ui.pyside.widget import create_laser_widget, ensure_qapp


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
