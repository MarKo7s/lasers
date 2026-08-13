"""Jupyter-safe launcher helpers for the PySide6 twin widget.

Jupyter Qt integration depends on your notebook environment.
Typical setups:
  - use `%gui qt` (qtconsole / IPython magic) before embedding
  - or use a Qt-enabled Jupyter kernel
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt

from ui.pyside.widget import create_laser_widget, ensure_qapp


def embed_in_notebook(parent=None):
    """Create and return the widget; also attempts to display it in Jupyter."""
    ensure_qapp()
    widget = create_laser_widget(parent=parent)
    try:
        widget.setWindowFlag(Qt.Window, False)
    except Exception:
        pass

    # If running under IPython/Jupyter, try to display the widget.
    try:  # pragma: no cover (depends on environment)
        from IPython.display import display

        display(widget)
    except Exception:
        pass

    return widget

