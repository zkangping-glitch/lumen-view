"""Zoomable / pannable image canvas with animation playback."""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve, QPointF, QRectF, Qt, QTimer, QVariantAnimation, Signal,
)
from PySide6.QtGui import (
    QBrush, QColor, QPainter, QPixmap, QRadialGradient, QTransform,
)
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QGraphicsView

from .decoders import Loaded
from . import theme

MIN_SCALE = 0.02
MAX_SCALE = 32.0


class ImageCanvas(QGraphicsView):
    zoomChanged = Signal(float)
    doubleClicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self._item = QGraphicsPixmapItem()
        self._item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self._scene.addItem(self._item)

        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
            | QPainter.RenderHint.TextAntialiasing
        )
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setBackgroundBrush(Qt.BrushStyle.NoBrush)
        self.setStyleSheet("background: transparent;")
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        self._loaded: Loaded | None = None
        self._frame_index = 0
        self._rotation = 0
        self._flipped = False
        self._fit_mode = True
        self._anim_timer = QTimer(self)
        self._anim_timer.setSingleShot(True)
        self._anim_timer.timeout.connect(self._advance_frame)

        self._fade = QVariantAnimation(self)
        self._fade.setDuration(180)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.valueChanged.connect(lambda value: self._item.setOpacity(float(value)))

    # ------------------------------------------------------------------ #
    # loading
    # ------------------------------------------------------------------ #
    def clear_image(self) -> None:
        self._stop_animation()
        self._loaded = None
        self._item.setPixmap(QPixmap())
        self._scene.setSceneRect(QRectF())
        self.resetTransform()
        self.zoomChanged.emit(1.0)

    def set_loaded(self, loaded: Loaded) -> None:
        self._stop_animation()
        self._loaded = loaded
        self._frame_index = 0
        self._rotation = 0
        self._flipped = False
        self._apply_pixmap(loaded.frames[0].image)
        self.fit_to_window()
        self._fade.stop()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        if loaded.animated:
            self._schedule_next()

    def set_view_state(self, rotation: int, flipped: bool) -> None:
        self._rotation = rotation % 360
        self._flipped = flipped
        self._apply_item_transform()
        self.fit_to_window()

    def view_state(self) -> tuple[int, bool]:
        return self._rotation, self._flipped

    def _apply_pixmap(self, image) -> None:
        pix = QPixmap.fromImage(image)
        self._item.setPixmap(pix)
        rect = QRectF(0, 0, pix.width(), pix.height())
        self._scene.setSceneRect(rect)
        self._item.setTransformOriginPoint(rect.center())
        self._apply_item_transform()

    def _apply_item_transform(self) -> None:
        tf = QTransform()
        tf.rotate(self._rotation)
        tf.scale(-1.0 if self._flipped else 1.0, 1.0)
        self._item.setTransform(tf)
        bounds = self._item.sceneBoundingRect()
        if not bounds.isEmpty():
            self._scene.setSceneRect(bounds)

    # ------------------------------------------------------------------ #
    # animation
    # ------------------------------------------------------------------ #
    def _schedule_next(self) -> None:
        if not self._loaded or not self._loaded.animated:
            return
        duration = self._loaded.frames[self._frame_index].duration or 100
        self._anim_timer.start(max(20, duration))

    def _advance_frame(self) -> None:
        if not self._loaded or not self._loaded.animated:
            return
        self._frame_index = (self._frame_index + 1) % len(self._loaded.frames)
        self._apply_pixmap(self._loaded.frames[self._frame_index].image)
        self._schedule_next()

    def _stop_animation(self) -> None:
        self._anim_timer.stop()

    # ------------------------------------------------------------------ #
    # zoom / fit
    # ------------------------------------------------------------------ #
    def current_scale(self) -> float:
        return self.transform().m11()

    def is_fit_mode(self) -> bool:
        return self._fit_mode

    def _emit_zoom(self) -> None:
        self.zoomChanged.emit(self.current_scale())

    def _set_scale(self, scale: float, anchor: QPointF | None = None) -> None:
        scale = max(MIN_SCALE, min(MAX_SCALE, scale))
        if anchor is None:
            anchor = QPointF(self.viewport().rect().center())
        old_scene = self.mapToScene(anchor.toPoint())
        self.resetTransform()
        self.scale(scale, scale)
        new_scene = self.mapToScene(anchor.toPoint())
        delta = new_scene - old_scene
        self.translate(delta.x(), delta.y())
        self._emit_zoom()

    def zoom_by(self, factor: float, anchor: QPointF | None = None) -> None:
        self._fit_mode = False
        self._set_scale(self.current_scale() * factor, anchor)

    def zoom_in(self) -> None:
        self._fit_mode = False
        self._set_scale(self.current_scale() * 1.25)

    def zoom_out(self) -> None:
        self._fit_mode = False
        self._set_scale(self.current_scale() / 1.25)

    def fit_to_window(self) -> None:
        if self._item.pixmap().isNull():
            return
        rect = self._item.sceneBoundingRect()
        if rect.width() <= 0 or rect.height() <= 0:
            return
        viewport = self.viewport().size()
        pad = 32  # breathing room around the photo
        scale = min(
            (viewport.width() - pad) / rect.width(),
            (viewport.height() - pad) / rect.height(),
        )
        scale = max(MIN_SCALE, min(4.0, scale))
        self.resetTransform()
        self.scale(scale, scale)
        self.centerOn(rect.center())
        self._fit_mode = True
        self._emit_zoom()

    def actual_size(self) -> None:
        self._fit_mode = False
        self.resetTransform()
        self.centerOn(self._item.sceneBoundingRect().center())
        self._emit_zoom()

    def rotate_by(self, degrees: int) -> None:
        self._rotation = (self._rotation + degrees) % 360
        self._apply_item_transform()
        if self._fit_mode:
            self.fit_to_window()
        else:
            self.centerOn(self._item.sceneBoundingRect().center())

    def flip(self) -> None:
        self._flipped = not self._flipped
        self._apply_item_transform()
        if self._fit_mode:
            self.fit_to_window()

    # ------------------------------------------------------------------ #
    # events
    # ------------------------------------------------------------------ #
    def drawBackground(self, painter, rect) -> None:
        painter.save()
        painter.fillRect(rect, QColor(theme.CANVAS))
        painter.restore()

    def wheelEvent(self, event) -> None:
        if self._item.pixmap().isNull():
            return
        steps = event.angleDelta().y() / 120.0
        if steps == 0:
            return
        self.zoom_by(1.2 ** steps, event.position())
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        self.doubleClicked.emit()
        event.accept()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fit_mode:
            self.fit_to_window()
