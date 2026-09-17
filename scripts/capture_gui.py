#!/usr/bin/env python3
"""Grab a discovery-mode PySide GUI screenshot for README (docs/images/gui.png).

Does not open a laser; the widget stays on USB discovery.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DEFAULT = REPO_ROOT / "docs" / "images" / "gui.png"


def build_window():
    from PySide6.QtWidgets import QMainWindow

    from laser.ui.pyside.widget import create_laser_widget, ensure_qapp

    ensure_qapp()
    widget = create_laser_widget()
    window = QMainWindow()
    window.setWindowTitle("Laser Control (PySide6)")
    window.setCentralWidget(widget)
    window.resize(1100, 900)
    window.show()

    def teardown() -> None:
        widget.shutdown()
        window.close()

    return window, teardown


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture GUI screenshot for README.")
    parser.add_argument("-o", "--output", type=Path, default=OUT_DEFAULT)
    parser.add_argument("--wait-ms", type=int, default=4000)
    parser.add_argument(
        "--offscreen",
        action="store_true",
        help="Use QT_QPA_PLATFORM=offscreen.",
    )
    args = parser.parse_args()

    if args.offscreen:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    window, teardown = build_window()
    window.show()
    window.raise_()
    window.activateWindow()

    deadline = time.perf_counter() + max(args.wait_ms, 200) / 1000.0
    while time.perf_counter() < deadline:
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    pix = window.grab()
    if pix.isNull() or pix.width() < 10:
        teardown()
        raise SystemExit("grab() returned an empty pixmap")
    if not pix.save(str(args.output), "PNG"):
        teardown()
        raise SystemExit(f"Failed to write {args.output}")

    teardown()
    print(f"Wrote {args.output}")
    app.quit()


if __name__ == "__main__":
    main()
