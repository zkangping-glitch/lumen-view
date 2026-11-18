"""Render the app icon to build/LumenView.ico (used by the C# launcher)."""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from PIL import Image  # noqa: E402

from lumenview import icons  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    pm = icons.app_icon().pixmap(QSize(256, 256))
    build = os.path.join(ROOT, "build")
    os.makedirs(build, exist_ok=True)
    png = os.path.join(build, "LumenView.png")
    pm.save(png)

    img = Image.open(png).convert("RGBA")
    ico = os.path.join(ROOT, "LumenView.ico")
    img.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", ico)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


