"""PySide6 widgets for the Laser package.

This subpackage is intended to be independent from the NiceGUI implementation.
"""

from laser.ui.pyside.jupyter_launch import embed_in_notebook
from laser.ui.pyside.widget import LaserControlWidget, create_laser_widget, ensure_qapp

__all__ = [
    "LaserControlWidget",
    "create_laser_widget",
    "embed_in_notebook",
    "ensure_qapp",
]
