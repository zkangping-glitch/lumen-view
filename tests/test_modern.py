import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import time
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QDialog
from PySide6.QtTest import QTest
from lumenview import decoders, theme
from lumenview.modern import MainWindow, ExportDialog

@pytest.fixture(scope='module')
def app():
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    return app

def wait(app, predicate):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate(): return
        QTest.qWait(10)
    raise AssertionError('UI operation timed out')

@pytest.fixture
def window(app, monkeypatch):
    monkeypatch.setattr(QMessageBox, 'question', lambda *a, **kw: QMessageBox.StandardButton.Discard)
    w = MainWindow(); w.show()
    yield w
    w.cancel_editor(); w.close(); app.processEvents()

def load(app, w, name):
    path = str(Path('samples', name).resolve())
    w.load_path(path)
    wait(app, lambda: w._loaded is not None and w._loaded.path == path)

def test_edit_undo_gif_trim_export_and_cancel(app, window, tmp_path, monkeypatch):
    w = window
    load(app, w, 'sample.gif')
    source = Path(w._loaded.path).read_bytes()
    w.enter_editor()
    wait(app, lambda: w.canvas._loaded is not w._loaded)
    assert w.timeline.isVisible() and w.editor.isVisible()
    w.sliders['brightness'].setValue(20)
    w.ratio.setCurrentIndex(1)
    w.rotate(90)
    wait(app, lambda: w.canvas._loaded.width == w.canvas._loaded.height)
    assert w.history.state.brightness == 20
    assert w.history.state.rotation == 90
    w.undo_edit(); assert w.history.state.rotation == 0
    w.redo_edit(); assert w.history.state.rotation == 90
    w.trim_start.setValue(.12)
    w.trim_end.setValue(.48)
    w.speed.setCurrentIndex(3)
    assert w.history.state.start_ms == 120
    assert w.history.state.end_ms == 480
    assert w.history.state.speed == 2
    w.toggle_edit_playback()
    first = w._frame
    wait(app, lambda: w._frame != first)
    w._stop_edit_playback()
    destination = tmp_path / 'edited.gif'
    monkeypatch.setattr(ExportDialog, 'exec', lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, **kw: (str(destination), 'GIF'))
    messages = []
    monkeypatch.setattr(QMessageBox, 'information', lambda *a, **kw: messages.append(a))
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a, **kw: pytest.fail(str(a)))
    w.save_copy()
    wait(app, lambda: not w._exporting)
    output = decoders.load_image(str(destination))
    assert output.width == output.height
    assert len(output.frames) == 3
    assert sum(f.duration for f in output.frames) == 180
    assert Path(w._loaded.path).read_bytes() == source
    w.cancel_editor()
    assert not w.editor.isVisible() and not w.timeline.isVisible()
    assert w.canvas._loaded is w._loaded

def test_missing_path_and_pending_decode_rotation(app, window):
    w = window
    w.load_path('/does-not-exist.png')
    assert '文件不存在' in w.msg_title.text()
    load(app, w, 'sample.jpg')
    displayed = w._loaded.path
    w._current = 'pending.png'
    w.rotate(90)
    assert w._view_states[displayed][0] == 90
    assert 'pending.png' not in w._view_states

def test_dark_appearance_and_minimum_window(app, window):
    w = window
    theme.apply_theme(app, dark=True)
    w.resize(800, 620)
    app.processEvents()
    assert theme.BG == '#171819'
    assert w.save_button.geometry().right() < w.toolbar.width()
    theme.apply_theme(app, dark=False)
