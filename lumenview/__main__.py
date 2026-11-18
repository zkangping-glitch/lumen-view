"""Entry point: ``python -m lumenview [image-or-folder]``."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from . import icons, theme
from .modern import MainWindow


def main() -> int:
    QApplication.setApplicationName("Lumen View")
    QApplication.setApplicationDisplayName("Lumen View")
    QApplication.setOrganizationName("Lumen")
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    theme.apply_theme(app)
    app.setWindowIcon(icons.app_icon())

    window = MainWindow()
    window.show()

    files = [arg for arg in sys.argv[1:] if not arg.startswith("-")]
    if files:
        window.load_path(files[0])

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
