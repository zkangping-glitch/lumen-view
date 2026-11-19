"""Hand-drawn interface icons plus the Lumen View app mark."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
    QRadialGradient,
)

from . import theme


def _stroke(p: QPainter, color: str, width: float = 1.55) -> None:
    pen = QPen(QColor(color))
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)


def _poly(p: QPainter, points, close: bool = False) -> None:
    path = QPainterPath(QPointF(*points[0]))
    for pt in points[1:]:
        path.lineTo(QPointF(*pt))
    if close:
        path.closeSubpath()
    p.drawPath(path)


def _chevron(p: QPainter, direction: int) -> None:
    x1, x2 = (14, 9.5) if direction < 0 else (10, 14.5)
    _poly(p, [(x1, 5.5), (x2, 12), (x1, 18.5)])


def _magnifier(p: QPainter, plus: bool) -> None:
    p.drawEllipse(QPointF(10.5, 10.5), 6.1, 6.1)
    _poly(p, [(15.2, 15.2), (19.8, 19.8)])
    _poly(p, [(7.8, 10.5), (13.2, 10.5)])
    if plus:
        _poly(p, [(10.5, 7.8), (10.5, 13.2)])


def _corners(p: QPainter) -> None:
    m, n = 4, 20
    _poly(p, [(m, m + 5), (m, m), (m + 5, m)])
    _poly(p, [(n - 5, m), (n, m), (n, m + 5)])
    _poly(p, [(n, n - 5), (n, n), (n - 5, n)])
    _poly(p, [(m + 5, n), (m, n), (m, n - 5)])


def _rotate(p: QPainter, clockwise: bool) -> None:
    rect = QRectF(4.5, 4.5, 15, 15)
    if clockwise:
        p.drawArc(rect, 60 * 16, 270 * 16)
        tip = QPointF(18.4, 7.4)
        _poly(p, [(tip.x() - 3.6, tip.y() - 0.4), (tip.x(), tip.y()), (tip.x() - 0.4, tip.y() + 3.6)])
    else:
        p.drawArc(rect, 150 * 16, -270 * 16)
        tip = QPointF(5.6, 7.4)
        _poly(p, [(tip.x() + 3.6, tip.y() - 0.4), (tip.x(), tip.y()), (tip.x() + 0.4, tip.y() + 3.6)])


def _flip(p: QPainter) -> None:
    pen = p.pen()
    dashed = QPen(pen)
    dashed.setStyle(Qt.PenStyle.DashLine)
    dashed.setDashPattern([2, 2])
    p.setPen(dashed)
    _poly(p, [(12, 4), (12, 20)])
    p.setPen(pen)
    _poly(p, [(9.5, 6.5), (4, 12), (9.5, 17.5)], close=True)
    _poly(p, [(14.5, 6.5), (20, 12), (14.5, 17.5)], close=True)


def _play(p: QPainter, color: str) -> None:
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    _poly(p, [(8.5, 5.5), (18.5, 12), (8.5, 18.5)], close=True)


def _text_icon(p: QPainter, text: str) -> None:
    font = QFont("Segoe UI")
    font.setPixelSize(11)
    font.setWeight(QFont.Weight.Bold)
    p.setFont(font)
    p.drawText(QRectF(0, 0, 24, 24), Qt.AlignmentFlag.AlignCenter, text)


def _more(p: QPainter) -> None:
    p.setBrush(p.pen().color())
    p.setPen(Qt.PenStyle.NoPen)
    for x in (6.2, 12, 17.8):
        p.drawEllipse(QPointF(x, 12), 1.35, 1.35)


def _draw(name: str, p: QPainter, color: str) -> None:
    if name == "open":
        _poly(p, [(3, 19), (3, 7), (10, 7), (12, 9.5), (21, 9.5), (21, 19)], close=True)
        _poly(p, [(3, 11), (21, 11)])
    elif name == "image":
        p.drawRoundedRect(QRectF(3.5, 4.5, 17, 15), 2.5, 2.5)
        p.drawEllipse(QPointF(8.6, 9.3), 1.6, 1.6)
        _poly(p, [(5.8, 17), (10.2, 11.8), (13.2, 14.9), (15.6, 12.3), (18.4, 17)])
    elif name == "prev":
        _chevron(p, -1)
    elif name == "next":
        _chevron(p, 1)
    elif name == "zoom_in":
        _magnifier(p, True)
    elif name == "zoom_out":
        _magnifier(p, False)
    elif name == "fit":
        _corners(p)
    elif name == "actual":
        _text_icon(p, "1:1")
    elif name == "rotate_right":
        _rotate(p, True)
    elif name == "rotate_left":
        _rotate(p, False)
    elif name == "flip":
        _flip(p)
    elif name == "play":
        _play(p, color)
    elif name == "fullscreen":
        _corners(p)
        p.drawEllipse(QPointF(12, 12), 1.8, 1.8)
    elif name == "more":
        _more(p)
    elif name == "close":
        _poly(p, [(6.5, 6.5), (17.5, 17.5)])
        _poly(p, [(17.5, 6.5), (6.5, 17.5)])
    else:  # pragma: no cover - programming error
        raise ValueError(f"unknown icon: {name}")


def _render(name: str, color: str, size: int, dpr: float) -> QPixmap:
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.scale(size / 24.0, size / 24.0)
    _stroke(p, color)
    _draw(name, p, color)
    p.end()
    return pm


def icon(name: str, color: str = "#C7C1B4", size: int = 20, dpr: float = 2.0) -> QIcon:
    result = QIcon()
    result.addPixmap(_render(name, color, size, dpr), QIcon.Mode.Normal)
    result.addPixmap(_render(name, "#5A554B", size, dpr), QIcon.Mode.Disabled)
    return result


def accent_dot(size: int = 8) -> QPixmap:
    dpr = 3.0
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    grad = QRadialGradient(QPointF(size / 2, size / 2), size / 2)
    grad.setColorAt(0.0, QColor(theme.ACCENT))
    grad.setColorAt(0.55, QColor(230, 181, 103, 210))
    grad.setColorAt(1.0, QColor(230, 181, 103, 0))
    p.setBrush(grad)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(0, 0, size, size))
    p.end()
    return pm


def app_icon() -> QIcon:
    """Load the authored app mark, with the original vector mark as a fallback."""
    asset = Path(__file__).resolve().parent / "assets" / "LumenView.png"
    if asset.is_file():
        result = QIcon(str(asset))
        if not result.isNull():
            return result

    # Fallback used only if an incomplete source checkout is launched.
    pm = QPixmap(256, 256)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    tile = QPainterPath()
    tile.addRoundedRect(QRectF(8, 8, 240, 240), 58, 58)
    p.setClipPath(tile)

    bg = QLinearGradient(0, 0, 256, 256)
    bg.setColorAt(0.0, QColor("#1C1812"))
    bg.setColorAt(1.0, QColor("#090807"))
    p.fillPath(tile, bg)

    bloom = QRadialGradient(QPointF(182, 76), 150)
    bloom.setColorAt(0.0, QColor(246, 200, 126, 235))
    bloom.setColorAt(0.45, QColor(233, 178, 96, 120))
    bloom.setColorAt(1.0, QColor(233, 178, 96, 0))
    p.setBrush(bloom)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(182, 76), 150, 150)

    p.setClipping(False)
    ring = QPen(QColor(247, 240, 226, 235))
    ring.setWidthF(9)
    p.setPen(ring)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(112, 150), 57, 57)

    p.setPen(QPen(QColor(247, 240, 226, 90), 5, Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap))
    p.drawArc(QRectF(55, 93, 114, 114), 125 * 16, 70 * 16)

    core = QRadialGradient(QPointF(112, 150), 30)
    core.setColorAt(0.0, QColor(255, 226, 170, 255))
    core.setColorAt(0.5, QColor(233, 178, 96, 210))
    core.setColorAt(1.0, QColor(233, 178, 96, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(core)
    p.drawEllipse(QPointF(112, 150), 30, 30)
    p.end()
    return QIcon(pm)
