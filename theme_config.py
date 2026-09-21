"""
theme_config.py - Light Theme Only & High-DPI Manager for Image Viewer.

Applies enterprise Light Theme exclusively to UI controls (window, menus,
toolbars, scrollbars, adjustment sidebar, tabs, dialogs) without altering
the original displayed image appearance.
"""

import os
import sys
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

if getattr(sys, 'frozen', False):
    BASE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ICO_PATH = os.path.join(BASE_DIR, "Swift_Prosys.ico")


def setup_high_dpi():
    """Configure PyQt6 high-DPI auto-scaling settings."""
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except AttributeError:
        pass


def get_app_icon() -> QIcon:
    """Return QIcon loaded from Swift_Prosys.ico."""
    if os.path.exists(ICO_PATH):
        return QIcon(ICO_PATH)
    return QIcon()


def get_light_stylesheet() -> str:
    """Return enterprise Light Theme stylesheet affecting ONLY the UI controls."""
    return """
        /* Main Window & Dialogs */

        QMainWindow, QDialog {
            background-color: #f8fafc;
            color: #0f172a;
            font-family: 'Segoe UI', 'Segoe UI Emoji', 'Apple Color Emoji', 'Noto Color Emoji', Arial, sans-serif;
        }

        QWidget {
            font-family: 'Segoe UI', 'Segoe UI Emoji', 'Apple Color Emoji', 'Noto Color Emoji', Arial, sans-serif;
            font-size: 12px;
            color: #0f172a;
        }

        /* Menu Bar */
        QMenuBar {
            background-color: #ffffff;
            color: #0f172a;
            border-bottom: 1px solid #cbd5e1;
            font-weight: 600;
        }
        QMenuBar::item {
            background-color: transparent;
            padding: 5px 10px;
        }
        QMenuBar::item:selected {
            background-color: #0284c7;
            color: #ffffff;
            border-radius: 4px;
        }
        QMenu {
            background-color: #ffffff;
            color: #0f172a;
            border: 1px solid #cbd5e1;
            padding: 4px;
        }
        QMenu::item {
            padding: 6px 20px;
        }
        QMenu::item:selected {
            background-color: #0284c7;
            color: #ffffff;
            border-radius: 4px;
        }
        QMenu::separator {
            height: 1px;
            background: #cbd5e1;
            margin: 4px 8px;
        }

        /* Toolbars */
        QToolBar {
            background-color: #f1f5f9;
            border-bottom: 1px solid #cbd5e1;
            spacing: 3px;
            padding: 3px 6px;
        }
        QToolBar#LeftToolBar {
            background-color: #e2e8f0;
            border-right: 1px solid #cbd5e1;
            border-bottom: none;
            padding: 6px 3px;
            spacing: 6px;
        }
        QToolButton {
            background-color: #ffffff;
            color: #0f172a;
            border: 1px solid #cbd5e1;
            border-radius: 4px;
            padding: 4px 8px;
            font-weight: 600;
            font-family: 'Segoe UI', 'Segoe UI Emoji', 'Apple Color Emoji', 'Noto Color Emoji', Arial, sans-serif;
        }
        QToolButton:hover {
            background-color: #e2e8f0;
            border-color: #0284c7;
        }
        QToolButton:pressed, QToolButton:checked {
            background-color: #0284c7;
            color: #ffffff;
        }

        /* Toolbar Overflow Extension Button (3 Dots / More Actions) */
        QToolBarExtension, QToolButton#qt_toolbar_ext_button {
            background-color: #ffffff;
            color: #334155;
            border: 1px solid #cbd5e1;
            border-radius: 4px;
            padding: 2px 6px;
            font-size: 14px;
            font-weight: bold;
            min-width: 24px;
            min-height: 22px;
            qproperty-text: "...";
        }
        QToolBarExtension:hover, QToolButton#qt_toolbar_ext_button:hover {
            background-color: #e2e8f0;
            border-color: #0284c7;
            color: #0284c7;
        }

        /* Action Buttons on Toolbar */
        QToolButton#btn_save {
            background-color: #ffffff;
            color: #0284c7;
            border: 1px solid #0284c7;
            font-weight: bold;
        }
        QToolButton#btn_save:hover {
            background-color: #e0f2fe;
            border-color: #0369a1;
        }
        QToolButton#btn_save[modified="true"] {
            background-color: #0284c7;
            color: #ffffff;
            border: 1px solid #0369a1;
            font-weight: bold;
        }
        QToolButton#btn_save[modified="true"]:hover {
            background-color: #0369a1;
        }
        QToolButton#btn_discard {
            background-color: #ffffff;
            color: #d97706;
            border: 1px solid #fcd34d;
        }
        QToolButton#btn_discard:hover {
            background-color: #fef3c7;
            border-color: #b45309;
            color: #b45309;
        }
        QToolButton#btn_delete {
            background-color: #ffffff;
            color: #ef4444;
            border: 1px solid #fca5a5;
            font-weight: bold;
        }
        QToolButton#btn_delete:hover {
            background-color: #fee2e2;
            border-color: #dc2626;
            color: #dc2626;
        }

        /* Status Bar */
        QStatusBar {
            background-color: #e2e8f0;
            color: #334155;
            border-top: 1px solid #cbd5e1;
            font-size: 11px;
            padding: 2px 8px;
        }

        /* Tabs & Adjustment Sidebar Panels */
        QFrame#AdjustmentSidebar {
            background-color: #f8fafc;
            border-left: 1px solid #cbd5e1;
        }

        QTabWidget::pane {
            border: 1px solid #cbd5e1;
            background-color: #ffffff;
            border-radius: 6px;
        }
        QTabBar::tab {
            background-color: #e2e8f0;
            color: #475569;
            padding: 8px 14px;
            font-weight: 700;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            margin-right: 2px;
            border: 1px solid #cbd5e1;
            border-bottom: none;
        }
        QTabBar::tab:selected {
            background-color: #0284c7;
            color: #ffffff;
            border-color: #0284c7;
        }
        QTabBar::tab:hover:!selected {
            background-color: #cbd5e1;
            color: #0f172a;
        }

        QGroupBox {
            font-weight: 700;
            font-size: 12px;
            border: 1px solid #cbd5e1;
            border-radius: 6px;
            margin-top: 10px;
            padding-top: 10px;
            background-color: #ffffff;
            color: #0f172a;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 2px 6px;
            color: #0284c7;
            background-color: #ffffff;
        }

        /* Buttons */
        QPushButton {
            background-color: #ffffff;
            color: #0f172a;
            border: 1px solid #cbd5e1;
            border-radius: 5px;
            padding: 6px 14px;
            font-weight: 600;
        }
        QPushButton:hover {
            background-color: #e2e8f0;
            border-color: #0284c7;
        }
        QPushButton:pressed {
            background-color: #0284c7;
            color: #ffffff;
        }
        QPushButton.btn-primary {
            background-color: #0284c7;
            color: #ffffff;
            border: 1px solid #0369a1;
            font-weight: 700;
        }
        QPushButton.btn-primary:hover {
            background-color: #0369a1;
        }
        QPushButton.btn-danger {
            background-color: #ef4444;
            color: #ffffff;
            border: 1px solid #dc2626;
        }
        QPushButton.btn-danger:hover {
            background-color: #dc2626;
        }

        /* Modern Light Scrollbars */
        QScrollBar:vertical, QScrollBar:horizontal {
            background-color: #f1f5f9;
            border: none;
            width: 10px;
            height: 10px;
            margin: 0px;
            border-radius: 5px;
        }
        QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
            background-color: #cbd5e1;
            min-height: 20px;
            min-width: 20px;
            border-radius: 5px;
        }
        QScrollBar::handle:hover {
            background-color: #0284c7;
        }
        QScrollBar::add-line, QScrollBar::sub-line {
            width: 0px;
            height: 0px;
        }

        /* Sliders */
        QSlider::groove:horizontal {
            height: 6px;
            background: #cbd5e1;
            border-radius: 3px;
        }
        QSlider::sub-page:horizontal {
            background: #0284c7;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: #ffffff;
            border: 2px solid #0284c7;
            width: 16px;
            margin-top: -5px;
            margin-bottom: -5px;
            border-radius: 8px;
        }

        /* Inputs & Spinboxes */
        QDoubleSpinBox, QSpinBox, QLineEdit {
            background-color: #ffffff;
            color: #0f172a;
            border: 1px solid #cbd5e1;
            border-radius: 4px;
            padding: 4px 6px;
            selection-background-color: #0284c7;
        }
        QDoubleSpinBox:focus, QSpinBox:focus, QLineEdit:focus {
            border: 1px solid #0284c7;
        }
        QDoubleSpinBox::up-button, QSpinBox::up-button,
        QDoubleSpinBox::down-button, QSpinBox::down-button {
            width: 0px;
            height: 0px;
            border: none;
        }
        QDoubleSpinBox::up-arrow, QSpinBox::up-arrow,
        QDoubleSpinBox::down-arrow, QSpinBox::down-arrow {
            image: none;
        }
    """


def get_theme_stylesheet(theme_name: str = "Light") -> str:
    """Compatibility alias returning Light Theme stylesheet."""
    return get_light_stylesheet()

