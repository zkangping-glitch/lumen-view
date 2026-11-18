"""Photo-first browsing and a reversible editor on the existing Qt viewer."""
from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSlider,
    QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from . import editing, icons, theme
from .decoders import Frame, Loaded
from .window import MainWindow as ViewerWindow


class WorkerSignals(QObject):
    done = Signal(int, object, str)


class Work(QRunnable):
    def __init__(self, token, signals, callback):
        super().__init__()
        self.token, self.signals, self.callback = token, signals, callback

    def run(self):
        try:
            result = self.callback()
        except Exception as exc:
            self.signals.done.emit(self.token, None, str(exc))
        else:
            self.signals.done.emit(self.token, result, "")


def button(text, callback, parent=None, primary=False):
    widget = QPushButton(text, parent)
    if primary:
        widget.setObjectName("Primary")
    widget.clicked.connect(callback)
    return widget


class ExportDialog(QDialog):
    def __init__(self, loaded, state, index, parent):
        super().__init__(parent)
        self.loaded, self.state, self.index = loaded, state, index
        self.setWindowTitle("保存副本")
        self.setMinimumWidth(380)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(20)
        title = QLabel("保存副本")
        title.setObjectName("EditorTitle")
        layout.addWidget(title)
        form = QFormLayout()
        form.setSpacing(16)
        self.name = QLineEdit(Path(loaded.path).stem + "-已编辑")
        form.addRow("文件名", self.name)
        self.format = QComboBox()
        self.format.addItems(["GIF", "动画 WebP", "JPEG", "PNG", "WebP"] if loaded.animated else ["JPEG", "PNG", "WebP"])
        form.addRow("格式", self.format)
        self.frame = QComboBox()
        self.frame.addItems(["当前预览帧", "第一帧"])
        form.addRow("导出画面", self.frame)
        self.quality = QSlider(Qt.Orientation.Horizontal)
        self.quality.setRange(10, 100)
        self.quality.setValue(90)
        self.quality.setAccessibleName("输出画质")
        self.quality_label = QLabel("画质 90%")
        self.quality.valueChanged.connect(lambda v: self.quality_label.setText(f"画质 {v}%"))
        form.addRow(self.quality_label, self.quality)
        self.background = QComboBox()
        self.background.addItems(["白色", "黑色"])
        form.addRow("透明区域填充", self.background)
        layout.addLayout(form)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setObjectName("Hint")
        layout.addWidget(self.note)
        row = QHBoxLayout()
        row.addWidget(button("返回", self.reject))
        row.addStretch()
        row.addWidget(button("选择位置并保存", self.accept, primary=True))
        layout.addLayout(row)
        self.form = form
        self.format.currentTextChanged.connect(self.update_options)
        self.update_options()

    def update_options(self):
        fmt = self.format.currentText()
        animated = fmt in {"GIF", "动画 WebP"}
        self.form.setRowVisible(self.frame, self.loaded.animated and not animated)
        self.form.setRowVisible(self.quality, fmt in {"JPEG", "WebP", "动画 WebP"})
        self.form.setRowVisible(self.background, fmt == "JPEG")
        if animated:
            selected = editing.selected_frames(self.loaded, self.state)
            seconds = sum(d for _, d in selected) / 1000
            self.note.setText(f"保留动画 · {seconds:.1f} 秒 · 保存为新文件\nGIF 使用 256 色，半透明区域会转为透明或不透明。" if fmt == "GIF" else f"保留动画 · {seconds:.1f} 秒 · 保存为新文件")
        else:
            self.note.setText("保存为静态图片，原图保留。" if self.loaded.animated else "所有编辑保存到副本，原图保留。")


class MainWindow(ViewerWindow):
    def __init__(self):
        self._editing = False
        self._exporting = False
        self.history = editing.History()
        self._preview_token = 0
        self._frame = 0
        self._comparing = False
        self._playing = False
        super().__init__()
        self.setMinimumSize(800, 620)
        self._preview_pool = QThreadPool(self)
        self._preview_pool.setMaxThreadCount(1)
        self._preview_signals = WorkerSignals(self)
        self._preview_signals.done.connect(self._preview_done)
        self._export_pool = QThreadPool(self)
        self._export_pool.setMaxThreadCount(1)
        self._export_signals = WorkerSignals(self)
        self._export_signals.done.connect(self._export_done)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(70)
        self._debounce.timeout.connect(self._request_preview)
        self._play_timer = QTimer(self)
        self._play_timer.setSingleShot(True)
        self._play_timer.timeout.connect(self._advance_edit_frame)
        self._build_editor()
        self._build_timeline()
        self._replace_topbar()
        self._filmstrip.hide()
        self._sync_footer_margin()
        QApplication.instance().styleHints().colorSchemeChanged.connect(self._appearance_changed)
        self._update_actions()

    def _appearance_changed(self, _scheme):
        theme.apply_theme(QApplication.instance())
        self.canvas.viewport().update()
        self._chrome_applied = False
        self._apply_window_chrome()

    def _replace_topbar(self):
        layout = self._bar_layout
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().hide()
        self.toolbar.setFixedHeight(76)
        layout.setContentsMargins(24, 12, 24, 12)
        brand = QLabel("Lumen")
        brand.setObjectName("Brand")
        layout.addWidget(brand)
        self.open_button = button("打开", self.open_file)
        layout.addWidget(self.open_button)
        layout.addStretch()
        self.file_label = QLabel("图片查看器")
        self.file_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.file_label.setMinimumWidth(40)
        self.file_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.file_label, 1)
        layout.addStretch()
        self.previous_button = button("上一张", self.previous)
        self.next_button = button("下一张", self.next)
        layout.addWidget(self.previous_button)
        layout.addWidget(self.next_button)
        self.edit_button = button("编辑", self.enter_editor, primary=True)
        self.save_button = button("另存为", self.save_copy)
        self.cancel_button = button("取消", self.cancel_editor)
        self.cancel_button.hide()
        layout.addWidget(self.cancel_button)
        layout.addWidget(self.edit_button)
        layout.addWidget(self.save_button)
        self.menu_button.show()
        self.menu_button.setIcon(QIcon())
        self.menu_button.setText("更多")
        self.menu_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.menu_button.setFixedSize(60, 38)
        layout.addWidget(self.menu_button)
        self._buttons = []
        for text, shortcut, callback in (("编辑图片", "Ctrl+E", self.enter_editor),
                                          ("保存副本", "Ctrl+Shift+S", self.save_copy),
                                          ("撤销", "Ctrl+Z", self.undo_edit),
                                          ("重做", "Ctrl+Shift+Z", self.redo_edit)):
            action = QAction(text, self)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(callback)
            self.addAction(action)

    def _build_editor(self):
        self.editor = QFrame()
        self.editor.setObjectName("Editor")
        self.editor.setFixedWidth(264)
        layout = QVBoxLayout(self.editor)
        layout.setContentsMargins(22, 26, 22, 22)
        layout.setSpacing(24)
        title = QLabel("编辑图片")
        title.setObjectName("EditorTitle")
        layout.addWidget(title)
        self.scope = QLabel("所有编辑保存到副本")
        self.scope.setObjectName("Hint")
        layout.addWidget(self.scope)
        tools = QHBoxLayout()
        self.tool_buttons = []
        self.panels = QStackedWidget()
        for i, text in enumerate(("调整", "裁剪", "旋转")):
            b = button(text, lambda checked=False, index=i: self._select_tool(index))
            b.setCheckable(True)
            tools.addWidget(b)
            self.tool_buttons.append(b)
        layout.addLayout(tools)
        adjust = QWidget()
        controls = QVBoxLayout(adjust)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(24)
        self.sliders, self.values = {}, {}
        for key, name, minimum in (("brightness", "亮度", -50), ("contrast", "对比度", -50), ("saturation", "饱和度", -100)):
            row = QHBoxLayout()
            row.addWidget(QLabel(name))
            row.addStretch()
            value = QLabel("0")
            value.setObjectName("Hint")
            row.addWidget(value)
            controls.addLayout(row)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(minimum, -minimum)
            slider.setAccessibleName(name)
            slider.valueChanged.connect(lambda v, k=key: self.change_edit(**{k: v}))
            controls.addWidget(slider)
            self.sliders[key], self.values[key] = slider, value
        controls.addStretch()
        self.panels.addWidget(adjust)
        crop = QWidget()
        crops = QVBoxLayout(crop)
        crops.setContentsMargins(0, 0, 0, 0)
        crops.addWidget(QLabel("裁剪比例"))
        self.ratio = QComboBox()
        for name, value in (("原始比例", "original"), ("1 : 1", "square"), ("16 : 9", "wide"), ("4 : 5", "portrait")):
            self.ratio.addItem(name, value)
        self.ratio.currentIndexChanged.connect(lambda _: self.change_edit(ratio=self.ratio.currentData()))
        crops.addWidget(self.ratio)
        hint = QLabel("以画面中心裁剪，预览即导出范围")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        crops.addWidget(hint)
        crops.addStretch()
        self.panels.addWidget(crop)
        rotate = QWidget()
        turns = QVBoxLayout(rotate)
        turns.setContentsMargins(0, 0, 0, 0)
        turns.addWidget(button("向右旋转 90°", lambda: self.rotate(90)))
        turns.addWidget(button("水平翻转", self.flip))
        turns.addStretch()
        self.panels.addWidget(rotate)
        layout.addWidget(self.panels, 1)
        row = QHBoxLayout()
        self.undo_button = button("撤销", self.undo_edit)
        self.redo_button = button("重做", self.redo_edit)
        row.addWidget(self.undo_button)
        row.addWidget(self.redo_button)
        layout.addLayout(row)
        self.compare_button = button("按住查看原图", lambda: None)
        self.compare_button.pressed.connect(lambda: self.compare_original(True))
        self.compare_button.released.connect(lambda: self.compare_original(False))
        layout.addWidget(self.compare_button)
        self.stack.parentWidget().layout().addWidget(self.editor)
        self.editor.hide()
        self._select_tool(0)

    def _build_timeline(self):
        self.timeline = QWidget()
        self.timeline.setObjectName("Timeline")
        layout = QVBoxLayout(self.timeline)
        layout.setContentsMargins(24, 14, 24, 14)
        row = QHBoxLayout()
        self.play_button = button("播放", self.toggle_edit_playback)
        row.addWidget(self.play_button)
        self.time_label = QLabel()
        self.time_label.setObjectName("Hint")
        row.addWidget(self.time_label)
        row.addStretch()
        row.addWidget(QLabel("速度"))
        self.speed = QComboBox()
        for v in (.5, 1, 1.5, 2):
            self.speed.addItem(f"{v:g}×", v)
        self.speed.setCurrentIndex(1)
        self.speed.currentIndexChanged.connect(lambda _: self.change_edit(speed=self.speed.currentData()))
        row.addWidget(self.speed)
        row.addWidget(QLabel("调整应用于全部帧"))
        layout.addLayout(row)
        self.thumb_row = QHBoxLayout()
        layout.addLayout(self.thumb_row)
        self.scrub = QSlider(Qt.Orientation.Horizontal)
        self.scrub.setAccessibleName("GIF 预览帧")
        self.scrub.valueChanged.connect(self.seek_frame)
        layout.addWidget(self.scrub)
        trim = QHBoxLayout()
        self.trim_start, self.trim_end = QDoubleSpinBox(), QDoubleSpinBox()
        for name, spin in (("起点", self.trim_start), ("终点", self.trim_end)):
            trim.addWidget(QLabel(name))
            spin.setDecimals(2)
            spin.setSingleStep(.1)
            spin.setSuffix(" 秒")
            spin.setAccessibleName("片段" + name)
            trim.addWidget(spin)
        self.trim_start.valueChanged.connect(lambda v: self._trim_changed(True, v))
        self.trim_end.valueChanged.connect(lambda v: self._trim_changed(False, v))
        layout.addLayout(trim)
        self.centralWidget().layout().insertWidget(2, self.timeline)
        self.timeline.hide()

    def _select_tool(self, index):
        self.panels.setCurrentIndex(index)
        for i, b in enumerate(self.tool_buttons):
            b.setChecked(i == index)

    def enter_editor(self):
        if self._editing or not self._loaded or self._loaded.path != self._current or self._exporting:
            return
        if self.isFullScreen():
            self.toggle_fullscreen()
        self.stop_slideshow()
        self._editing = True
        self.history = editing.History()
        rotation, flipped = self._view_states.get(self._loaded.path, (0, False))
        self.history.state = editing.EditState(rotation=rotation, flipped=flipped)
        self._edit_baseline = self.history.state
        self._frame = 0
        self._rail_was_visible = self._filmstrip.isVisible()
        self._filmstrip.hide()
        self.editor.show()
        self.canvas._stop_animation()
        self.timeline.setVisible(self._loaded.animated)
        if self._loaded.animated:
            total = editing.duration_ms(self._loaded) / 1000
            for spin, value in ((self.trim_start, 0), (self.trim_end, total)):
                spin.blockSignals(True)
                spin.setRange(0, total)
                spin.setValue(value)
                spin.blockSignals(False)
            self.scrub.blockSignals(True)
            self.scrub.setRange(0, len(self._loaded.frames) - 1)
            self.scrub.setValue(0)
            self.scrub.blockSignals(False)
            while self.thumb_row.count():
                self.thumb_row.takeAt(0).widget().deleteLater()
            for n in range(min(8, len(self._loaded.frames))):
                index = round(n * (len(self._loaded.frames) - 1) / max(1, min(8, len(self._loaded.frames)) - 1))
                label = QLabel()
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setPixmap(QPixmap.fromImage(self._loaded.frames[index].image.scaled(92, 52, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)))
                self.thumb_row.addWidget(label)
        self.scope.setText("GIF · 全部帧统一编辑" if self._loaded.animated else "原图保留 · 保存副本")
        self._sync_edit_controls()
        self._update_actions()
        self._request_preview()

    def change_edit(self, **changes):
        if not self._editing:
            return
        self._stop_edit_playback()
        self.history.set(**changes)
        self._comparing = False
        self._preview_token += 1
        self._sync_edit_controls()
        self._debounce.start()

    def _sync_edit_controls(self):
        state = self.history.state
        for key, slider in self.sliders.items():
            slider.blockSignals(True)
            slider.setValue(getattr(state, key))
            slider.blockSignals(False)
            self.values[key].setText(f"{getattr(state, key):+d}")
        for combo, value in ((self.ratio, state.ratio), (self.speed, state.speed)):
            combo.blockSignals(True)
            combo.setCurrentIndex(combo.findData(value))
            combo.blockSignals(False)
        if self._loaded and self._loaded.animated:
            for spin, value in ((self.trim_start, state.start_ms / 1000), (self.trim_end, (state.end_ms if state.end_ms is not None else editing.duration_ms(self._loaded)) / 1000)):
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)
        self.undo_button.setEnabled(bool(self.history.undo_stack))
        self.redo_button.setEnabled(bool(self.history.redo_stack))

    def undo_edit(self):
        if self._editing:
            self._stop_edit_playback()
            self.history.undo()
            self._sync_edit_controls()
            self._request_preview()

    def redo_edit(self):
        if self._editing:
            self._stop_edit_playback()
            self.history.redo()
            self._sync_edit_controls()
            self._request_preview()

    def rotate(self, degrees):
        if self._editing:
            self.change_edit(rotation=(self.history.state.rotation + degrees) % 360)
        else:
            super().rotate(degrees)

    def flip(self):
        if self._editing:
            self.change_edit(flipped=not self.history.state.flipped)
        else:
            super().flip()

    def compare_original(self, original):
        if self._editing:
            self._stop_edit_playback()
            self._comparing = original
            self._request_preview()

    def _request_preview(self):
        if not self._editing or not self._loaded:
            return
        self._debounce.stop()
        self._preview_token += 1
        self._preview_pool.clear()
        loaded, state, index = self._loaded, self.history.state, self._frame
        if self._comparing:
            state = editing.EditState()
        self._preview_pool.start(Work(self._preview_token, self._preview_signals, lambda: editing.preview(loaded, state, index)))

    def _preview_done(self, token, image, error):
        if token != self._preview_token or not self._editing:
            return
        if error:
            self._stop_edit_playback()
            QMessageBox.warning(self, "编辑预览失败", error)
            return
        fit = self.canvas.is_fit_mode()
        old_transform = self.canvas.transform()
        self.canvas.set_loaded(Loaded(self._loaded.path, [Frame(image)], self._loaded.fmt, image.width(), image.height()))
        if not fit:
            self.canvas.setTransform(old_transform)
            self.canvas._fit_mode = False
        self.canvas._fade.stop()
        self.canvas._item.setOpacity(1)
        self._update_edit_time()
        if self._playing:
            timing = dict(editing.selected_frames(self._loaded, self.history.state))
            self._play_timer.start(timing.get(self._frame, 100))

    def _trim_changed(self, start, seconds):
        if not self._editing:
            return
        state = self.history.state
        end = state.end_ms if state.end_ms is not None else editing.duration_ms(self._loaded)
        value = round(seconds * 1000)
        if (start and value >= end) or (not start and value <= state.start_ms):
            self._sync_edit_controls()
            return
        self.change_edit(**({"start_ms": value} if start else {"end_ms": value}))
        self._frame = editing.selected_frames(self._loaded, self.history.state)[0][0]
        self._request_preview()

    def seek_frame(self, index):
        if self._editing:
            self._stop_edit_playback()
            self._frame = index
            self._request_preview()

    def _update_edit_time(self):
        elapsed = sum(max(20, f.duration or 100) for f in self._loaded.frames[:self._frame]) / 1000
        self.time_label.setText(f"{elapsed:.2f} 秒 · 第 {self._frame + 1} 帧")
        self.scrub.blockSignals(True)
        self.scrub.setValue(self._frame)
        self.scrub.blockSignals(False)

    def toggle_edit_playback(self):
        if self._playing:
            self._stop_edit_playback()
        elif self._editing and self._loaded.animated:
            self._playing = True
            self.play_button.setText("暂停")
            self._frame = editing.selected_frames(self._loaded, self.history.state)[0][0]
            self._request_preview()

    def _advance_edit_frame(self):
        indices = [i for i, _ in editing.selected_frames(self._loaded, self.history.state)]
        self._frame = indices[(indices.index(self._frame) + 1) % len(indices)] if self._frame in indices else indices[0]
        self._request_preview()

    def _stop_edit_playback(self):
        self._playing = False
        if hasattr(self, "_play_timer"):
            self._play_timer.stop()
            self.play_button.setText("播放")

    def cancel_editor(self):
        if not self._editing:
            return
        self._stop_edit_playback()
        self._debounce.stop()
        self._preview_token += 1
        self._preview_pool.clear()
        self._editing = False
        self._comparing = False
        self.editor.hide()
        self.timeline.hide()
        self._filmstrip.setVisible(self._rail_was_visible)
        self.canvas.set_loaded(self._loaded)
        rotation, flipped = self._view_states.get(self._loaded.path, (0, False))
        self.canvas.set_view_state(rotation, flipped)
        self.history = editing.History()
        self._update_actions()

    def _leave_editor(self):
        if not self._editing:
            return True
        if self.history.state != self._edit_baseline:
            answer = QMessageBox.question(self, "离开编辑？", "尚未保存的修改将被丢弃，原图不会改变。", QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
            if answer != QMessageBox.StandardButton.Discard:
                return False
        self.cancel_editor()
        return True

    def _load(self, path):
        if not self._leave_editor():
            return
        super()._load(path)
        self._update_actions()

    def load_path(self, path):
        if self._leave_editor():
            super().load_path(path)

    def _set_folder(self, files, current):
        if self._leave_editor():
            self._files = files
            self._filmstrip.set_files([])
            self._filmstrip.hide()
            self.act_rail.setChecked(False)
            self._sync_footer_margin()
            self._load(current)

    def _toggle_rail(self, visible=None):
        if self._editing:
            return
        show = not self._filmstrip.isVisible() if visible is None else visible
        if show and not self._filmstrip._items:
            self._filmstrip.set_files(self._files, self._current)
        super()._toggle_rail(show)

    def _update_actions(self):
        super()._update_actions()
        if not hasattr(self, "edit_button"):
            return
        ready = self._loaded is not None and self._loaded.path == self._current and not self._exporting
        self.edit_button.setVisible(not self._editing)
        self.cancel_button.setVisible(self._editing)
        self.save_button.setObjectName("Primary" if self._editing else "")
        self.save_button.style().unpolish(self.save_button)
        self.save_button.style().polish(self.save_button)
        self.edit_button.setEnabled(ready)
        self.save_button.setEnabled(ready)
        self.act_slideshow.setEnabled(ready and not self._editing)
        self.act_rail.setEnabled(bool(self._files) and not self._editing)
        self.save_button.setText("正在保存…" if self._exporting else ("保存副本" if self._editing else "另存为"))
        self.previous_button.setVisible(not self._editing)
        self.next_button.setVisible(not self._editing)
        self.previous_button.setEnabled(self.act_prev.isEnabled())
        self.next_button.setEnabled(self.act_next.isEnabled())
        name = Path(self._current).name if self._current else "图片查看器"
        self.file_label.setText(self.file_label.fontMetrics().elidedText(name, Qt.TextElideMode.ElideMiddle, max(80, self.file_label.width())))
        self.file_label.setToolTip(name)

    def save_copy(self):
        if not self._loaded or self._loaded.path != self._current or self._exporting:
            return
        self._stop_edit_playback()
        loaded = self._loaded
        rotation, flipped = self._view_states.get(loaded.path, (0, False))
        state = self.history.state if self._editing else editing.EditState(rotation=rotation, flipped=flipped)
        dialog = ExportDialog(loaded, state, self._frame if self._editing else self.canvas._frame_index, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name = dialog.name.text().strip()
        if not name or Path(name).name != name or any(c in name for c in '<>:"/\\|?*'):
            QMessageBox.warning(self, "文件名无效", "请输入不含路径和特殊字符的文件名。")
            return
        fmt = dialog.format.currentText()
        ext = {"JPEG": "jpg", "PNG": "png", "WebP": "webp", "GIF": "gif", "动画 WebP": "webp"}[fmt]
        destination, _ = QFileDialog.getSaveFileName(self, "保存副本", str(Path(loaded.path).parent / f"{name}.{ext}"), f"{fmt} (*.{ext})")
        if not destination:
            return
        if Path(destination).suffix.lower() != f".{ext}":
            destination += f".{ext}"
            if Path(destination).exists() and QMessageBox.question(self, "替换副本？", f"{Path(destination).name} 已存在，是否替换？") != QMessageBox.StandardButton.Yes:
                return
        index = 0 if dialog.frame.currentIndex() == 1 else dialog.index
        quality = dialog.quality.value()
        background = "white" if dialog.background.currentIndex() == 0 else "black"
        self._exporting = True
        self.save_button.setText("正在保存…")
        self._update_actions()
        def save():
            editing.export_image(loaded, state, destination, fmt, quality, index, background)
            return destination
        self._export_pool.start(Work(0, self._export_signals, save))

    def _export_done(self, _token, path, error):
        self._exporting = False
        self._update_actions()
        if error:
            QMessageBox.warning(self, "保存失败", error)
        else:
            QMessageBox.information(self, "副本已保存", f"已保存到：\n{path}\n\n原图保留。")

    def toggle_fullscreen(self):
        if self._editing:
            return
        super().toggle_fullscreen()

    def copy_image(self):
        if self._editing:
            QApplication.clipboard().setImage(self.canvas._loaded.first)
        else:
            super().copy_image()

    def closeEvent(self, event):
        if self._exporting:
            QMessageBox.information(self, "正在保存", "请等待副本保存完成后再关闭。")
            event.ignore()
            return
        if not self._leave_editor():
            event.ignore()
            return
        self._preview_pool.clear()
        self._preview_pool.waitForDone()
        super().closeEvent(event)
