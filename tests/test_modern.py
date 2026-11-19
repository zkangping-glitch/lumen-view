import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import time
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QDialog
from PySide6.QtCore import QPoint, Qt
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
    w._select_tool(1)
    w._set_crop_ratio(2)
    w.finish_crop()
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
    destination = tmp_path / 'sample-已编辑.gif'
    monkeypatch.setattr(ExportDialog, 'exec', lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *a, **kw: str(tmp_path))
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

def test_canvas_navigation_zoom_and_save_location(app, window, tmp_path, monkeypatch):
    w = window
    load(app, w, 'sample.gif')
    assert w.previous_button.parentWidget() is w.canvas_area
    assert w.next_button.parentWidget() is w.canvas_area
    assert w.next_button.isVisible()
    before = w._current
    QTest.mouseClick(w.next_button, Qt.MouseButton.LeftButton)
    wait(app, lambda: w._current != before and w._loaded.path == w._current)
    w.canvas.zoom_in()
    assert w.canvas.current_scale() != 1
    QTest.mouseClick(w.zoom_label, Qt.MouseButton.LeftButton)
    assert w.canvas.current_scale() == pytest.approx(1)
    assert w.zoom_label.text() == '100%'
    folder = tmp_path / 'saved'
    folder.mkdir()
    monkeypatch.setattr(ExportDialog, 'exec', lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *a, **kw: str(folder))
    monkeypatch.setattr(QMessageBox, 'information', lambda *a, **kw: None)
    w.save_copy()
    wait(app, lambda: not w._exporting)
    assert (folder / (Path(w._current).stem + '-已编辑.jpg')).exists()
    assert w._last_save_dir == str(folder)

@pytest.mark.parametrize('label,suffix', [('PNG', 'png'), ('WebP', 'webp')])
def test_save_name_extension_follows_format(app, window, tmp_path, monkeypatch, label, suffix):
    w = window
    load(app, w, 'sample.jpg')
    def configure(dialog):
        dialog.name.setText('renamed.jpg')
        dialog.format.setCurrentText(label)
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(ExportDialog, 'exec', configure)
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *a, **kw: str(tmp_path))
    monkeypatch.setattr(QMessageBox, 'information', lambda *a, **kw: None)
    w.save_copy()
    wait(app, lambda: not w._exporting)
    assert (tmp_path / f'renamed.{suffix}').exists()
    assert not (tmp_path / f'renamed.jpg.{suffix}').exists()

def test_navigation_stays_at_view_edges_during_zoom(app, window):
    w = window
    load(app, w, 'sample.svg')
    def check():
        app.processEvents()
        rect = w.canvas.viewport().rect()
        left = w.canvas.viewport().mapTo(w.canvas_area, rect.topLeft()).x()
        right = w.canvas.viewport().mapTo(w.canvas_area, rect.topRight()).x()
        assert abs(w.previous_button.x() - (left + 12)) <= 2
        assert abs(w.next_button.geometry().right() - (right - 12)) <= 2
        assert w.previous_button.isVisible() and w.next_button.isVisible()
    check()
    w.actual_size(); check()
    w.canvas.zoom_by(2); check()
    w.fit(); check()
    w.resize(850, 700); check()
    w.showMaximized(); check()

def test_crop_overlay_screen_mapping_and_frame_labels(app, window):
    w = window
    load(app, w, 'sample.gif')
    w.enter_editor()
    wait(app, lambda: w.canvas._loaded is not w._loaded)
    w._select_tool(1)
    wait(app, lambda: w.crop_overlay.isVisible() and w.crop_overlay.reference_size is not None)
    overlay = w.crop_overlay
    overlay.set_box((.2, .2, .7, .7))
    before = overlay.box
    w.canvas.actual_size()
    app.processEvents()
    assert overlay.box == before
    w.canvas.zoom_by(2)
    app.processEvents()
    assert overlay.box == before
    assert overlay._screen_rect().width() > 0
    assert [label.text() for label in w._frame_buttons] == [''] * 6
    assert [label.text() for label in w.frame_strip.findChildren(type(w._frame_labels[0])) if label.objectName() == 'FrameNumber'] == [str(n) for n in range(1, 7)]

def test_crop_drag_ratio_apply_undo_and_many_frame_labels(app, window):
    w = window
    load(app, w, 'sample.gif')
    w.enter_editor()
    wait(app, lambda: w.canvas._loaded is not w._loaded)
    w._select_tool(1)
    wait(app, lambda: w.crop_overlay.isVisible() and w.crop_overlay.reference_size is not None)
    overlay = w.crop_overlay
    overlay.set_box((.2, .2, .8, .8))
    rect = overlay._screen_rect()
    start = rect.center().toPoint()
    QTest.mousePress(overlay, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(overlay, start + QPoint(20, 8))
    QTest.mouseRelease(overlay, Qt.MouseButton.LeftButton, pos=start + QPoint(20, 8))
    assert overlay.box[0] > .2
    w._set_crop_ratio(2)
    x0, y0, x1, y1 = overlay.box
    assert ((x1 - x0) * 320) / ((y1 - y0) * 220) == pytest.approx(1)
    w.finish_crop()
    wait(app, lambda: w.canvas._loaded.width == w.canvas._loaded.height)
    assert w.history.state.crop_box is not None
    w.undo_edit()
    assert w.history.state.crop_box is None
    w._edit_frames.frames = w._edit_frames.frames[:1] * 101
    w._frame_states = w._frame_states[:1] * 101
    w._frame = 100
    w._refresh_frames()
    assert w.frame_strip.findChildren(type(w._frame_labels[0]), 'FrameNumber')[-1].text() == '101'
    assert w._frame_buttons[-1].isChecked()

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
