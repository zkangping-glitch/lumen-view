"""Lumen View visual language: warm light on charcoal, thin lines, quiet chrome."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette

BG = "#0A0B0D"
CANVAS = "#060708"
SURFACE = "#0F1114"
SURFACE_HI = "#15181C"
BORDER = "#1B1E23"
TEXT = "#ECE6DA"
MUTED = "#8E887C"
DIM = "#5D584F"
ACCENT = "#E6B567"
ACCENT_HOVER = "#F0C47C"
ACCENT_TEXT = "#1A1408"
ACCENT_SOFT = "#241D12"

FONT_FAMILY = '"Segoe UI Variable Text", "Microsoft YaHei UI", "Segoe UI", sans-serif'

QSS = f"""
* {{
    font-family: {FONT_FAMILY};
    font-size: 10pt;
    color: {TEXT};
}}
QMainWindow, QWidget#Root, QWidget#CanvasArea {{
    background: {BG};
}}
QWidget#TopBar {{
    background: transparent;
}}
QLabel#Brand {{
    color: #CFC6B4;
    font-size: 9pt;
    font-weight: 600;
}}
QLabel#BrandSub {{
    color: {DIM};
    font-size: 8pt;
}}
QWidget#MessagePage {{
    background: qradialgradient(cx:0.5, cy:0.40, radius:0.85,
        fx:0.5, fy:0.40, stop:0 #17130E, stop:0.45 #0C0D0F, stop:1 {BG});
}}
QLabel#Hint {{
    color: {MUTED};
    font-size: 9.5pt;
}}
QLabel#ErrorTitle {{
    color: {TEXT};
    font-size: 14pt;
    font-weight: 600;
}}
QLabel#PillName {{
    color: {TEXT};
    font-size: 9pt;
    font-weight: 600;
}}
QLabel#PillMeta {{
    color: {MUTED};
    font-size: 8.5pt;
}}
QLabel#Zoom {{
    color: {MUTED};
    font-size: 8.5pt;
}}
QToolButton {{
    background: transparent;
    border: none;
    border-radius: 9px;
    padding: 6px;
}}
QToolButton:hover {{
    background: #14FFFFFF;
}}
QToolButton:pressed {{
    background: #22FFFFFF;
}}
QToolButton:checked {{
    background: {ACCENT_SOFT};
}}
QFrame#Rail {{
    background: #0E1013;
    border: 1px solid {BORDER};
    border-radius: 16px;
}}
QFrame#Pill, QFrame#ZoomChip {{
    background: rgba(10, 11, 13, 0.62);
    border: 1px solid #1EFFFFFF;
    border-radius: 12px;
}}
QListWidget {{
    background: transparent;
    border: none;
    outline: 0;
    padding: 0px;
}}
QListWidget::item {{
    color: {MUTED};
    border: 1px solid transparent;
    border-radius: 10px;
    padding: 6px;
    margin: 2px 0;
}}
QListWidget::item:hover {{
    background: #10FFFFFF;
    color: {TEXT};
}}
QListWidget::item:selected {{
    background: #1AF0C47C;
    border: 1px solid #59E6B567;
    color: {TEXT};
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: #26FFFFFF;
    border-radius: 3px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{
    background: #38FFFFFF;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
    height: 0;
}}
QMenu {{
    background: #14161A;
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 6px;
    color: {TEXT};
}}
QMenu::item {{
    padding: 7px 28px 7px 14px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background: {ACCENT_SOFT};
    color: {TEXT};
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 5px 8px;
}}
QToolTip {{
    background: #14161A;
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 5px 9px;
}}
QPushButton {{
    background: #16FFFFFF;
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 9px 18px;
}}
QPushButton:hover {{
    background: #22FFFFFF;
}}
QPushButton#Primary {{
    background: {ACCENT};
    color: {ACCENT_TEXT};
    border: none;
    font-weight: 600;
}}
QPushButton#Primary:hover {{
    background: {ACCENT_HOVER};
}}
QMessageBox {{
    background: {SURFACE};
}}
"""


def apply_theme(app) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)

    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(SURFACE))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(SURFACE_HI))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(SURFACE))
    pal.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(SURFACE_HI))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(ACCENT_TEXT))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor("#14161A"))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(MUTED))
    app.setPalette(pal)

    font = QFont()
    font.setFamilies(["Segoe UI Variable Text", "Microsoft YaHei UI", "Segoe UI"])
    font.setPointSizeF(10)
    app.setFont(font)


def colorref(hex_color: str) -> int:
    """#RRGGBB -> Windows COLORREF (0x00BBGGRR)."""
    value = hex_color.lstrip("#")
    r, g, b = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    return (b << 16) | (g << 8) | r
