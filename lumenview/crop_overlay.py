"""Viewport anchored, nondestructive crop selection."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class CropOverlay(QWidget):
    boxChanged = Signal(object)

    def __init__(self, canvas):
        super().__init__(canvas.viewport())
        self.canvas = canvas
        self.box = (0.1, 0.1, 0.9, 0.9)
        self.ratio = None
        self.reference_size = None
        self.ratio_label = "自由"
        self._drag = None
        self._initial = self.box
        self._start = QPointF()
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.hide()
        canvas.zoomChanged.connect(self.update)
        canvas.horizontalScrollBar().valueChanged.connect(self.update)
        canvas.verticalScrollBar().valueChanged.connect(self.update)

    def set_box(self, box):
        self.box = box or (0.1, 0.1, 0.9, 0.9)
        self.update()

    def reset_box(self):
        self.set_box((0.0, 0.0, 1.0, 1.0))
        self.boxChanged.emit(self.box)

    def set_ratio(self, ratio):
        self.ratio = ratio
        if ratio:
            x0, y0, x1, y1 = self.box
            width, height = self._image_size()
            if width and height:
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                w = x1 - x0
                h = w * width / (ratio * height)
                if h > 1:
                    h = y1 - y0
                    w = h * ratio * height / width
                w, h = min(w, 1), min(h, 1)
                cx = max(w / 2, min(1 - w / 2, cx))
                cy = max(h / 2, min(1 - h / 2, cy))
                self.box = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        self.update()

    def _image_size(self):
        pix = self.canvas._item.pixmap()
        return pix.width(), pix.height()

    def _screen_rect(self):
        width, height = self._image_size()
        x0, y0, x1, y1 = self.box
        item = self.canvas._item
        a = self.canvas.mapFromScene(item.mapToScene(QPointF(x0 * width, y0 * height)))
        b = self.canvas.mapFromScene(item.mapToScene(QPointF(x1 * width, y1 * height)))
        return QRectF(QPointF(a), QPointF(b)).normalized()

    def _normalized_at(self, point):
        width, height = self._image_size()
        if not width or not height:
            return QPointF()
        scene = self.canvas.mapToScene(point.toPoint())
        image = self.canvas._item.mapFromScene(scene)
        return QPointF(max(0, min(1, image.x() / width)),
                       max(0, min(1, image.y() / height)))

    def _handles(self, rect):
        cx, cy = rect.center().x(), rect.center().y()
        return {
            "nw": rect.topLeft(), "n": QPointF(cx, rect.top()), "ne": rect.topRight(),
            "e": QPointF(rect.right(), cy), "se": rect.bottomRight(),
            "s": QPointF(cx, rect.bottom()), "sw": rect.bottomLeft(),
            "w": QPointF(rect.left(), cy),
        }

    def _hit(self, point):
        rect = self._screen_rect()
        for name, center in self._handles(rect).items():
            if (center - point).manhattanLength() <= 16:
                return name
        return "move" if rect.contains(point) else "new"

    def paintEvent(self, _event):
        rect = self._screen_rect()
        if rect.isEmpty():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        shade = QColor(10, 16, 13, 145)
        bounds = QRectF(self.rect())
        painter.fillRect(QRectF(bounds.left(), bounds.top(), bounds.width(), max(0, rect.top())), shade)
        painter.fillRect(QRectF(bounds.left(), rect.bottom(), bounds.width(), max(0, bounds.bottom() - rect.bottom())), shade)
        painter.fillRect(QRectF(bounds.left(), rect.top(), max(0, rect.left()), rect.height()), shade)
        painter.fillRect(QRectF(rect.right(), rect.top(), max(0, bounds.right() - rect.right()), rect.height()), shade)
        painter.setPen(QPen(QColor("#FFFFFF"), 2))
        painter.drawRect(rect)
        painter.setPen(QPen(QColor(255, 255, 255, 120), 1))
        for fraction in (1 / 3, 2 / 3):
            x = rect.left() + rect.width() * fraction
            y = rect.top() + rect.height() * fraction
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        painter.setPen(QPen(QColor("#356B52"), 1))
        painter.setBrush(QColor("#FFFFFF"))
        for center in self._handles(rect).values():
            painter.drawRoundedRect(QRectF(center.x() - 5, center.y() - 5, 10, 10), 2, 2)
        width, height = self.reference_size or self._image_size()
        x0, y0, x1, y1 = self.box
        label = f"{round((x1 - x0) * width)} × {round((y1 - y0) * height)} px"
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(QRectF(rect.left(), rect.top() - 28, max(120, rect.width()), 24), self.ratio_label)
        painter.drawText(QRectF(rect.left(), rect.bottom() + 8, max(120, rect.width()), 24), label)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._drag = "pan"
            self._start = event.position()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        self._drag = self._hit(event.position())
        self._start = self._normalized_at(event.position())
        self._initial = self.box
        self.mouseMoveEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag == "pan":
            delta = event.position() - self._start
            self.canvas.horizontalScrollBar().setValue(self.canvas.horizontalScrollBar().value() - round(delta.x()))
            self.canvas.verticalScrollBar().setValue(self.canvas.verticalScrollBar().value() - round(delta.y()))
            self._start = event.position()
            self.update()
            return
        if not self._drag:
            hit = self._hit(event.position())
            shape = Qt.CursorShape.SizeAllCursor if hit == "move" else (
                Qt.CursorShape.CrossCursor if hit == "new" else Qt.CursorShape.SizeFDiagCursor)
            self.setCursor(shape)
            return
        point = self._normalized_at(event.position())
        x0, y0, x1, y1 = self._initial
        if self._drag == "move":
            dx, dy = point.x() - self._start.x(), point.y() - self._start.y()
            dx = max(-x0, min(1 - x1, dx))
            dy = max(-y0, min(1 - y1, dy))
            box = (x0 + dx, y0 + dy, x1 + dx, y1 + dy)
        elif self._drag == "new":
            box = (min(self._start.x(), point.x()), min(self._start.y(), point.y()),
                   max(self._start.x(), point.x()), max(self._start.y(), point.y()))
        else:
            if "w" in self._drag: x0 = point.x()
            if "e" in self._drag: x1 = point.x()
            if "n" in self._drag: y0 = point.y()
            if "s" in self._drag: y1 = point.y()
            box = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        if self.ratio and self._drag != "move":
            a, b, c, d = box
            width, height = self._image_size()
            if width and height:
                factor = self.ratio * height / width
                if self._drag in ("n", "s"):
                    target_w = min(1, (d - b) * factor)
                    center = (self._initial[0] + self._initial[2]) / 2
                    a = max(0, min(1 - target_w, center - target_w / 2))
                    c = a + target_w
                else:
                    target_h = min(1, (c - a) / factor)
                    if self._drag in ("w", "e"):
                        center = (self._initial[1] + self._initial[3]) / 2
                        b = max(0, min(1 - target_h, center - target_h / 2))
                        d = b + target_h
                    elif "n" in self._drag and "s" not in self._drag:
                        b = max(0, d - target_h)
                    else:
                        d = min(1, b + target_h)
                box = (a, b, c, d)
        if box[2] - box[0] >= .01 and box[3] - box[1] >= .01:
            self.box = box
            self.boxChanged.emit(box)
            self.update()

    def mouseReleaseEvent(self, event):
        self._drag = None
        event.accept()

    def wheelEvent(self, event):
        steps = event.angleDelta().y() / 120
        if steps:
            self.canvas.zoom_by(1.2 ** steps, event.position())
            self.update()
        event.accept()
