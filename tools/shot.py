"""Open the window on the desktop, grab a screenshot, quit.

Usage: python tools/shot.py [image-or-folder] [out.png] [--fullscreen]
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from lumenview import theme
from lumenview.window import MainWindow


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    fullscreen = "--fullscreen" in sys.argv

    app = QApplication(sys.argv)
    theme.apply_theme(app)
    window = MainWindow()
    window.resize(1280, 800)
    window.show()

    target = args[0] if args else os.path.join(ROOT, "samples", "sample.jpg")
    if target:
        window.load_path(target)

    out = args[1] if len(args) > 1 else os.path.join(ROOT, "build", "_ui_live.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    if fullscreen:
        window.toggle_fullscreen()

    def grab() -> None:
        window.grab().save(out)
        print("saved", out)
        app.quit()

    QTimer.singleShot(1400, grab)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
