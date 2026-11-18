"""Headless smoke test: decode every sample, then render the main window."""

from __future__ import annotations

import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lumenview import decoders, theme  # noqa: E402

SAMPLES = os.path.join(ROOT, "samples")


def check_decoders() -> int:
    files = sorted(
        os.path.join(SAMPLES, name)
        for name in os.listdir(SAMPLES)
        if decoders.is_supported(name) and not name.startswith("_")
    )
    print(f"{len(files)} sample(s) in {SAMPLES}")
    failures = 0
    for path in files:
        started = time.perf_counter()
        try:
            loaded = decoders.load_image(path)
        except Exception as exc:
            failures += 1
            print(f"  FAIL {os.path.basename(path):<18} {exc}")
            continue
        elapsed = (time.perf_counter() - started) * 1000
        image = loaded.first
        blank = image.pixelColor(image.width() // 2, image.height() // 2).alpha() == 0
        flag = "OK  " if not image.isNull() and not blank else "BLANK"
        if flag != "OK  ":
            failures += 1
        print(
            f"  {flag} {os.path.basename(path):<18} {loaded.fmt:<10} "
            f"{loaded.width}x{loaded.height}  {len(loaded.frames)}f  {elapsed:6.0f} ms"
        )
    return failures


def ui_smoke(app: QApplication) -> None:
    theme.apply_theme(app)

    from lumenview.window import MainWindow

    window = MainWindow()
    window.resize(1180, 760)
    window.show()

    sample = os.path.join(SAMPLES, "sample.jpg")
    if os.path.exists(sample):
        window.load_path(sample)

    def shot() -> None:
        out = os.path.join(ROOT, "build", "_ui.png")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        window.grab().save(out)
        print(f"screenshot: {out}")
        app.quit()

    QTimer.singleShot(1600, shot)
    app.exec()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    failures = check_decoders()
    ui_smoke(app)
    print("FAILURES:", failures)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

