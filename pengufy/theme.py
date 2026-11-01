"""Night blue colours (from the Gece desktop) and the application style sheet."""

from PyQt6.QtGui import QColor, QPalette

WINDOW = "#070a0f"   # gaps between the panels
PANEL = "#0f141c"    # sidebar, main area, side panel
SURFACE = "#141a24"  # player bar, inputs
CARD = "#18202b"     # hovered cards and rows
HOVER = "#1f2836"
LINE = "#263142"
LINE2 = "#3a4a66"
TEXT = "#d8e0ea"
DIM = "#8b97a8"
ACCENT = "#7aa8ff"
GREEN = "#3ddc84"   # Pengufy logo; used sparingly
ACCENT_DARK = "#5b8ef0"
ON_ACCENT = "#0b1018"

STYLE = f"""
* {{ outline: none; }}
QWidget {{ color: {TEXT}; font-size: 10pt; }}
QMainWindow, #root {{ background: {WINDOW}; }}
#panel {{ background: {PANEL}; border-radius: 10px; }}
#playerBar {{ background: {WINDOW}; }}
QToolTip {{ background: {CARD}; color: {TEXT}; border: 1px solid {LINE}; padding: 4px 6px; }}

QScrollArea, QScrollArea > QWidget > QWidget, #page {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: {LINE}; border-radius: 3px; min-height: 30px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: {LINE2}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    background: none; width: 0; height: 0; }}

QLineEdit {{
    background: {SURFACE}; border: 1px solid {LINE}; border-radius: 19px; padding: 8px 16px 8px 38px;
    selection-background-color: {ACCENT}; selection-color: {ON_ACCENT}; }}
QLineEdit:hover {{ border-color: {LINE2}; background: {CARD}; }}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QLineEdit#plain {{ padding-left: 14px; }}

QToolButton {{ background: transparent; border: none; border-radius: 6px; padding: 4px; }}
QToolButton:hover {{ background: {CARD}; }}
QToolButton#round {{ border-radius: 16px; background: {SURFACE}; }}
QToolButton#round:hover {{ background: {HOVER}; }}
QToolButton#play {{ background: {TEXT}; border-radius: 18px; }}
QToolButton#play:hover {{ background: #ffffff; }}
QToolButton#bigPlay {{ background: {ACCENT}; border-radius: 26px; }}
QToolButton#bigPlay:hover {{ background: #9bbdff; }}

QPushButton {{
    background: transparent; border: 1px solid {LINE2}; border-radius: 16px; padding: 6px 16px; font-weight: 600; }}
QPushButton:hover {{ border-color: {TEXT}; }}
QPushButton:checked {{ background: {TEXT}; color: {ON_ACCENT}; border-color: {TEXT}; }}
QPushButton#accent {{ background: {ACCENT}; color: {ON_ACCENT}; border: none; border-radius: 16px; padding: 8px 22px; }}
QPushButton#accent:hover {{ background: #9bbdff; }}
QPushButton#accent:disabled {{ background: {CARD}; color: {DIM}; }}
QPushButton#nav {{
    border: none; border-radius: 6px; text-align: left; padding: 9px 12px; font-size: 11pt; color: {DIM}; }}
QPushButton#nav:hover {{ color: {TEXT}; background: {CARD}; }}
QPushButton#nav:checked {{ color: {TEXT}; background: {CARD}; }}
QPushButton#chip {{ border: none; background: {CARD}; padding: 6px 14px; font-weight: 500; }}
QPushButton#chip:hover {{ background: {HOVER}; }}
QPushButton#chip:checked {{ background: {TEXT}; color: {ON_ACCENT}; }}

QSlider {{ min-height: 16px; background: transparent; }}
QSlider::groove:horizontal {{ height: 4px; background: {LINE}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ height: 4px; background: {TEXT}; border-radius: 2px; }}
QSlider::sub-page:horizontal:hover {{ background: {ACCENT}; }}
QSlider::sub-page:horizontal:disabled {{ background: {LINE}; }}
QSlider::handle:horizontal {{ width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; background: transparent; }}
QSlider::handle:horizontal:hover {{ background: #ffffff; }}

QListWidget, QTableView {{ background: transparent; border: none; }}
QTableView {{ selection-background-color: {HOVER}; selection-color: {TEXT}; }}
QTableView::item {{ border: none; padding: 0 8px; }}
QTableView::item:hover {{ background: {CARD}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{
    background: transparent; color: {DIM}; border: none; border-bottom: 1px solid {LINE};
    padding: 6px 8px; font-size: 9pt; }}
QListWidget::item {{ border-radius: 6px; padding: 6px 8px; }}
QListWidget::item:hover {{ background: {CARD}; }}
QListWidget::item:selected {{ background: {HOVER}; color: {TEXT}; }}

QMenu {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 7px 24px 7px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {HOVER}; }}
QMenu::item:disabled {{ color: {DIM}; }}
QMenu::separator {{ height: 1px; background: {LINE}; margin: 4px 6px; }}

QLabel#h1 {{ font-size: 30pt; font-weight: 800; }}
QLabel#h2 {{ font-size: 16pt; font-weight: 700; }}
QLabel#h3 {{ font-size: 11pt; font-weight: 700; }}
QLabel#dim {{ color: {DIM}; }}
QLabel#small {{ color: {DIM}; font-size: 9pt; }}
QLabel#link {{ color: {DIM}; }}
QLabel#link:hover {{ color: {TEXT}; text-decoration: underline; }}
"""


def palette() -> QPalette:
    pal = QPalette()
    for role, color in ((QPalette.ColorRole.Window, PANEL), (QPalette.ColorRole.WindowText, TEXT),
                        (QPalette.ColorRole.Base, SURFACE), (QPalette.ColorRole.AlternateBase, CARD),
                        (QPalette.ColorRole.Text, TEXT), (QPalette.ColorRole.Button, CARD),
                        (QPalette.ColorRole.ButtonText, TEXT), (QPalette.ColorRole.Highlight, ACCENT),
                        (QPalette.ColorRole.HighlightedText, ON_ACCENT), (QPalette.ColorRole.PlaceholderText, DIM),
                        (QPalette.ColorRole.ToolTipBase, CARD), (QPalette.ColorRole.ToolTipText, TEXT),
                        (QPalette.ColorRole.Link, ACCENT)):
        pal.setColor(role, QColor(color))
    return pal
