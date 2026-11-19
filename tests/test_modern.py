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
    assert w.trim_start.text() == "0.12"
    assert w.speed._buttons[3].isChecked()
    w.toggle_edit_playback()
    first = w._frame
    wait(app, lambda: w._frame != first)
    w._stop_edit_playback()
    destination = tmp_path / 'edited.gif'
    monkeypatch.setattr(ExportDialog, 'exec', lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(QFileDialog, 'exec', lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(QFileDialog, 'selectedFiles', lambda self: [str(destination)])
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

def test_frame_controls_at_150_percent(app, window, tmp_path, monkeypatch):
    w = window
    load(app, w, 'sample.gif')
    w.resize(800, 620)
    w.enter_editor()
    wait(app, lambda: len(w._frame_buttons) == len(w._loaded.frames))
    assert w.editor.width() == 336
    assert all(b.width() >= 70 for b in w.tool_buttons)
    assert all(b.text() == t for b, t in zip(w.tool_buttons, ('调整', '裁剪', '旋转')))
    assert w.frame_scroll.viewport().width() > 250
    assert w._frame_buttons[0].isChecked()
    w.seek_frame(2)
    assert w._frame_buttons[2].isChecked()
    w.edit_scope.setCurrentIndex(1)
    w.sliders['brightness'].setValue(25)
    assert w._frame_states[2].brightness == 25
    assert w._frame_states[1].brightness == 0
    w.undo_edit()
    assert w._frame_states[2].brightness == 0
    w.edit_scope.setCurrentIndex(0)
    w.sliders['contrast'].setValue(15)
    assert all(state.contrast == 15 for state in w._frame_states)
    w.delete_frame()
    assert len(w._edit_frames.frames) == len(w._loaded.frames) - 1
    insert = tmp_path / 'insert.png'
    from PIL import Image
    Image.new('RGBA', (48, 48), 'magenta').save(insert)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **k: (str(insert), ''))
    w.add_frame()
    assert len(w._edit_frames.frames) == len(w._loaded.frames)
    assert w._frame == 3
    single = tmp_path / 'single.png'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a, **k: (str(single), ''))
    w.export_frame()
    assert single.exists()

@pytest.mark.parametrize('source,fmt,suffix', [('sample.gif', 'GIF', 'gif'),
                                               ('sample.webp', '动画 WebP', 'webp')])
def test_frame_sequence_roundtrip(app, window, tmp_path, monkeypatch, source, fmt, suffix):
    w = window
    load(app, w, source)
    w.enter_editor()
    original_count = len(w._edit_frames.frames)
    w.seek_frame(0)
    w.delete_frame()
    insert = tmp_path / 'added.png'
    from PIL import Image
    Image.new('RGB', (44, 33), '#af3388').save(insert)
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', lambda *a, **kw: (str(insert), ''))
    w.add_frame()
    assert len(w._edit_frames.frames) == original_count
    destination = tmp_path / f'roundtrip.{suffix}'
    from lumenview import editing
    editing.export_image(w._edit_frames, w.history.state, str(destination), fmt,
                         frame_states=w._frame_states)
    reopened = decoders.load_image(str(destination))
    assert len(reopened.frames) == original_count
    assert reopened.loop == w._loaded.loop
    assert reopened.frames[1].image.pixelColor(reopened.width // 2, reopened.height // 2).red() > 120
