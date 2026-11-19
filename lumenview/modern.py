"""Photo-first browsing and a reversible editor on the existing Qt viewer."""
from __future__ import annotations

import os
from dataclasses import fields, replace
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QRunnable, QSize, QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QDialog, QFileDialog, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSlider,
    QSizePolicy, QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from . import editing, icons, theme
from .decoders import Frame, Loaded, load_image
from .window import MainWindow as ViewerWindow


class SpeedSelector(QFrame):
    """Compact segmented speed control without native combo-box chrome."""

    currentIndexChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SegmentedControl")
        self.setAccessibleName("GIF 播放速度")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        self._values = (.5, 1, 1.5, 2)
        self._buttons = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for index, value in enumerate(self._values):
            item = QPushButton(f"{value:g}×", self)
            item.setObjectName("SegmentedButton")
            item.setCheckable(True)
            item.setAccessibleName(f"{value:g} 倍速")
            self._group.addButton(item, index)
            layout.addWidget(item)
            self._buttons.append(item)
        self._group.idClicked.connect(self._select)
        self._index = 1
        self._buttons[self._index].setChecked(True)

    def _select(self, index):
        if index != self._index:
            self._index = index
            self.currentIndexChanged.emit(index)

    def currentData(self):
        return self._values[self._index]

    def findData(self, value):
        try:
            return self._values.index(value)
        except ValueError:
            return -1

    def setCurrentIndex(self, index):
        if not 0 <= index < len(self._buttons):
            return
        changed = index != self._index
        self._index = index
        self._buttons[index].setChecked(True)
        if changed:
            self.currentIndexChanged.emit(index)


class TimeInput(QLineEdit):
    """Keyboard-first numeric field with no native stepper chrome."""

    valueChanged = Signal(float)

    def __init__(self, accessible_name, parent=None):
        super().__init__(parent)
        self.setObjectName("TimeInput")
        self.setAccessibleName(accessible_name)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._minimum = 0.0
        self._maximum = 0.0
        self._value = 0.0
        self.setText("0.00")
        self.editingFinished.connect(self._commit)

    def setRange(self, minimum, maximum):
        self._minimum, self._maximum = float(minimum), float(maximum)
        self.setValue(self._value)

    def setValue(self, value):
        value = max(self._minimum, min(self._maximum, float(value)))
        changed = value != self._value
        self._value = value
        self.setText(f"{value:.2f}")
        if changed:
            self.valueChanged.emit(value)

    def value(self):
        return self._value

    def _commit(self):
        try:
            value = float(self.text().strip().replace(",", "."))
        except ValueError:
            value = self._value
        self.setValue(value)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        QTimer.singleShot(0, self.selectAll)


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
        self.setObjectName("ExportDialog")
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
        self.name.setObjectName("ExportName")
        self.name.setAccessibleName("输出文件名")
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
        self._frame_states = []
        self._edit_frames = None
        self._frames_changed = False
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
        self.open_button = button("打开", self.open_file)
        layout.addWidget(self.open_button)
        layout.addStretch()
        self.file_label = QLabel("图片查看器")
        self.file_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.file_label.setMinimumWidth(40)
        self.file_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.file_label, 1)
        layout.addStretch()
        self.previous_button = button("❮", self.previous, self.canvas.viewport())
        self.next_button = button("❯", self.next, self.canvas.viewport())
        for nav, name in ((self.previous_button, "上一张"), (self.next_button, "下一张")):
            nav.setObjectName("CanvasNav")
            nav.setAccessibleName(name)
            nav.setToolTip(name)
            nav.setFixedSize(52, 72)
            nav.raise_()
        self.canvas.viewport().installEventFilter(self)
        self._position_navigation()
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

    def eventFilter(self, obj, event):
        if obj is self.canvas.viewport() and event.type() == QEvent.Type.Resize:
            self._position_navigation()
        return super().eventFilter(obj, event)

    def _position_navigation(self):
        if not hasattr(self, "previous_button"):
            return
        viewport = self.canvas.viewport()
        y = max(0, (viewport.height() - 72) // 2)
        self.previous_button.move(12, y)
        self.next_button.move(max(12, viewport.width() - 64), y)

    def _build_editor(self):
        self.editor = QScrollArea()
        self.editor.setObjectName("Editor")
        self.editor.setFixedWidth(336)
        self.editor.setWidgetResizable(True)
        self.editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        editor_content = QFrame()
        editor_content.setObjectName("EditorContent")
        layout = QVBoxLayout(editor_content)
        layout.setContentsMargins(22, 26, 22, 22)
        layout.setSpacing(24)
        title = QLabel("编辑图片")
        title.setObjectName("EditorTitle")
        layout.addWidget(title)
        self.scope = QLabel("所有编辑保存到副本")
        self.scope.setObjectName("Hint")
        layout.addWidget(self.scope)
        self.edit_scope = QComboBox()
        self.edit_scope.addItems(["作用于全部帧", "仅当前帧"])
        self.edit_scope.setAccessibleName("调整作用范围")
        layout.addWidget(self.edit_scope)
        tools = QHBoxLayout()
        self.tool_buttons = []
        self.panels = QStackedWidget()
        for i, text in enumerate(("调整", "裁剪", "旋转")):
            b = button(text, lambda checked=False, index=i: self._select_tool(index))
            b.setCheckable(True)
            b.setMinimumWidth(74)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
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
        self.editor.setWidget(editor_content)
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
        self.speed = SpeedSelector()
        self.speed.currentIndexChanged.connect(lambda _: self.change_edit(speed=self.speed.currentData()))
        row.addWidget(self.speed)
        layout.addLayout(row)
        self.frame_scroll = QScrollArea()
        self.frame_scroll.setWidgetResizable(True)
        self.frame_scroll.setFixedHeight(104)
        self.frame_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.frame_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.frame_strip = QWidget()
        self.thumb_row = QHBoxLayout(self.frame_strip)
        self.thumb_row.setContentsMargins(0, 4, 0, 4)
        self.thumb_row.setSpacing(8)
        self.frame_scroll.setWidget(self.frame_strip)
        layout.addWidget(self.frame_scroll)
        frame_actions = QHBoxLayout()
        frame_actions.addWidget(button("添加帧", self.add_frame))
        frame_actions.addWidget(button("删除当前帧", self.delete_frame))
        frame_actions.addWidget(button("导出当前帧", self.export_frame))
        frame_actions.addStretch()
        layout.addLayout(frame_actions)
        self.scrub = QSlider(Qt.Orientation.Horizontal)
        self.scrub.setAccessibleName("GIF 预览帧")
        self.scrub.valueChanged.connect(self.seek_frame)
        self.scrub.hide()
        layout.addWidget(self.scrub)
        trim = QHBoxLayout()
        trim.setSpacing(12)
        self.trim_start = TimeInput("片段起点")
        self.trim_end = TimeInput("片段终点")
        for name, spin in (("起点", self.trim_start), ("终点", self.trim_end)):
            field = QFrame()
            field.setObjectName("TimeField")
            field_layout = QVBoxLayout(field)
            field_layout.setContentsMargins(12, 8, 12, 8)
            field_layout.setSpacing(2)
            label = QLabel(name)
            label.setObjectName("TimeFieldLabel")
            field_layout.addWidget(label)
            value_row = QHBoxLayout()
            value_row.setSpacing(4)
            value_row.addWidget(spin, 1)
            unit = QLabel("秒")
            unit.setObjectName("TimeFieldUnit")
            value_row.addWidget(unit)
            field_layout.addLayout(value_row)
            trim.addWidget(field, 1)
        self.trim_start.valueChanged.connect(lambda v: self._trim_changed(True, v))
        self.trim_end.valueChanged.connect(lambda v: self._trim_changed(False, v))
        self.trim_panel = QWidget()
        self.trim_panel.setLayout(trim)
        self.trim_panel.hide()
        layout.addWidget(self.trim_panel)
        self.centralWidget().layout().insertWidget(2, self.timeline)
        self.timeline.hide()

    def _select_tool(self, index):
        self.panels.setCurrentIndex(index)
        for i, b in enumerate(self.tool_buttons):
            b.setChecked(i == index)

    def _refresh_frames(self):
        while self.thumb_row.count():
            item = self.thumb_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._frame_buttons = []
        self._thumb_next = 0
        for index in range(len(self._edit_frames.frames)):
            frame_button = button(str(index + 1), lambda checked=False, i=index: self.seek_frame(i))
            frame_button.setObjectName("FrameThumb")
            frame_button.setCheckable(True)
            frame_button.setAccessibleName(f"第 {index + 1} 帧")
            frame_button.setFixedSize(88, 80)
            frame_button.setIconSize(QSize(76, 52))
            self.thumb_row.addWidget(frame_button)
            self._frame_buttons.append(frame_button)
        self.thumb_row.addStretch()
        self.scrub.setRange(0, len(self._frame_buttons) - 1)
        self._highlight_frame()
        QTimer.singleShot(0, self._fill_frame_thumbnails)

    def _fill_frame_thumbnails(self):
        if not self._editing or not self._edit_frames:
            return
        end = min(self._thumb_next + 12, len(self._frame_buttons))
        for index in range(self._thumb_next, end):
            image = self._edit_frames.frames[index].image.scaled(
                76, 52, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            self._frame_buttons[index].setIcon(QIcon(QPixmap.fromImage(image)))
        self._thumb_next = end
        if end < len(self._frame_buttons):
            QTimer.singleShot(0, self._fill_frame_thumbnails)

    def _highlight_frame(self):
        for index, frame_button in enumerate(getattr(self, "_frame_buttons", [])):
            frame_button.setChecked(index == self._frame)
        if getattr(self, "_frame_buttons", None):
            self.frame_scroll.ensureWidgetVisible(self._frame_buttons[self._frame], 12, 0)

    def add_frame(self):
        if not self._editing or not self._edit_frames:
            return
        path, _ = QFileDialog.getOpenFileName(self, "插入图片帧", str(Path(self._loaded.path).parent))
        if not path:
            return
        try:
            image = load_image(path).first
        except Exception as exc:
            QMessageBox.warning(self, "添加帧失败", str(exc))
            return
        position = self._frame + 1
        duration = self._edit_frames.frames[self._frame].duration or 100
        self._edit_frames.frames.insert(position, Frame(image, duration))
        self._frame_states.insert(position, editing.EditState())
        self._frames_changed = True
        self._frame = position
        self.history = editing.History()
        self._refresh_frames()
        self._sync_edit_controls()
        self._request_preview()

    def delete_frame(self):
        if not self._editing or not self._edit_frames:
            return
        if len(self._edit_frames.frames) <= 1:
            QMessageBox.information(self, "保留一帧", "动画至少需要保留一帧。")
            return
        self._edit_frames.frames.pop(self._frame)
        self._frame_states.pop(self._frame)
        self._frame = min(self._frame, len(self._edit_frames.frames) - 1)
        self.history = editing.History()
        self.history.state = self._frame_states[self._frame]
        self._frames_changed = True
        self._refresh_frames()
        self._sync_edit_controls()
        self._request_preview()

    def export_frame(self):
        if not self._editing or not self._edit_frames:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出当前帧", str(Path(self._loaded.path).with_name(
                f"{Path(self._loaded.path).stem}-帧{self._frame + 1}.png")), "PNG (*.png)",
            options=QFileDialog.Option.DontUseNativeDialog)
        if path:
            try:
                editing.export_image(self._edit_frames, self._frame_states[self._frame],
                                     path if path.lower().endswith('.png') else path + '.png',
                                     "PNG", frame_index=self._frame)
            except Exception as exc:
                QMessageBox.warning(self, "导出帧失败", str(exc))

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
        self._frames_changed = False
        self._edit_frames = None
        self._frame_states = []
        self._rail_was_visible = self._filmstrip.isVisible()
        self._filmstrip.hide()
        self.editor.show()
        self.canvas._stop_animation()
        self.timeline.setVisible(self._loaded.animated)
        self.edit_scope.setVisible(self._loaded.animated)
        if self._loaded.animated:
            self._edit_frames = Loaded(self._loaded.path, list(self._loaded.frames), self._loaded.fmt,
                                       self._loaded.width, self._loaded.height, loop=self._loaded.loop)
            self._frame_states = [self.history.state for _ in self._edit_frames.frames]
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
            self._refresh_frames()
        self.scope.setText("逐帧编辑 · 可选择作用范围" if self._loaded.animated else "原图保留 · 保存副本")
        self._sync_edit_controls()
        self._update_actions()
        self._request_preview()

    def change_edit(self, **changes):
        if not self._editing:
            return
        self._stop_edit_playback()
        self.history.set(**changes)
        if self._edit_frames:
            if self.edit_scope.currentIndex() == 0:
                self._frame_states = [replace(s, **changes) for s in self._frame_states]
            else:
                self._frame_states[self._frame] = self.history.state
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
            before = self.history.state
            self.history.undo()
            self._sync_frame_state_change(before)
            self._sync_edit_controls()
            self._request_preview()

    def redo_edit(self):
        if self._editing:
            self._stop_edit_playback()
            before = self.history.state
            self.history.redo()
            self._sync_frame_state_change(before)
            self._sync_edit_controls()
            self._request_preview()

    def _sync_frame_state_change(self, before):
        if not self._edit_frames or before == self.history.state:
            return
        changed = {item.name: getattr(self.history.state, item.name)
                   for item in fields(editing.EditState)
                   if getattr(before, item.name) != getattr(self.history.state, item.name)}
        if self.edit_scope.currentIndex() == 0:
            self._frame_states = [replace(state, **changed) for state in self._frame_states]
        else:
            self._frame_states[self._frame] = self.history.state

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
        loaded, state, index = self._edit_frames or self._loaded, self.history.state, self._frame
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
            timing = dict(editing.selected_frames(self._edit_frames or self._loaded, self.history.state))
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
            if self._edit_frames:
                self.history.state = self._frame_states[index]
                self.history.undo_stack.clear()
                self.history.redo_stack.clear()
                self._sync_edit_controls()
                self._highlight_frame()
            self._request_preview()

    def _update_edit_time(self):
        frames = (self._edit_frames or self._loaded).frames
        elapsed = sum(max(20, f.duration or 100) for f in frames[:self._frame]) / 1000
        self.time_label.setText(f"第 {self._frame + 1} / {len(frames)} 帧 · {elapsed:.2f} 秒")
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
        indices = [i for i, _ in editing.selected_frames(self._edit_frames or self._loaded, self.history.state)]
        self._frame = indices[(indices.index(self._frame) + 1) % len(indices)] if self._frame in indices else indices[0]
        if self._edit_frames:
            self.history.state = self._frame_states[self._frame]
            self._sync_edit_controls()
            self._highlight_frame()
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
        self._edit_frames = None
        self._frame_states = []
        self._update_actions()

    def _leave_editor(self):
        if not self._editing:
            return True
        if self.history.state != self._edit_baseline or self._frames_changed or any(s != self._edit_baseline for s in self._frame_states):
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
        self.previous_button.setVisible(not self._editing and ready)
        self.next_button.setVisible(not self._editing and ready)
        self.previous_button.setEnabled(self.act_prev.isEnabled())
        self.next_button.setEnabled(self.act_next.isEnabled())
        name = Path(self._current).name if self._current else "图片查看器"
        self.file_label.setText(self.file_label.fontMetrics().elidedText(name, Qt.TextElideMode.ElideMiddle, max(80, self.file_label.width())))
        self.file_label.setToolTip(name)

    def save_copy(self):
        if not self._loaded or self._loaded.path != self._current or self._exporting:
            return
        self._stop_edit_playback()
        loaded = self._edit_frames or self._loaded
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
        if Path(name).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            name = Path(name).stem
        if not name:
            QMessageBox.warning(self, "文件名无效", "请输入文件名。")
            return
        start_dir = getattr(self, "_last_save_dir", None) or str(Path(loaded.path).parent)
        folder = QFileDialog.getExistingDirectory(self, "选择保存文件夹", start_dir)
        if not folder:
            return
        destination = str(Path(folder) / f"{name}.{ext}")
        if Path(destination).exists() and QMessageBox.question(
                self, "替换副本？", f"{Path(destination).name} 已存在，是否替换？") != QMessageBox.StandardButton.Yes:
            return
        index = 0 if dialog.frame.currentIndex() == 1 else dialog.index
        quality = dialog.quality.value()
        background = "white" if dialog.background.currentIndex() == 0 else "black"
        self._exporting = True
        self.save_button.setText("正在保存…")
        self._update_actions()
        def save():
            editing.export_image(loaded, state, destination, fmt, quality, index, background,
                                 self._frame_states if self._edit_frames else None)
            return destination
        self._export_pool.start(Work(0, self._export_signals, save))

    def _export_done(self, _token, path, error):
        self._exporting = False
        self._update_actions()
        if error:
            QMessageBox.warning(self, "保存失败", error)
        else:
            self._last_save_dir = str(Path(path).parent)
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
