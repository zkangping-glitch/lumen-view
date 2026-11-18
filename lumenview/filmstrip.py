"""Floating thumbnail rail with a background decoding pool."""

from __future__ import annotations

import os

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame, QLabel, QListWidget, QListWidgetItem, QVBoxLayout,
)

from . import decoders, theme

THUMB_W, THUMB_H = 168, 116
MAX_THUMBS = 1500


def _placeholder(text: str = "") -> QPixmap:
    pm = QPixmap(THUMB_W, THUMB_H)
    pm.fill(QColor("#101215"))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setBrush(QColor("#171A1F"))
    p.setPen(QColor("#22262D"))
    p.drawRoundedRect(1, 1, THUMB_W - 2, THUMB_H - 2, 9, 9)
    if text:
        p.setPen(QColor("#4E4A43"))
        font = p.font()
        font.setPointSize(9)
        p.setFont(font)
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, text)
    p.end()
    return pm


class _Signals(QObject):
    ready = Signal(str, QImage)


class _ThumbTask(QRunnable):
    def __init__(self, path: str, size: int, signals: _Signals) -> None:
        super().__init__()
        self.path = path
        self.size = size
        self.signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            image = decoders.load_thumbnail(self.path, self.size)
        except Exception:
            image = QImage()
        self.signals.ready.emit(self.path, image)


class Filmstrip(QFrame):
    fileActivated = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Rail")
        self.setFixedWidth(208)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(8)

        self.header = QLabel("", self)
        self.header.setObjectName("BrandSub")
        header_font = QFont(self.header.font())
        header_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
        self.header.setFont(header_font)
        layout.addWidget(self.header)

        self.list = QListWidget(self)
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setFlow(QListWidget.Flow.TopToBottom)
        self.list.setWrapping(False)
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setGridSize(QSize(THUMB_W + 12, THUMB_H + 34))
        self.list.setIconSize(QSize(THUMB_W, THUMB_H))
        self.list.setUniformItemSizes(True)
        self.list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.list.setWordWrap(False)
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.setStyleSheet("QListWidget { background: transparent; border: none; }")
        layout.addWidget(self.list, 1)

        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(4)
        self._signals = _Signals(self)
        self._signals.ready.connect(self._on_thumb_ready)

        self._items: dict[str, QListWidgetItem] = {}
        self._cache: dict[str, QPixmap] = {}
        self._pending: set[str] = set()
        self._syncing = False
        self._placeholder = _placeholder()

        self.list.currentItemChanged.connect(self._on_current_changed)

    # ------------------------------------------------------------------ #
    def set_files(self, paths: list[str], current: str | None = None) -> None:
        self._syncing = True
        self.list.clear()
        self._items.clear()
        for path in paths:
            item = QListWidgetItem(os.path.basename(path))
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            item.setForeground(QColor(theme.MUTED))
            cached = self._cache.get(path)
            item.setIcon(cached if cached is not None else self._placeholder)
            self.list.addItem(item)
            self._items[path] = item
        self._syncing = False

        folder = os.path.dirname(paths[0]) if paths else ""
        name = os.path.basename(folder) or folder
        if len(name) > 22:
            name = name[:21] + "…"
        self.header.setText(f"{name.upper()}  ·  {len(paths)}" if paths else "")

        for path in paths[:MAX_THUMBS]:
            if path not in self._cache:
                self._request(path)

        if current:
            self.set_current(current)
        elif paths:
            self.list.setCurrentRow(0)

    def shutdown(self) -> None:
        self._pool.clear()
        self._pool.waitForDone(3000)

    def set_current(self, path: str) -> None:
        item = self._items.get(path)
        if item is None:
            return
        self._syncing = True
        self.list.setCurrentItem(item)
        self._syncing = False
        self.list.scrollToItem(item, QListWidget.ScrollHint.PositionAtCenter)

    # ------------------------------------------------------------------ #
    def _request(self, path: str) -> None:
        if path in self._pending:
            return
        self._pending.add(path)
        self._pool.start(_ThumbTask(path, max(THUMB_W, THUMB_H) * 2, self._signals))

    def _on_thumb_ready(self, path: str, image: QImage) -> None:
        self._pending.discard(path)
        item = self._items.get(path)
        if item is None:
            return
        if image.isNull():
            item.setIcon(_placeholder("!"))
            return
        pix = QPixmap.fromImage(image)
        self._cache[path] = pix
        item.setIcon(pix)

    def _on_current_changed(self, current: QListWidgetItem | None, _previous) -> None:
        if self._syncing or current is None:
            return
        path = current.data(Qt.ItemDataRole.UserRole)
        if path:
            self.fileActivated.emit(path)
