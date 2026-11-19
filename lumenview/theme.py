"""System appearance and quiet sage surfaces."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette
BG, CANVAS, SURFACE, SURFACE_HI, BORDER = '#F6F6F4', '#F6F6F4', '#FFFFFF', '#E9EDEA', '#E5E7E5'
TEXT, MUTED, DIM = '#242629', '#737675', '#737675'
ACCENT, ACCENT_HOVER, ACCENT_TEXT, ACCENT_SOFT = '#3B6552', '#477B63', '#FFFFFF', '#E9EDEA'

def apply_theme(app, dark=None):
    global BG, CANVAS, SURFACE, SURFACE_HI, BORDER, TEXT, MUTED, DIM, ACCENT, ACCENT_HOVER, ACCENT_TEXT, ACCENT_SOFT
    if dark is None:
        dark = app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    BG, SURFACE, SURFACE_HI, BORDER, TEXT, MUTED, ACCENT, ACCENT_HOVER, ACCENT_TEXT = (
        ('#171819', '#212325', '#303A35', '#35383A', '#EFEFED', '#A4AAA7', '#B5D7C2', '#CCE7D6', '#193727') if dark else
        ('#F6F6F4', '#FFFFFF', '#E9EDEA', '#E5E7E5', '#242629', '#737675', '#3B6552', '#477B63', '#FFFFFF'))
    CANVAS, DIM, ACCENT_SOFT = BG, MUTED, SURFACE_HI
    app.setStyle('Fusion')
    palette = QPalette()
    for role, value in ((QPalette.ColorRole.Window, BG), (QPalette.ColorRole.WindowText, TEXT), (QPalette.ColorRole.Base, SURFACE),
                        (QPalette.ColorRole.Text, TEXT), (QPalette.ColorRole.Button, SURFACE), (QPalette.ColorRole.ButtonText, TEXT),
                        (QPalette.ColorRole.Highlight, ACCENT), (QPalette.ColorRole.HighlightedText, ACCENT_TEXT),
                        (QPalette.ColorRole.ToolTipBase, SURFACE), (QPalette.ColorRole.ToolTipText, TEXT), (QPalette.ColorRole.PlaceholderText, MUTED)):
        palette.setColor(role, QColor(value))
    app.setPalette(palette)
    font = QFont(); font.setFamilies(['Segoe UI Variable Text', 'Microsoft YaHei UI', 'Inter', 'Segoe UI']); font.setPointSizeF(10)
    app.setFont(font)
    app.setStyleSheet(f'''
    * {{ color: {TEXT}; font-size: 10pt; }}
    QMainWindow, QWidget#Root, QWidget#CanvasArea, QWidget#MessagePage {{ background: {BG}; }}
    QWidget#TopBar, QScrollArea#Editor, QFrame#EditorContent, QWidget#Timeline {{ background: {SURFACE}; }}
    QWidget#TopBar {{ border-bottom: 1px solid {BORDER}; }}
    QLabel#Brand {{ font-size: 17pt; font-weight: 500; }}
    QLabel#EditorTitle, QLabel#ErrorTitle {{ font-size: 14pt; font-weight: 500; }}
    QLabel#Hint, QLabel#PillMeta, QLabel#Zoom, QLabel#BrandSub {{ color: {MUTED}; font-size: 9pt; }}
    QPushButton, QToolButton {{ background: transparent; border: none; border-radius: 10px; padding: 9px 13px; }}
    QPushButton:hover, QToolButton:hover, QPushButton:checked, QToolButton:checked {{ background: {SURFACE_HI}; }}
    QPushButton:disabled, QToolButton:disabled {{ color: {MUTED}; }}
    QPushButton#Primary {{ background: {ACCENT}; color: {ACCENT_TEXT}; font-weight: 500; }}
    QPushButton#Primary:hover {{ background: {ACCENT_HOVER}; }}
    QPushButton:focus, QToolButton:focus {{ border: 1px solid {ACCENT}; }}
    QFrame#Rail {{ background: {SURFACE}; border-radius: 12px; }}
    QScrollArea#Editor {{ border: none; border-left: 1px solid {BORDER}; }}
    QPushButton#FrameThumb {{ background: {BG}; border: 2px solid {BORDER}; border-radius: 10px; padding: 4px; }}
    QPushButton#FrameThumb:hover {{ border-color: {ACCENT}; }}
    QPushButton#FrameThumb:checked {{ border-color: {ACCENT}; background: {ACCENT_SOFT}; }}
    QListWidget {{ background: transparent; border: none; }}
    QListWidget::item {{ padding: 6px; margin: 2px; border-radius: 8px; }}
    QListWidget::item:selected {{ background: {SURFACE_HI}; }}
    QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{ background: {SURFACE}; border: 1px solid {MUTED}; border-radius: 9px; padding: 8px 12px; min-height: 22px; selection-background-color: {ACCENT}; selection-color: {ACCENT_TEXT}; }}
    QComboBox:hover, QLineEdit:hover {{ border-color: {ACCENT}; }}
    QComboBox:focus, QLineEdit:focus {{ border: 2px solid {ACCENT}; background: {BG}; }}
    QComboBox:disabled, QLineEdit:disabled {{ color: {MUTED}; background: {SURFACE_HI}; border-color: {BORDER}; }}
    QComboBox::drop-down {{ border: none; width: 32px; }}
    QComboBox::down-arrow {{ image: none; border: none; }}
    QComboBox QAbstractItemView {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER}; selection-background-color: {ACCENT}; selection-color: {ACCENT_TEXT}; padding: 5px; outline: none; }}
    QPushButton#CanvasNav {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 18px; font-size: 18pt; padding: 0; }}
    QPushButton#CanvasNav:hover {{ background: {SURFACE_HI}; border-color: {ACCENT}; }}
    QPushButton#CanvasNav:pressed {{ background: {ACCENT}; color: {ACCENT_TEXT}; }}
    QPushButton#CanvasNav:disabled {{ color: {MUTED}; background: {SURFACE_HI}; }}
    QFrame#SegmentedControl {{ background: {SURFACE_HI}; border: none; border-radius: 11px; }}
    QPushButton#SegmentedButton {{ color: {MUTED}; border: none; border-radius: 8px; padding: 6px 10px; min-height: 18px; }}
    QPushButton#SegmentedButton:hover {{ background: {BG}; color: {TEXT}; }}
    QPushButton#SegmentedButton:checked {{ background: {ACCENT}; color: {ACCENT_TEXT}; }}
    QFrame#TimeField {{ background: {BG}; border: 1px solid {BORDER}; border-radius: 11px; }}
    QLabel#TimeFieldLabel {{ color: {MUTED}; font-size: 8.5pt; }}
    QFrame#TimeField {{ background: {SURFACE_HI}; border: none; border-radius: 11px; }}
    QLabel#TimeFieldLabel, QLabel#TimeFieldUnit {{ color: {MUTED}; font-size: 9pt; }}
    QLineEdit#TimeInput {{ background: transparent; border: none; border-radius: 0; padding: 0; min-height: 24px; font-size: 11pt; font-weight: 500; }}
    QLineEdit#TimeInput:focus {{ color: {ACCENT}; }}
    QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: {ACCENT}; width: 14px; margin: -5px 0; border-radius: 7px; }}
    QMenu, QToolTip {{ background: {SURFACE}; border: 1px solid {BORDER}; padding: 6px; }}
    QMenu::item {{ padding: 8px 24px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {SURFACE_HI}; }}
    QScrollBar:vertical {{ background: transparent; width: 8px; }}
    QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 24px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    ''')

def colorref(hex_color):
    value = hex_color.lstrip('#')
    r, g, b = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    return (b << 16) | (g << 8) | r
