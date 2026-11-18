"""Drive the real MainWindow headlessly: decode, navigate, animate, transform."""

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

from PySide6.QtWidgets import QApplication  # noqa: E402

from lumenview import theme  # noqa: E402
from lumenview.window import MainWindow  # noqa: E402

SAMPLES = os.path.join(ROOT, "samples")
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{(' — ' + detail) if detail else ''}")
    if not ok:
        failures.append(name)


def wait_until(app: QApplication, predicate, timeout: float = 8.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def main() -> int:
    app = QApplication(sys.argv)
    theme.apply_theme(app)
    window = MainWindow()
    window.resize(1200, 800)
    window.show()

    gif = os.path.join(SAMPLES, "sample.gif")
    window.load_path(gif)
    ok = wait_until(app, lambda: window._loaded is not None and window._loaded.path == gif)
    check("load animated GIF", ok)
    if ok:
        check("GIF reports animation", window._loaded.animated, f"{len(window._loaded.frames)} frames")
        first = window.canvas._frame_index
        wait_until(app, lambda: window.canvas._frame_index != first, 2.0)
        check("GIF frame advances", window.canvas._frame_index != first,
              f"frame {window.canvas._frame_index}")

    check("status shows dimensions", "320 × 220" in window.info_label.text(),
          window.info_label.text())
    check("count label", "/ 16" in window.count_label.text(), window.count_label.text())

    before = window._files.index(window._current)
    window.next()
    ok = wait_until(app, lambda: window._loaded is not None and window._index() == before + 1)
    check("navigate next", ok)
    window.previous()
    ok = wait_until(app, lambda: window._loaded is not None and window._index() == before)
    check("navigate previous", ok)

    for path in ("sample.psd", "sample.svg", "sample.heic", "sample.tiff"):
        window.load_path(os.path.join(SAMPLES, path))
        ok = wait_until(app, lambda p=path: window._loaded is not None and
                        os.path.basename(window._loaded.path) == p)
        check(f"open {path}", ok)

    window.rotate(90)
    check("rotate 90", window.canvas.view_state()[0] == 90)
    window.rotate(-90)
    window.flip()
    check("flip toggles", window.canvas.view_state()[1] is True)
    window.flip()

    window.actual_size()
    check("actual size = 100%", abs(window.canvas.current_scale() - 1.0) < 1e-6,
          f"{window.canvas.current_scale():.2f}")
    window.fit()
    check("fit produces valid scale", 0.02 <= window.canvas.current_scale() <= 4.0,
          f"{window.canvas.current_scale():.2f}")

    window.canvas.zoom_by(1.5)
    check("zoom in works", window.canvas.current_scale() > 1.0)
    window.canvas.zoom_by(1 / 1.5)

    rail_was_visible = window._filmstrip.isVisible()
    window._toggle_rail(False)
    check("rail hides", not window._filmstrip.isVisible())
    window._toggle_rail(True)
    check("rail returns", window._filmstrip.isVisible() == rail_was_visible)

    window.toggle_fullscreen()
    check("fullscreen on", window.isFullScreen() and not window.toolbar.isVisible())
    check("fullscreen hides footer", not window.footer.isVisible())
    window.toggle_fullscreen()
    check("fullscreen off", not window.isFullScreen() and window.toolbar.isVisible())
    check("footer returns", window.footer.isVisible())

    window.toggle_slideshow()
    check("slideshow starts", window._slideshow.isActive())
    window.stop_slideshow()
    check("slideshow stops", not window._slideshow.isActive())

    window.close()
    print("FAILURES:", len(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

