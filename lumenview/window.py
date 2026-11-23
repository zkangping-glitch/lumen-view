"""Lumen View main window: quiet chrome, warm light, the photo first."""

from __future__ import annotations

import os
import re

from PySide6.QtCore import (
    QObject, QRunnable, QSettings, QSize, Qt, QThreadPool, QTimer, Signal,
)
from PySide6.QtGui import QAction, QFont, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox,
    QPushButton, QSizePolicy, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from . import decoders, icons, theme
from .canvas import ImageCanvas
from .decoders import DecodeError, Loaded
from .filmstrip import Filmstrip


class _FilenameLabel(QLabel):
    """Keep the full name accessible without letting it widen the window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._full_text = ""
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)

    def setText(self, text):
        self._full_text = text
        self.setToolTip(text)
        self.setAccessibleName(text)
        self._refresh()

    def _refresh(self):
        super().setText(self.fontMetrics().elidedText(
            self._full_text, Qt.TextElideMode.ElideMiddle, self.contentsRect().width()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh()


class _DecodeSignals(QObject):
    loaded = Signal(int, str, object)
    failed = Signal(int, str, str)


class _DecodeTask(QRunnable):
    def __init__(self, token: int, path: str, signals: _DecodeSignals) -> None:
        super().__init__()
        self.token = token
        self.path = path
        self.signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            loaded = decoders.load_image(self.path)
        except DecodeError as exc:
            self.signals.failed.emit(self.token, self.path, str(exc))
        except Exception as exc:  # unexpected decoder bug
            self.signals.failed.emit(self.token, self.path, f"解码时发生意外错误：{exc}")
        else:
            self.signals.loaded.emit(self.token, self.path, loaded)


def _natural_key(name: str):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Lumen View")
        self.setMinimumSize(960, 640)
        self.setAcceptDrops(True)

        self._settings = QSettings("Lumen", "LumenView")
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(2)
        self._signals = _DecodeSignals(self)
        self._signals.loaded.connect(self._on_decoded)
        self._signals.failed.connect(self._on_decode_failed)

        self._token = 0
        self._loaded: Loaded | None = None
        self._files: list[str] = []
        self._current = ""
        self._view_states: dict[str, tuple[int, bool]] = {}
        self._chrome_applied = False
        self._rail_was_visible = True

        self._slideshow = QTimer(self)
        self._slideshow.setInterval(3000)
        self._slideshow.timeout.connect(self._slideshow_next)

        self._build_ui()
        self._filmstrip.hide()
        self._build_actions()
        self._restore_settings()
        self.show_empty_state()
        self._update_actions()
        self.setWindowIcon(icons.app_icon())

    # ------------------------------------------------------------------ #
    # ui construction
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        root = QWidget(self)
        root.setObjectName("Root")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.toolbar = self._build_topbar(root)
        outer.addWidget(self.toolbar)

        self.canvas_area = QWidget(root)
        self.canvas_area.setObjectName("CanvasArea")
        area_layout = QVBoxLayout(self.canvas_area)
        area_layout.setContentsMargins(14, 2, 14, 14)
        area_layout.setSpacing(0)

        row = QWidget(self.canvas_area)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(14)

        self._filmstrip = Filmstrip(row)
        self._filmstrip.fileActivated.connect(self._on_filmstrip_clicked)
        row_layout.addWidget(self._filmstrip)

        self.stack = QStackedWidget(row)
        self.canvas = ImageCanvas(self.stack)
        self.canvas.zoomChanged.connect(self._on_zoom_changed)
        self.canvas.doubleClicked.connect(self._toggle_fit)

        self.message_page = QWidget(self.stack)
        self._build_message_page()
        self.stack.addWidget(self.canvas)
        self.stack.addWidget(self.message_page)
        row_layout.addWidget(self.stack, 1)

        area_layout.addWidget(row, 1)

        self.footer = self._build_footer(self.canvas_area)
        area_layout.addWidget(self.footer)

        outer.addWidget(self.canvas_area, 1)
        self.setCentralWidget(root)

        self.canvas.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.canvas.customContextMenuRequested.connect(self._canvas_menu)

    def _build_topbar(self, parent: QWidget) -> QWidget:
        bar = QWidget(parent)
        bar.setObjectName("TopBar")
        bar.setFixedHeight(58)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 6, 14, 4)
        layout.setSpacing(6)

        dot = QLabel(bar)
        dot.setPixmap(icons.accent_dot(9))
        dot.setFixedSize(11, 11)

        brand = QLabel("LUMEN VIEW", bar)
        brand.setObjectName("Brand")
        brand_font = QFont(brand.font())
        brand_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3.4)
        brand.setFont(brand_font)

        layout.addWidget(dot)
        layout.addSpacing(2)
        layout.addWidget(brand)
        layout.addSpacing(8)

        self._brand_badge = QLabel("图片查看器", bar)
        self._brand_badge.setObjectName("BrandSub")
        self._brand_badge.setVisible(False)
        layout.addWidget(self._brand_badge)
        layout.addStretch(1)
        self._bar_layout = layout
        return bar

    def _build_message_page(self) -> None:
        page = self.message_page
        page.setObjectName("MessagePage")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(48, 36, 48, 48)
        outer.addStretch(1)

        self._msg_icon = QLabel(page)
        self._msg_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._msg_icon.setPixmap(icons.app_icon().pixmap(84, 84))

        self._msg_brand = QLabel("LUMEN VIEW", page)
        self._msg_brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_font = QFont(self._msg_brand.font())
        brand_font.setPointSizeF(17)
        brand_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 7)
        self._msg_brand.setFont(brand_font)
        self._msg_brand.setStyleSheet(f"color: {theme.TEXT};")
        self._msg_brand.setVisible(False)

        self.msg_title = QLabel("", page)
        self.msg_title.setObjectName("ErrorTitle")
        self.msg_title.setWordWrap(True)
        self.msg_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.msg_detail = QLabel("", page)
        self.msg_detail.setObjectName("Hint")
        self.msg_detail.setWordWrap(True)
        self.msg_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.msg_detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.msg_buttons = QHBoxLayout()
        self.msg_buttons.setSpacing(10)
        self.msg_buttons.addStretch(1)
        self.msg_buttons.addStretch(1)

        outer.addWidget(self._msg_icon)
        outer.addSpacing(20)
        outer.addWidget(self._msg_brand)
        outer.addWidget(self.msg_title)
        outer.addSpacing(10)
        outer.addWidget(self.msg_detail)
        outer.addSpacing(24)
        outer.addLayout(self.msg_buttons)
        outer.addStretch(2)

    def _build_footer(self, parent: QWidget) -> QWidget:
        footer = QWidget(parent)
        footer.setObjectName("Footer")
        footer.setMinimumHeight(52)

        layout = QVBoxLayout(footer)
        layout.setContentsMargins(240, 6, 6, 6)
        layout.setSpacing(4)

        self.name_label = _FilenameLabel(footer)
        self.name_label.setObjectName("PillName")
        self.info_label = QLabel("", footer)
        self.info_label.setObjectName("PillMeta")
        self.count_label = QLabel("", footer)
        self.count_label.setObjectName("PillMeta")
        self.zoom_label = QPushButton("", footer)
        self.zoom_label.setObjectName("Zoom")
        self.zoom_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.zoom_label.setToolTip("点击恢复到 100% 实际大小")
        self.zoom_label.setAccessibleName("恢复到 100% 实际大小")
        self.zoom_label.clicked.connect(self.actual_size)

        self._dot_b = QLabel("·", footer)
        self._dot_b.setObjectName("PillMeta")

        layout.addWidget(self.name_label)
        metadata = QHBoxLayout()
        metadata.setSpacing(8)
        metadata.addWidget(self.info_label)
        metadata.addWidget(self._dot_b)
        metadata.addWidget(self.count_label)
        metadata.addStretch(1)
        metadata.addWidget(self.zoom_label)
        layout.addLayout(metadata)
        footer.hide()
        return footer

    def _build_actions(self) -> None:
        self._buttons: list[QToolButton] = []

        def act(name: str, text: str, shortcut: str | None, slot, checkable=False) -> QAction:
            action = QAction(icons.icon(name), text, self)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            action.setToolTip(f"{text}  {shortcut}" if shortcut else text)
            action.triggered.connect(slot)
            action.setCheckable(checkable)
            self.addAction(action)
            return action

        def button(action: QAction, color: str | None = None) -> QToolButton:
            btn = QToolButton(self.toolbar)
            btn.setDefaultAction(action)
            btn.setFixedSize(34, 34)
            btn.setIconSize(QSize(20, 20))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            self._bar_layout.addWidget(btn)
            self._buttons.append(btn)
            return btn

        def gap(width: int = 6) -> None:
            self._bar_layout.addSpacing(width)

        self.act_open = act("image", "打开图片", "Ctrl+O", self.open_file)
        self.act_folder = act("open", "打开文件夹", "Ctrl+Shift+O", self.open_folder)
        button(self.act_open)
        button(self.act_folder)
        gap(10)

        self.act_prev = act("prev", "上一张", "Left", self.previous)
        self.act_next = act("next", "下一张", "Right", self.next)
        button(self.act_prev)
        button(self.act_next)
        gap(10)

        self.act_zoom_out = act("zoom_out", "缩小", None, self.canvas.zoom_out)
        self.act_zoom_out.setShortcuts([QKeySequence("Ctrl+-"), QKeySequence("Ctrl+_")])
        self.act_fit = act("fit", "适应窗口", "0", self.fit)
        self.act_zoom_in = act("zoom_in", "放大", None, self.canvas.zoom_in)
        self.act_zoom_in.setShortcuts([QKeySequence("Ctrl+="), QKeySequence("Ctrl++")])
        self.act_actual = act("actual", "实际大小", "1", self.actual_size)
        for action in (self.act_zoom_out, self.act_fit, self.act_zoom_in, self.act_actual):
            button(action)
        gap(10)

        self.act_slideshow = act("play", "幻灯片", "F5", self.toggle_slideshow, checkable=True)
        self.act_fullscreen = act("fullscreen", "全屏", "F11", self.toggle_fullscreen)
        button(self.act_slideshow)
        button(self.act_fullscreen)
        self.act_slideshow.toggled.connect(
            lambda on: self.act_slideshow.setIcon(
                icons.icon("play", theme.ACCENT if on else "#C7C1B4")
            )
        )

        gap(4)
        self.menu_button = QToolButton(self.toolbar)
        self.menu_button.setIcon(icons.icon("more"))
        self.menu_button.setIconSize(QSize(20, 20))
        self.menu_button.setFixedSize(34, 34)
        self.menu_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.menu_button.setToolTip("更多")
        self.menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.menu_button)

        def menu_action(text: str, slot, shortcut: str | None = None, checkable=False) -> QAction:
            item = QAction(text, self)
            if shortcut:
                item.setShortcut(QKeySequence(shortcut))
            item.setCheckable(checkable)
            item.triggered.connect(slot)
            self.addAction(item)
            return item

        self.act_rail = menu_action("显示缩略图栏", self._toggle_rail, "Tab", checkable=True)
        self.act_rail.setChecked(True)
        menu.addAction(self.act_rail)
        menu.addSeparator()
        menu.addAction(menu_action("向左旋转", lambda: self.rotate(-90), "Shift+R"))
        menu.addAction(menu_action("向右旋转", lambda: self.rotate(90), "R"))
        menu.addAction(menu_action("水平翻转", self.flip, "H"))
        menu.addSeparator()
        menu.addAction("复制图片", self.copy_image)
        menu.addAction("在资源管理器中显示", self.reveal_in_explorer)
        menu.addAction("用系统默认应用打开", self.open_externally)
        menu.addSeparator()
        menu.addAction("关于 Lumen View", self.show_about)
        self.menu_button.setMenu(menu)
        self._bar_layout.addWidget(self.menu_button)

        self._extra_actions = [
            self.act_fit, self.act_actual, self.act_zoom_in, self.act_zoom_out,
        ]

    # ------------------------------------------------------------------ #
    # window chrome
    # ------------------------------------------------------------------ #
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._chrome_applied:
            self._chrome_applied = True
            self._apply_window_chrome()

    def _apply_window_chrome(self) -> None:
        """Dark native caption that blends into the app background."""
        try:
            import ctypes

            hwnd = int(self.winId())
            dwm = ctypes.windll.dwmapi

            def attribute(value_id: int, value: int) -> None:
                data = ctypes.c_int(value)
                dwm.DwmSetWindowAttribute(
                    hwnd, value_id, ctypes.byref(data), ctypes.sizeof(data)
                )

            attribute(20, int(theme.BG == "#171819"))  # DWMWA_USE_IMMERSIVE_DARK_MODE
            attribute(35, theme.colorref(theme.BG))  # caption colour
            attribute(36, theme.colorref(theme.TEXT))  # caption text
            attribute(34, theme.colorref(theme.BG))  # border colour
            attribute(33, 2)  # rounded corners
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # layout helpers
    # ------------------------------------------------------------------ #
    def _toggle_rail(self, visible: bool | None = None) -> None:
        if visible is None:
            visible = not self._filmstrip.isVisible()
        show = bool(visible) and bool(self._files)
        self._filmstrip.setVisible(show)
        self.act_rail.setChecked(show)
        self._sync_footer_margin()

    def _sync_footer_margin(self) -> None:
        left = 240 if self._filmstrip.isVisible() else 18
        self.footer.layout().setContentsMargins(left, 6, 6, 6)

    # ------------------------------------------------------------------ #
    # settings
    # ------------------------------------------------------------------ #
    def _restore_settings(self) -> None:
        geometry = self._settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(1280, 820)
        interval = self._settings.value("slideshow/interval", 3000, type=int)
        self._slideshow.setInterval(max(500, interval))

    def closeEvent(self, event) -> None:
        self._pool.clear()
        self._pool.waitForDone(3000)
        self._filmstrip.shutdown()
        self._settings.setValue("window/geometry", self.saveGeometry())
        self._settings.sync()
        super().closeEvent(event)

    # ------------------------------------------------------------------ #
    # opening
    # ------------------------------------------------------------------ #
    def open_file(self) -> None:
        start = self._settings.value("paths/last", os.path.expanduser("~"), type=str)
        pattern = " ".join(f"*.{ext}" for ext in sorted(decoders.SUPPORTED_EXTS))
        filters = f"图片文件 ({pattern});;所有文件 (*.*)"
        path, _ = QFileDialog.getOpenFileName(self, "打开图片", start, filters)
        if path:
            self.load_path(path)

    def open_folder(self) -> None:
        start = self._settings.value("paths/last", os.path.expanduser("~"), type=str)
        folder = QFileDialog.getExistingDirectory(self, "打开文件夹", start)
        if folder:
            files = self._scan_folder(folder)
            if not files:
                QMessageBox.information(self, "Lumen View", "这个文件夹里没有可显示的图片。")
                return
            self._settings.setValue("paths/last", folder)
            self._set_folder(files, files[0])

    def load_path(self, path: str) -> None:
        path = os.path.abspath(path)
        if os.path.isdir(path):
            files = self._scan_folder(path)
            if files:
                self._set_folder(files, files[0])
            return
        if not os.path.isfile(path):
            self.show_message("文件不存在", path, [])
            return

        self._settings.setValue("paths/last", os.path.dirname(path))
        files = self._scan_folder(os.path.dirname(path))
        if path not in files:
            files = [path]
        self._set_folder(files, path)

    @staticmethod
    def _scan_folder(folder: str) -> list[str]:
        try:
            entries = [
                entry.path
                for entry in os.scandir(folder)
                if entry.is_file() and decoders.extension(entry.name) in decoders.SUPPORTED_EXTS
            ]
        except OSError:
            return []
        entries.sort(key=lambda p: _natural_key(os.path.basename(p)))
        return entries[:5000]

    def _set_folder(self, files: list[str], current: str) -> None:
        self._files = files
        self._filmstrip.set_files(files, current)
        self._filmstrip.setVisible(True)
        self.act_rail.setChecked(True)
        self._sync_footer_margin()
        self._load(current)

    def _load(self, path: str) -> None:
        self._current = path
        self._token += 1
        self._pool.clear()
        token = self._token
        self._update_title()
        self._update_count()
        if self._loaded is None:
            self.show_message("正在解码…", os.path.basename(path), [])
        self._pool.start(_DecodeTask(token, path, self._signals))

    # ------------------------------------------------------------------ #
    # decode results
    # ------------------------------------------------------------------ #
    def _on_decoded(self, token: int, path: str, loaded: Loaded) -> None:
        if token != self._token:
            return
        self._loaded = loaded
        self.stack.setCurrentWidget(self.canvas)
        self.canvas.set_loaded(loaded)
        rotation, flipped = self._view_states.get(path, (0, False))
        if rotation or flipped:
            self.canvas.set_view_state(rotation, flipped)
        self._update_info()
        self._update_actions()
        self._filmstrip.set_current(path)
        self._show_overlays(True)

    def _on_decode_failed(self, token: int, path: str, message: str) -> None:
        if token != self._token:
            return
        self._loaded = None
        self._update_actions()
        self.info_label.setText("无法打开")
        self._show_overlays(False)
        self.show_message(
            "打不开这张图片",
            f"{os.path.basename(path)}\n\n{message}",
            [("用系统默认应用试试", self.open_externally),
             ("在资源管理器中显示", self.reveal_in_explorer)],
        )

    # ------------------------------------------------------------------ #
    # navigation
    # ------------------------------------------------------------------ #
    def _index(self) -> int:
        try:
            return self._files.index(self._current)
        except ValueError:
            return -1

    def next(self) -> None:
        index = self._index()
        if 0 <= index < len(self._files) - 1:
            self._load(self._files[index + 1])

    def previous(self) -> None:
        index = self._index()
        if index > 0:
            self._load(self._files[index - 1])

    def _on_filmstrip_clicked(self, path: str) -> None:
        if path != self._current:
            self._load(path)

    # ------------------------------------------------------------------ #
    # view commands
    # ------------------------------------------------------------------ #
    def fit(self) -> None:
        if self._loaded:
            self.canvas.fit_to_window()

    def actual_size(self) -> None:
        if self._loaded:
            self.canvas.actual_size()

    def _toggle_fit(self) -> None:
        if not self._loaded:
            return
        if self.canvas.current_scale() >= 0.999:
            self.canvas.fit_to_window()
        else:
            self.canvas.actual_size()

    def rotate(self, degrees: int) -> None:
        if not self._loaded:
            return
        self.canvas.rotate_by(degrees)
        self._view_states[self._loaded.path] = self.canvas.view_state()

    def flip(self) -> None:
        if not self._loaded:
            return
        self.canvas.flip()
        self._view_states[self._loaded.path] = self.canvas.view_state()

    def toggle_slideshow(self) -> None:
        if self._slideshow.isActive():
            self.stop_slideshow()
            return
        if not self._loaded or len(self._files) < 2:
            self.act_slideshow.setChecked(False)
            return
        self._slideshow.start()
        self.act_slideshow.setChecked(True)

    def stop_slideshow(self) -> None:
        self._slideshow.stop()
        self.act_slideshow.setChecked(False)

    def _slideshow_next(self) -> None:
        index = self._index()
        if index < 0:
            return
        self._load(self._files[(index + 1) % len(self._files)])

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            self.toolbar.show()
            self._filmstrip.setVisible(bool(self._files) and self._rail_was_visible)
            self.canvas_area.layout().setContentsMargins(14, 2, 14, 14)
            self._sync_footer_margin()
            self._show_overlays(self._loaded is not None)
            self.act_fullscreen.setChecked(False)
        else:
            self._rail_was_visible = self._filmstrip.isVisible()
            self.showFullScreen()
            self.toolbar.hide()
            self._filmstrip.hide()
            self.footer.hide()
            self.canvas_area.layout().setContentsMargins(0, 0, 0, 0)
            self.act_fullscreen.setChecked(True)
        QTimer.singleShot(0, self._refit_if_needed)

    def _refit_if_needed(self) -> None:
        if self._loaded and self.canvas.is_fit_mode():
            self.canvas.fit_to_window()

    # ------------------------------------------------------------------ #
    # misc actions
    # ------------------------------------------------------------------ #
    def reveal_in_explorer(self) -> None:
        if not self._current:
            return
        try:
            os.startfile(os.path.dirname(self._current))  # type: ignore[attr-defined]
        except Exception:
            pass

    def open_externally(self) -> None:
        if not self._current:
            return
        try:
            os.startfile(self._current)  # type: ignore[attr-defined]
        except Exception as exc:
            QMessageBox.warning(self, "Lumen View", f"无法调用系统程序：{exc}")

    def copy_image(self) -> None:
        if self._loaded:
            QGuiApplication.clipboard().setImage(self._loaded.first)

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            "关于 Lumen View",
            "<b>Lumen View</b><br>轻量、本地优先、格式管够的看图软件。<br><br>"
            "风格与 <i>Lumen Mark</i> 一脉相承：成熟底座 + 薄定制层。<br>"
            "JPEG / PNG / GIF / WebP / AVIF / HEIC / HEIF / JXL / TIFF / ICO / "
            "PSD / SVG / 相机 RAW …",
        )

    # ------------------------------------------------------------------ #
    # ui updates
    # ------------------------------------------------------------------ #
    def _update_title(self) -> None:
        if self._current:
            self.setWindowTitle(f"{os.path.basename(self._current)} — Lumen View")
        else:
            self.setWindowTitle("Lumen View")

    def _update_count(self) -> None:
        index = self._index()
        if index >= 0:
            self.count_label.setText(f"{index + 1} / {len(self._files)}")
            self._dot_b.setVisible(True)
        else:
            self.count_label.setText("")
            self._dot_b.setVisible(False)

    def _update_info(self) -> None:
        loaded = self._loaded
        if loaded is None:
            return
        parts = [f"{loaded.width} × {loaded.height}", loaded.fmt]
        if loaded.mode:
            parts.append(loaded.mode)
        if loaded.file_size:
            parts.append(decoders.format_size(loaded.file_size))
        if loaded.animated:
            parts.append(f"动图 {len(loaded.frames)} 帧")
        self.info_label.setText("  ·  ".join(parts))
        self.name_label.setText(os.path.basename(loaded.path))
        tips = [f"{key}：{value}" for key, value in loaded.exif.items()]
        self.info_label.setToolTip("\n".join(tips))

    def _update_actions(self) -> None:
        has_image = self._loaded is not None
        for action in self._extra_actions:
            action.setEnabled(has_image)
        index = self._index()
        self.act_prev.setEnabled(index > 0)
        self.act_next.setEnabled(0 <= index < len(self._files) - 1)
        if hasattr(self, "act_rail"):
            self.act_rail.setEnabled(bool(self._files))
        self._update_count()

    def _on_zoom_changed(self, scale: float) -> None:
        self.zoom_label.setText(f"{scale * 100:.0f}%")

    def _show_overlays(self, visible: bool) -> None:
        self.footer.setVisible(visible and not self.isFullScreen())

    # ------------------------------------------------------------------ #
    # message page
    # ------------------------------------------------------------------ #
    def show_empty_state(self) -> None:
        self._msg_icon.setVisible(True)
        self._msg_brand.setVisible(True)
        self.msg_title.setText("")
        self.msg_title.setVisible(False)
        self.msg_detail.setText(
            "把照片或文件夹拖进来，或按 Ctrl+O 打开\n"
            "JPEG · PNG · GIF · WebP · AVIF · HEIC · JXL · TIFF · PSD · SVG · RAW"
        )
        self._set_buttons(
            [("打开图片…", self.open_file, True), ("打开文件夹…", self.open_folder, False)]
        )
        self.stack.setCurrentWidget(self.message_page)
        self._show_overlays(False)

    def show_message(self, title: str, detail: str, buttons, primary: bool = False) -> None:
        self._msg_icon.setVisible(False)
        self._msg_brand.setVisible(False)
        self.msg_title.setText(title)
        self.msg_title.setVisible(True)
        self.msg_detail.setText(detail)
        self._set_buttons([(text, callback, primary and i == 0)
                           for i, (text, callback) in enumerate(buttons)])
        self.stack.setCurrentWidget(self.message_page)
        self._show_overlays(False)

    def _set_buttons(self, buttons) -> None:
        while self.msg_buttons.count() > 2:
            item = self.msg_buttons.takeAt(1)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for text, callback, primary in buttons:
            button = QPushButton(text, self)
            if primary:
                button.setObjectName("Primary")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(callback)
            self.msg_buttons.insertWidget(self.msg_buttons.count() - 1, button)

    def _canvas_menu(self, position) -> None:
        menu = QMenu(self)
        menu.addAction("适应窗口", self.fit)
        menu.addAction("实际大小", self.actual_size)
        menu.addSeparator()
        menu.addAction("向左旋转", lambda: self.rotate(-90))
        menu.addAction("向右旋转", lambda: self.rotate(90))
        menu.addAction("水平翻转", self.flip)
        menu.addSeparator()
        menu.addAction("复制图片", self.copy_image)
        menu.addAction("在资源管理器中显示", self.reveal_in_explorer)
        menu.exec(self.canvas.viewport().mapToGlobal(position))

    # ------------------------------------------------------------------ #
    # keyboard / dnd
    # ------------------------------------------------------------------ #
    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            if self.isFullScreen():
                self.toggle_fullscreen()
            elif self._slideshow.isActive():
                self.stop_slideshow()
            event.accept()
            return
        if key == Qt.Key.Key_Space:
            self.next()
            event.accept()
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if not urls:
            return
        path = urls[0].toLocalFile()
        if path:
            self.stop_slideshow()
            self.load_path(path)
        event.acceptProposedAction()
