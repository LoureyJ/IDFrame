"""Qt appearance uses existing IDFrame colors and persists the same preferences."""

from PySide6.QtGui import QPalette, QColor, QFont
from PySide6.QtWidgets import QApplication

from ui_theme import PALETTES, load_theme, save_theme


def apply_theme(name):
    """Change colors once without rebuilding widgets, images, or AI state."""
    colors = PALETTES.get(name, PALETTES["Light"])
    application = QApplication.instance()
    palette = QPalette()
    for role, key in [
        (QPalette.ColorRole.Window, "app"),
        (QPalette.ColorRole.WindowText, "text"),
        (QPalette.ColorRole.Base, "card"),
        (QPalette.ColorRole.AlternateBase, "preview"),
        (QPalette.ColorRole.Text, "text"),
        (QPalette.ColorRole.Button, "field"),
        (QPalette.ColorRole.ButtonText, "text"),
        (QPalette.ColorRole.Highlight, "accent"),
        (QPalette.ColorRole.HighlightedText, "accent_text"),
        (QPalette.ColorRole.PlaceholderText, "muted"),
    ]:
        palette.setColor(role, QColor(colors[key]))
    application.setPalette(palette)
    application.setFont(QFont("Segoe UI", 10))
    application.setStyleSheet(f"""
        QWidget {{ color: {colors['text']}; }}
        QFrame[card="true"] {{ background: {colors['card']}; border: 1px solid {colors['border']}; border-radius: 14px; }}
        QLabel {{ background: transparent; }}
        QPushButton {{ background: {colors['field']}; border: 1px solid {colors['border']}; border-radius: 10px; padding: 10px 16px; }}
        QPushButton:hover {{ background: {colors['selection']}; }}
        QPushButton:focus, QRadioButton:focus {{ border: 1px solid {colors['accent']}; }}
        QPushButton:disabled {{ color: {colors['disabled_text']}; background: {colors['disabled']}; }}
        QPushButton[accent="true"] {{ background: {colors['accent']}; color: {colors['accent_text']}; font-weight: 600; }}
        QPushButton[accent="true"]:disabled {{ background: {colors['disabled']}; color: {colors['disabled_text']}; }}
        QPushButton:checked {{ background: {colors['selection']}; border-color: {colors['accent']}; }}
        QRadioButton {{ padding: 7px; border: 1px solid transparent; border-radius: 9px; }}
        QRadioButton:checked {{ background: {colors['selection']}; }}
        QRadioButton::indicator {{ width: 15px; height: 15px; border-radius: 8px; border: 2px solid {colors['muted']}; background: {colors['card']}; }}
        QRadioButton::indicator:checked {{ background: {colors['accent']}; border-color: {colors['accent']}; }}
        QSlider::groove:horizontal {{ height: 4px; background: {colors['border']}; border-radius: 2px; }}
        QSlider::handle:horizontal {{ width: 16px; margin: -6px 0; border-radius: 8px; background: {colors['accent']}; }}
        QLineEdit, QListWidget, QTextBrowser {{ background: {colors['card']}; border: 1px solid {colors['border']}; border-radius: 8px; padding: 6px; }}
        QScrollArea {{ border: none; background: transparent; }}
        QProgressBar {{ border: none; border-radius: 3px; background: {colors['field']}; max-height: 6px; }}
        QProgressBar::chunk {{ background: {colors['accent']}; border-radius: 3px; }}
    """)


__all__ = ["apply_theme", "load_theme", "save_theme"]
