"""
adjustment_sidebar.py - Right-Side Image Adjustment Sidebar (Ctrl + L).

Matches the structure of a classic photo-editor edit panel, with four tabs:
1. Auto Exposure  - one-click automatic contrast/brightness correction
2. Brightness     - Brightness, Contrast, Gamma sliders + Grayscale toggle
3. Levels         - Shadows/Midtones/Highlights (black point, gamma, white point) + RGB Channels
4. Curves         - interactive tone curve editor (drag points on the graph) + RGB Channels

Plus a Global Bottom Action Footer Bar (Cancel button).
"""

import sys
import copy
from typing import Dict, Any, Optional, List, Tuple
import numpy as np

from PyQt6.QtCore import Qt, pyqtSignal, QPointF, QRectF
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QPixmap, QImage
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
    QTabWidget, QGroupBox, QSpinBox, QDoubleSpinBox, QFrame, QComboBox,
    QAbstractSpinBox, QCheckBox, QRadioButton, QButtonGroup, QScrollArea
)


class GradientSlider(QSlider):
    """Custom slider with blue-white gradient track matching reference screenshot."""

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 16px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #a5b4fc, stop:0.6 #c7d2fe, stop:1 #ffffff);
                border: 1px solid #cbd5e1;
                border-radius: 4px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #38bdf8);
                border: 1px solid #0284c7;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                width: 14px;
                margin-top: -3px;
                margin-bottom: -3px;
                border-radius: 4px;
                background-color: #ffffff;
                border: 2px solid #0284c7;
            }
            QSlider::handle:horizontal:hover {
                background-color: #f0f9ff;
                border-color: #0369a1;
            }
        """)


class CurveEditor(QWidget):
    """
    Interactive tone-curve editor. Click-drag on the graph to add/move
    points. Double-click to remove an interior point. Emits curve_changed
    on edit.
    """

    curve_changed = pyqtSignal()
    drag_started = pyqtSignal()
    drag_ended = pyqtSignal()

    _DEFAULT_POINTS = [(0, 0), (255, 255)]
    _HIT_RADIUS = 9

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(260, 200)
        self.setStyleSheet("background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 4px;")
        self.points: List[Tuple[int, int]] = list(self._DEFAULT_POINTS)
        self._dragging_index: Optional[int] = None
        self.channel: str = "RGB"
        self.channel_color: QColor = QColor("#0284c7")
        self.hist_data: Optional[np.ndarray] = None
        self.show_histogram: bool = True
        self.setMouseTracking(True)

    def is_identity(self) -> bool:
        return self.points == self._DEFAULT_POINTS

    def reset(self):
        self.points = list(self._DEFAULT_POINTS)
        self._dragging_index = None
        self.update()
        self.curve_changed.emit()

    def set_channel(self, channel: str, points: List[Tuple[int, int]]):
        self.channel = channel
        self.points = list(points)
        colors = {
            "RGB": QColor("#0284c7"),
            "Red": QColor("#ef4444"),
            "Green": QColor("#16a34a"),
            "Blue": QColor("#2563eb"),
        }
        self.channel_color = colors.get(channel, QColor("#0284c7"))
        self.update()

    def set_histogram(self, hist: Optional[np.ndarray]):
        self.hist_data = hist
        self.update()

    def get_lut(self) -> Optional[np.ndarray]:
        """Returns a 256-entry uint8 LUT, or None if the curve is identity (no-op)."""
        if self.is_identity():
            return None
        xs = np.array([p[0] for p in self.points], dtype=np.float64)
        ys = np.array([p[1] for p in self.points], dtype=np.float64)
        domain = np.arange(256, dtype=np.float64)
        lut = np.interp(domain, xs, ys)
        return np.clip(lut, 0, 255).astype(np.uint8)

    # -- geometry helpers -------------------------------------------------
    def _plot_rect(self) -> QRectF:
        m = 10
        return QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)

    def _to_widget(self, x: int, y: int) -> QPointF:
        r = self._plot_rect()
        px = r.left() + (x / 255.0) * r.width()
        py = r.bottom() - (y / 255.0) * r.height()
        return QPointF(px, py)

    def _to_curve(self, pos: QPointF) -> Tuple[int, int]:
        r = self._plot_rect()
        x = (pos.x() - r.left()) / max(1.0, r.width()) * 255.0
        y = (r.bottom() - pos.y()) / max(1.0, r.height()) * 255.0
        return int(round(max(0, min(255, x)))), int(round(max(0, min(255, y))))

    # -- painting -----------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self._plot_rect()

        # Grid
        painter.setPen(QPen(QColor("#e2e8f0"), 1))
        for i in range(1, 4):
            gx = r.left() + r.width() * i / 4.0
            gy = r.top() + r.height() * i / 4.0
            painter.drawLine(QPointF(gx, r.top()), QPointF(gx, r.bottom()))
            painter.drawLine(QPointF(r.left(), gy), QPointF(r.right(), gy))
        painter.setPen(QPen(QColor("#94a3b8"), 1))
        painter.drawRect(r)

        # Optional histogram background
        if self.show_histogram and self.hist_data is not None and len(self.hist_data) == 256:
            max_val = np.max(self.hist_data)
            if max_val > 0:
                hist_col = QColor(self.channel_color)
                hist_col.setAlpha(45)
                w_bar = r.width() / 256.0
                scaled_hist = np.log1p(self.hist_data) / np.log1p(max_val)
                for i in range(256):
                    h_bar = float(scaled_hist[i]) * r.height()
                    if h_bar > 0:
                        bx = r.left() + i * w_bar
                        by = r.bottom() - h_bar
                        painter.fillRect(QRectF(bx, by, max(1.0, w_bar), h_bar), hist_col)

        # Reference diagonal (identity line)
        painter.setPen(QPen(QColor("#cbd5e1"), 1, Qt.PenStyle.DashLine))
        painter.drawLine(self._to_widget(0, 0), self._to_widget(255, 255))

        # Curve line
        pts_sorted = sorted(self.points, key=lambda p: p[0])
        painter.setPen(QPen(self.channel_color, 2))
        for i in range(len(pts_sorted) - 1):
            painter.drawLine(self._to_widget(*pts_sorted[i]), self._to_widget(*pts_sorted[i + 1]))

        # Control points
        for idx, (x, y) in enumerate(pts_sorted):
            wp = self._to_widget(x, y)
            painter.setBrush(QBrush(self.channel_color))
            painter.setPen(QPen(QColor("#ffffff"), 1.5))
            painter.drawEllipse(wp, 5, 5)

    # -- mouse interaction ----------------------------------------------
    def _find_point_near(self, pos: QPointF) -> Optional[int]:
        for idx, (x, y) in enumerate(self.points):
            wp = self._to_widget(x, y)
            if (wp - pos).manhattanLength() <= self._HIT_RADIUS:
                return idx
        return None

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.drag_started.emit()
        idx = self._find_point_near(event.position())
        if idx is None:
            cx, cy = self._to_curve(event.position())
            self.points.append((cx, cy))
            self.points.sort(key=lambda p: p[0])
            idx = self.points.index((cx, cy))
        self._dragging_index = idx
        self.update()

    def mouseMoveEvent(self, event):
        if self._dragging_index is None:
            return
        cx, cy = self._to_curve(event.position())
        idx = self._dragging_index

        if idx == 0:
            cx = 0
        elif idx == len(self.points) - 1:
            cx = 255

        self.points[idx] = (cx, cy)
        self.points.sort(key=lambda p: p[0])
        self._dragging_index = self.points.index((cx, cy)) if (cx, cy) in self.points else idx
        self.update()
        self.curve_changed.emit()

    def mouseReleaseEvent(self, event):
        if self._dragging_index is not None:
            self._dragging_index = None
            self.drag_ended.emit()

    def mouseDoubleClickEvent(self, event):
        idx = self._find_point_near(event.position())
        if idx is not None and 0 < idx < len(self.points) - 1:
            self.drag_started.emit()
            self.points.pop(idx)
            self.update()
            self.curve_changed.emit()
            self.drag_ended.emit()


class LevelsHistogramWidget(QWidget):
    """
    ACDSee-style interactive Levels histogram with transfer curve and
    draggable Black/Gray/White triangle slider handles.
    """

    levels_changed = pyqtSignal(int, float, int)  # shadows, midtones, highlights
    drag_started = pyqtSignal()
    drag_ended = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(260, 115)
        self.setFixedHeight(115)
        self.setStyleSheet("background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 4px;")

        self.shadows: int = 0
        self.midtones: float = 1.00
        self.highlights: int = 255
        self.channel: str = "Luminance"
        self.hist_data: Optional[np.ndarray] = None
        self._dragging_handle: Optional[str] = None
        self.setMouseTracking(True)

    def set_levels(self, shadows: int, midtones: float, highlights: int):
        self.shadows = max(0, min(250, shadows))
        self.midtones = max(0.10, min(9.99, midtones))
        self.highlights = max(self.shadows + 1, min(255, highlights))
        self.update()

    def set_histogram(self, hist: Optional[np.ndarray], channel: str = "Luminance"):
        self.hist_data = hist
        self.channel = channel
        self.update()

    def _graph_rect(self) -> QRectF:
        m = 8
        return QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m - 14)

    def _slider_y(self) -> float:
        return self._graph_rect().bottom() + 1

    def _val_to_x(self, val: float) -> float:
        r = self._graph_rect()
        return r.left() + (val / 255.0) * r.width()

    def _x_to_val(self, x: float) -> float:
        r = self._graph_rect()
        val = (x - r.left()) / max(1.0, r.width()) * 255.0
        return max(0.0, min(255.0, val))

    def _midtone_val(self) -> float:
        ratio = 0.5 ** (1.0 / max(0.1, self.midtones))
        return self.shadows + (self.highlights - self.shadows) * ratio

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self._graph_rect()

        # Background
        painter.fillRect(r, QColor("#ffffff"))

        # Grid lines
        painter.setPen(QPen(QColor("#f1f5f9"), 1))
        for i in range(1, 4):
            gx = r.left() + r.width() * i / 4.0
            painter.drawLine(QPointF(gx, r.top()), QPointF(gx, r.bottom()))

        # Histogram bars
        if self.hist_data is not None and len(self.hist_data) == 256:
            max_val = np.max(self.hist_data)
            if max_val > 0:
                color_map = {
                    "Red": (QColor("#ef4444"), QColor(239, 68, 68, 160)),
                    "Green": (QColor("#16a34a"), QColor(22, 163, 74, 160)),
                    "Blue": (QColor("#2563eb"), QColor(37, 99, 235, 160)),
                    "Luminance": (QColor("#64748b"), QColor(100, 116, 139, 160)),
                }
                pen_col, brush_col = color_map.get(self.channel, (QColor("#64748b"), QColor(100, 116, 139, 160)))
                painter.setPen(pen_col)
                w_bar = r.width() / 256.0
                scaled_hist = np.log1p(self.hist_data) / np.log1p(max_val)
                for i in range(256):
                    h_bar = float(scaled_hist[i]) * r.height()
                    if h_bar > 0:
                        bx = r.left() + i * w_bar
                        by = r.bottom() - h_bar
                        painter.fillRect(QRectF(bx, by, max(1.0, w_bar), h_bar), brush_col)

        # Transfer curve
        painter.setPen(QPen(QColor("#0f172a"), 1.5))
        pts = []
        for xi in range(256):
            if xi <= self.shadows:
                yi = 0.0
            elif xi >= self.highlights:
                yi = 255.0
            else:
                norm = (xi - self.shadows) / max(1.0, float(self.highlights - self.shadows))
                yi = (norm ** (1.0 / self.midtones)) * 255.0
            px = self._val_to_x(xi)
            py = r.bottom() - (yi / 255.0) * r.height()
            pts.append(QPointF(px, py))
        for i in range(len(pts) - 1):
            painter.drawLine(pts[i], pts[i + 1])

        # Border
        painter.setPen(QPen(QColor("#cbd5e1"), 1))
        painter.drawRect(r)

        # Sliders below graph
        sy = self._slider_y()
        # 1. Black Triangle (Shadows)
        self._draw_triangle(painter, self._val_to_x(self.shadows), sy, QColor("#000000"))

        # 2. Gray Triangle (Midtones)
        self._draw_triangle(painter, self._val_to_x(self._midtone_val()), sy, QColor("#64748b"))

        # 3. White Triangle (Highlights)
        self._draw_triangle(painter, self._val_to_x(self.highlights), sy, QColor("#ffffff"), border=QColor("#000000"))

    def _draw_triangle(self, painter: QPainter, cx: float, top_y: float, fill_color: QColor, border: Optional[QColor] = None):
        w, h = 6, 9
        p1 = QPointF(cx, top_y)
        p2 = QPointF(cx - w, top_y + h)
        p3 = QPointF(cx + w, top_y + h)
        painter.setPen(QPen(border or fill_color, 1))
        painter.setBrush(QBrush(fill_color))
        painter.drawPolygon([p1, p2, p3])

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        sx = self._val_to_x(self.shadows)
        gx = self._val_to_x(self._midtone_val())
        hx = self._val_to_x(self.highlights)

        tol = 8
        if abs(pos.x() - sx) <= tol:
            self._dragging_handle = "black"
        elif abs(pos.x() - gx) <= tol:
            self._dragging_handle = "gray"
        elif abs(pos.x() - hx) <= tol:
            self._dragging_handle = "white"
        else:
            self._dragging_handle = None

        if self._dragging_handle:
            self.drag_started.emit()

    def mouseMoveEvent(self, event):
        if not self._dragging_handle:
            return
        val = self._x_to_val(event.position().x())
        if self._dragging_handle == "black":
            self.shadows = int(round(max(0, min(self.highlights - 5, val))))
        elif self._dragging_handle == "white":
            self.highlights = int(round(max(self.shadows + 5, min(255, val))))
        elif self._dragging_handle == "gray":
            denom = max(1.0, float(self.highlights - self.shadows))
            norm = (val - self.shadows) / denom
            norm = max(0.01, min(0.99, norm))
            gamma = np.log(0.5) / np.log(norm)
            self.midtones = float(np.clip(gamma, 0.10, 9.99))

        self.update()
        self.levels_changed.emit(self.shadows, round(self.midtones, 2), self.highlights)

    def mouseReleaseEvent(self, event):
        if self._dragging_handle:
            self._dragging_handle = None
            self.drag_ended.emit()


class ImageAdjustmentSidebar(QFrame):
    """Right-side image adjustments panel (Ctrl + L) matching ACDSee Edit Panel."""

    adjustments_changed = pyqtSignal()
    close_requested = pyqtSignal()
    save_requested = pyqtSignal()
    save_as_requested = pyqtSignal()
    discard_requested = pyqtSignal()
    apply_requested = pyqtSignal()
    done_requested = pyqtSignal()
    cancel_requested = pyqtSignal()
    undo_applied_requested = pyqtSignal()
    redo_applied_requested = pyqtSignal()
    eyedropper_mode_changed = pyqtSignal(object)  # emits 'black', 'gray', 'white', or None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(280)
        self.setMaximumWidth(480)
        self.setObjectName("AdjustmentSidebar")
        self.setStyleSheet("background-color: #f8fafc; font-family: 'Segoe UI', 'Segoe UI Emoji', Arial, sans-serif;")

        self._exposure_warning: bool = False
        self._warning_checkboxes: List[QCheckBox] = []
        self._undo_stack: List[Dict[str, Any]] = []
        self._redo_stack: List[Dict[str, Any]] = []
        self._pre_change_state: Optional[Dict[str, Any]] = None
        self._last_committed_state: Optional[Dict[str, Any]] = None
        self._can_undo_applied: bool = False
        self._can_redo_applied: bool = False

        self.levels_data: Dict[str, Dict[str, Any]] = {
            "Luminance": {"shadows": 0, "midtones": 1.00, "highlights": 255, "clip_black": 0.0, "clip_white": 0.0},
            "Red": {"shadows": 0, "midtones": 1.00, "highlights": 255, "clip_black": 0.0, "clip_white": 0.0},
            "Green": {"shadows": 0, "midtones": 1.00, "highlights": 255, "clip_black": 0.0, "clip_white": 0.0},
            "Blue": {"shadows": 0, "midtones": 1.00, "highlights": 255, "clip_black": 0.0, "clip_white": 0.0},
        }
        self._current_levels_channel: str = "Luminance"

        self.curves_data: Dict[str, List[Tuple[int, int]]] = {
            "RGB": [(0, 0), (255, 255)],
            "Red": [(0, 0), (255, 255)],
            "Green": [(0, 0), (255, 255)],
            "Blue": [(0, 0), (255, 255)],
        }
        self._current_curves_channel: str = "RGB"

        self.active_picker: Optional[str] = None
        self._cached_histograms: Dict[str, np.ndarray] = {}

        self._init_ui()
        self._last_committed_state = self.get_full_state()
        self._update_undo_redo_buttons()

    # ------------------------------------------------------------------
    def _wrap_in_scroll(self, widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; } QWidget#qt_scrollarea_viewport { background: transparent; }")
        scroll.setWidget(widget)
        return scroll

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame { background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 4px; padding: 4px 8px; }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(6, 4, 6, 4)
        title_lbl = QLabel("☀ Image Adjustments")
        title_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #0f172a;")
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        main_layout.addWidget(header_frame)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #cbd5e1; background: #ffffff; border-radius: 4px; top: -1px; }
            QTabBar::tab {
                background: #f1f5f9; border: 1px solid #cbd5e1; border-bottom: none;
                padding: 6px 12px; font-size: 11px; font-weight: 600; color: #475569;
                border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px;
            }
            QTabBar::tab:selected { background: #ffffff; color: #0284c7; border-bottom: 2px solid #0284c7; }
            QTabBar::tab:hover:!selected { background: #e2e8f0; }
        """)

        self._build_auto_exposure_tab()
        self._build_brightness_tab()
        self._build_levels_tab()
        self._build_curves_tab()

        main_layout.addWidget(self.tabs)

        # Footer matching ACDSee Edit Panel (Save, Save As, Discard, Apply, Done, Cancel, Undo, Redo)
        footer_frame = QFrame()
        footer_frame.setStyleSheet("QFrame { background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 4px; padding: 6px; }")
        footer_layout = QVBoxLayout(footer_frame)
        footer_layout.setContentsMargins(4, 4, 4, 4)
        footer_layout.setSpacing(6)

        # Row 1: Core ACDSee File Actions (Save, Save As, Discard)
        row_actions = QHBoxLayout()
        row_actions.setSpacing(6)

        self.btn_save = QPushButton("💾 Save")
        self.btn_save.setToolTip("Save Adjustments to Current File (Ctrl+S)")
        self.btn_save.setStyleSheet("""
            QPushButton { background-color: #0284c7; border: 1px solid #0369a1; border-radius: 4px; padding: 5px 10px; font-size: 11px; font-weight: bold; color: #ffffff; font-family: 'Segoe UI', 'Segoe UI Emoji', Arial, sans-serif; }
            QPushButton:hover { background-color: #0369a1; }
        """)
        self.btn_save.clicked.connect(self.save_requested.emit)

        self.btn_discard = QPushButton("↩ Discard")
        self.btn_discard.setToolTip("Discard Adjustments and Revert to Original (Ctrl+D)")
        self.btn_discard.setStyleSheet("""
            QPushButton { background-color: #fff7ed; border: 1px solid #fed7aa; border-radius: 4px; padding: 5px 10px; font-size: 11px; font-weight: 600; color: #c2410c; font-family: 'Segoe UI', 'Segoe UI Emoji', Arial, sans-serif; }
            QPushButton:hover { background-color: #ffedd5; border-color: #f97316; }
        """)
        self.btn_discard.clicked.connect(self.discard_requested.emit)

        self.btn_save_as = QPushButton("📁 Save As")
        self.btn_save_as.setToolTip("Save Image to New File (Ctrl+Shift+S)")
        self.btn_save_as.setStyleSheet("""
            QPushButton { background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 4px; padding: 5px 10px; font-size: 11px; font-weight: 600; color: #0f172a; font-family: 'Segoe UI', 'Segoe UI Emoji', Arial, sans-serif; }
            QPushButton:hover { background-color: #e2e8f0; border-color: #0284c7; }
        """)
        self.btn_save_as.clicked.connect(self.save_as_requested.emit)

        row_actions.addWidget(self.btn_save)
        row_actions.addWidget(self.btn_discard)
        row_actions.addWidget(self.btn_save_as)
        footer_layout.addLayout(row_actions)

        # Row 2: Apply, Done, Cancel
        row1 = QHBoxLayout()
        row1.setSpacing(6)

        self.btn_apply = QPushButton("Apply")
        self.btn_apply.setToolTip("Apply Adjustments to Image (ACDSee Apply)")
        self.btn_apply.setStyleSheet("""
            QPushButton { background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 4px; padding: 4px 10px; font-size: 11px; font-weight: 600; color: #0f172a; }
            QPushButton:hover { background-color: #e2e8f0; border-color: #0284c7; color: #0284c7; }
        """)
        self.btn_apply.clicked.connect(self.apply_requested.emit)

        self.btn_done = QPushButton("Done")
        self.btn_done.setToolTip("Done (Commit Adjustments and Close Sidebar)")
        self.btn_done.setStyleSheet("""
            QPushButton { background-color: #0284c7; border: 1px solid #0284c7; border-radius: 4px; padding: 4px 12px; font-size: 11px; font-weight: 600; color: #ffffff; }
            QPushButton:hover { background-color: #0369a1; }
        """)
        self.btn_done.clicked.connect(self.done_requested.emit)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setToolTip("Cancel and Discard Uncommitted Adjustments")
        self.btn_cancel.setStyleSheet("""
            QPushButton { background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 4px; padding: 4px 10px; font-size: 11px; font-weight: 600; color: #0f172a; }
            QPushButton:hover { background-color: #e2e8f0; }
        """)
        self.btn_cancel.clicked.connect(self.cancel_requested.emit)

        row1.addWidget(self.btn_apply)
        row1.addWidget(self.btn_done)
        row1.addWidget(self.btn_cancel)
        footer_layout.addLayout(row1)

        # Row 3: Undo, Redo
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        self.btn_undo = QPushButton("↩ Undo")
        self.btn_undo.setToolTip("Undo Last Adjustment (Ctrl+Z)")
        self.btn_redo = QPushButton("↪ Redo")
        self.btn_redo.setToolTip("Redo Adjustment (Ctrl+Y / Ctrl+Shift+Z)")

        for btn in (self.btn_undo, self.btn_redo):
            btn.setStyleSheet("""
                QPushButton { background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 4px; padding: 4px 10px; font-size: 11px; font-weight: 500; color: #334155; font-family: 'Segoe UI', 'Segoe UI Emoji', Arial, sans-serif; }
                QPushButton:hover { background-color: #e2e8f0; border-color: #0284c7; }
            """)
            row2.addWidget(btn)

        self.btn_undo.clicked.connect(self._on_undo_clicked)
        self.btn_redo.clicked.connect(self._on_redo_clicked)
        footer_layout.addLayout(row2)

        main_layout.addWidget(footer_frame)

    # ------------------------------------------------------------------
    # TAB 1: AUTO EXPOSURE
    # ------------------------------------------------------------------
    def _build_auto_exposure_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.setSpacing(8)

        # 1. Presets row
        presets_widget, self.cmb_auto_exp = self._create_presets_row(
            ["Default", "Auto Contrast", "Boost contrast"],
            self._on_auto_exp_preset_changed
        )
        layout.addWidget(presets_widget)

        # 2. Strength Card
        strength_card = self._card()
        strength_layout = QVBoxLayout(strength_card)
        strength_layout.setContentsMargins(6, 6, 6, 6)
        strength_layout.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("Strength:"))
        header_row.addStretch()
        strength_layout.addLayout(header_row)

        row = QHBoxLayout()
        self.slider_auto_exp = GradientSlider()
        self.slider_auto_exp.setRange(-100, 100)
        self.slider_auto_exp.setValue(0)

        self.spin_auto_exp = QSpinBox()
        self.spin_auto_exp.setRange(-100, 100)
        self.spin_auto_exp.setValue(0)
        self.spin_auto_exp.setFixedWidth(52)

        self.slider_auto_exp.valueChanged.connect(self.spin_auto_exp.setValue)
        self.spin_auto_exp.valueChanged.connect(self.slider_auto_exp.setValue)
        self.spin_auto_exp.valueChanged.connect(lambda: self.adjustments_changed.emit())
        self.slider_auto_exp.sliderReleased.connect(self._commit_change)
        self.spin_auto_exp.editingFinished.connect(self._commit_change)

        row.addWidget(self.slider_auto_exp)
        row.addWidget(self.spin_auto_exp)
        strength_layout.addLayout(row)
        layout.addWidget(strength_card)

        # 3. Radio Buttons Card
        radio_card = self._card()
        radio_layout = QVBoxLayout(radio_card)
        radio_layout.setContentsMargins(8, 8, 8, 8)
        radio_layout.setSpacing(8)

        radio_style = """
            QRadioButton {
                font-size: 11px;
                color: #0f172a;
                font-weight: 500;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border: 2px solid #64748b;
                border-radius: 8px;
                background-color: #ffffff;
            }
            QRadioButton::indicator:hover {
                border-color: #0284c7;
            }
            QRadioButton::indicator:checked {
                border-color: #0284c7;
                background: qradialgradient(cx: 0.5, cy: 0.5, radius: 0.5, fx: 0.5, fy: 0.5,
                    stop: 0 #0284c7, stop: 0.55 #0284c7, stop: 0.65 #ffffff, stop: 1 #ffffff);
            }
        """

        self.radio_auto_contrast = QRadioButton("Auto contrast")
        self.radio_auto_contrast.setStyleSheet(radio_style)

        self.radio_auto_contrast_color = QRadioButton("Auto contrast and color")
        self.radio_auto_contrast_color.setStyleSheet(radio_style)
        self.radio_auto_contrast_color.setChecked(True)

        self.btn_group_auto = QButtonGroup(self)
        self.btn_group_auto.addButton(self.radio_auto_contrast)
        self.btn_group_auto.addButton(self.radio_auto_contrast_color)
        self.btn_group_auto.buttonToggled.connect(lambda btn, checked: self._commit_change() if checked else None)

        radio_layout.addWidget(self.radio_auto_contrast)
        radio_layout.addWidget(self.radio_auto_contrast_color)
        layout.addWidget(radio_card)

        # 4. Exposure warning + Reset row
        layout.addSpacing(6)
        layout.addLayout(self._create_bottom_row(self.reset_auto_exposure_tab))

        layout.addStretch()
        self.tabs.addTab(self._wrap_in_scroll(tab), "Auto Exposure")

    # ------------------------------------------------------------------
    # TAB 2: BRIGHTNESS
    # ------------------------------------------------------------------
    def _build_brightness_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.setSpacing(8)

        # 1. Presets row
        presets_widget, self.cmb_brightness = self._create_presets_row(
            ["Default", "Boost contrast", "Brighten shadows"],
            self._on_brightness_preset_changed
        )
        layout.addWidget(presets_widget)

        # 2. Controls
        layout.addWidget(self._create_control_card("Brightness", -100, 100, 0, "bright"))
        layout.addWidget(self._create_control_card("Contrast", -100, 100, 0, "contrast"))
        layout.addWidget(self._create_control_card("Gamma", 10, 300, 50, "gamma"))

        # 3. Grayscale & Black and White Section
        bw_card = self._card()
        bw_layout = QVBoxLayout(bw_card)
        bw_layout.setContentsMargins(8, 8, 8, 8)
        bw_layout.setSpacing(6)

        self.chk_grayscale = QCheckBox("Convert to Black and White")
        self.chk_grayscale.setStyleSheet("""
            QCheckBox { font-size: 11px; font-weight: 600; color: #0f172a; spacing: 6px; }
            QCheckBox::indicator { width: 14px; height: 14px; border: 1.5px solid #94a3b8; border-radius: 3px; background: #ffffff; }
            QCheckBox::indicator:checked { background: #0284c7; border-color: #0284c7; }
        """)
        bw_layout.addWidget(self.chk_grayscale)

        # Mode options (nested)
        self.bw_options_widget = QWidget()
        bw_opt_layout = QVBoxLayout(self.bw_options_widget)
        bw_opt_layout.setContentsMargins(16, 2, 0, 2)
        bw_opt_layout.setSpacing(6)

        radio_style = """
            QRadioButton { font-size: 11px; color: #334155; spacing: 6px; }
            QRadioButton::indicator { width: 13px; height: 13px; border: 1.5px solid #94a3b8; border-radius: 6px; background: #ffffff; }
            QRadioButton::indicator:checked {
                border-color: #0284c7;
                background: qradialgradient(cx: 0.5, cy: 0.5, radius: 0.5, fx: 0.5, fy: 0.5,
                    stop: 0 #0284c7, stop: 0.55 #0284c7, stop: 0.65 #ffffff, stop: 1 #ffffff);
            }
        """

        self.radio_gray_full = QRadioButton("Grayscale (Pure Black to Pure White)")
        self.radio_gray_full.setStyleSheet(radio_style)
        self.radio_gray_full.setChecked(True)

        self.radio_bw_binary = QRadioButton("Pure Black & White (Binary / 2-Tone)")
        self.radio_bw_binary.setStyleSheet(radio_style)

        self.btn_group_bw = QButtonGroup(self)
        self.btn_group_bw.addButton(self.radio_gray_full)
        self.btn_group_bw.addButton(self.radio_bw_binary)

        bw_opt_layout.addWidget(self.radio_gray_full)
        bw_opt_layout.addWidget(self.radio_bw_binary)

        # Threshold slider for Binary B&W
        self.bw_thresh_widget = QWidget()
        thresh_layout = QHBoxLayout(self.bw_thresh_widget)
        thresh_layout.setContentsMargins(14, 0, 0, 0)
        thresh_layout.setSpacing(6)

        lbl_thresh = QLabel("Threshold:")
        lbl_thresh.setStyleSheet("font-size: 10px; color: #64748b; font-weight: 500;")
        thresh_layout.addWidget(lbl_thresh)

        self.slider_bw_threshold = GradientSlider()
        self.slider_bw_threshold.setRange(1, 254)
        self.slider_bw_threshold.setValue(128)

        self.spin_bw_threshold = QSpinBox()
        self.spin_bw_threshold.setRange(1, 254)
        self.spin_bw_threshold.setValue(128)
        self.spin_bw_threshold.setFixedWidth(46)
        self.spin_bw_threshold.setStyleSheet("background: #ffffff; border: 1px solid #cbd5e1; border-radius: 3px; font-size: 11px;")

        self.slider_bw_threshold.valueChanged.connect(self.spin_bw_threshold.setValue)
        self.spin_bw_threshold.valueChanged.connect(self.slider_bw_threshold.setValue)
        self.spin_bw_threshold.valueChanged.connect(lambda: self.adjustments_changed.emit())
        self.slider_bw_threshold.sliderReleased.connect(self._commit_change)
        self.spin_bw_threshold.editingFinished.connect(self._commit_change)

        thresh_layout.addWidget(self.slider_bw_threshold)
        thresh_layout.addWidget(self.spin_bw_threshold)
        bw_opt_layout.addWidget(self.bw_thresh_widget)
        self.bw_thresh_widget.setVisible(False)

        bw_layout.addWidget(self.bw_options_widget)
        self.bw_options_widget.setEnabled(False)

        # Connect toggles
        def _on_chk_gray_toggled(checked: bool):
            self.bw_options_widget.setEnabled(checked)
            self.bw_thresh_widget.setVisible(checked and self.radio_bw_binary.isChecked())
            self.adjustments_changed.emit()
            self._commit_change()

        def _on_radio_bw_toggled():
            self.bw_thresh_widget.setVisible(self.chk_grayscale.isChecked() and self.radio_bw_binary.isChecked())
            self.adjustments_changed.emit()
            self._commit_change()

        self.chk_grayscale.toggled.connect(_on_chk_gray_toggled)
        self.radio_gray_full.toggled.connect(lambda c: _on_radio_bw_toggled() if c else None)
        self.radio_bw_binary.toggled.connect(lambda c: _on_radio_bw_toggled() if c else None)

        layout.addWidget(bw_card)

        # 4. Exposure warning + Reset row
        layout.addSpacing(6)
        layout.addLayout(self._create_bottom_row(self.reset_brightness_tab))

        layout.addStretch()
        self.tabs.addTab(self._wrap_in_scroll(tab), "Brightness")

    # ------------------------------------------------------------------
    # TAB 3: LEVELS
    # ------------------------------------------------------------------
    def _build_levels_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.setSpacing(8)

        # 1. Presets row (ACDSee)
        presets_widget, self.cmb_levels = self._create_presets_row(
            ["Brighten shadows", "Darken", "Midtones only"],
            self._on_levels_preset_changed
        )
        self.cmb_levels.setCurrentIndex(-1)
        layout.addWidget(presets_widget)

        # 2. Channel
        row_channel = QHBoxLayout()
        row_channel.addWidget(QLabel("Channel:"))
        self.cmb_levels_channel = QComboBox()
        self.cmb_levels_channel.addItems(["Luminance", "Red", "Green", "Blue"])
        self.cmb_levels_channel.setStyleSheet("""
            QComboBox { background: #ffffff; border: 1px solid #cbd5e1; border-radius: 3px; padding: 2px 6px; font-size: 11px; }
        """)
        self.cmb_levels_channel.currentTextChanged.connect(self._on_levels_channel_changed)
        row_channel.addWidget(self.cmb_levels_channel)
        row_channel.addStretch()
        layout.addLayout(row_channel)

        # 3. Interactive Levels Histogram Graph with Black/Gray/White triangle slider handles
        self.levels_hist = LevelsHistogramWidget()
        self.levels_hist.levels_changed.connect(self._on_levels_hist_dragged)
        self.levels_hist.drag_ended.connect(self._commit_change)
        layout.addWidget(self.levels_hist)

        # 4. Levels sliders/inputs card
        card = self._card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 8, 8, 8)
        card_layout.setSpacing(8)

        def _level_row(label, minv, maxv, default, decimals=0):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            if decimals > 0:
                spin = QDoubleSpinBox()
                spin.setDecimals(decimals)
                spin.setSingleStep(0.05)
            else:
                spin = QSpinBox()
            spin.setRange(minv, maxv)
            spin.setValue(default)
            spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            spin.valueChanged.connect(self._on_levels_spinboxes_changed)
            spin.editingFinished.connect(self._commit_change)
            row.addStretch()
            row.addWidget(spin)
            card_layout.addLayout(row)
            return spin

        self.spin_shadows = _level_row("Shadows (black point):", 0, 250, 0)
        self.spin_midtones_val = _level_row("Midtones (gamma):", 0.10, 9.99, 1.00, decimals=2)
        self.spin_highlights = _level_row("Highlights (white point):", 5, 255, 255)

        # Clipped % (ACDSee Image 4)
        clip_row = QHBoxLayout()
        clip_row.setSpacing(4)
        self.spin_clip_black = QDoubleSpinBox()
        self.spin_clip_black.setDecimals(2)
        self.spin_clip_black.setRange(0.0, 100.0)
        self.spin_clip_black.setValue(0.00)
        self.spin_clip_black.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_clip_black.setFixedWidth(55)
        self.spin_clip_black.setStyleSheet("background: #ffffff; border: 1px solid #cbd5e1; border-radius: 3px; font-size: 11px;")

        lbl_clip = QLabel("Clipped %")
        lbl_clip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_clip.setStyleSheet("font-size: 11px; color: #64748b; font-weight: 500;")

        self.spin_clip_white = QDoubleSpinBox()
        self.spin_clip_white.setDecimals(2)
        self.spin_clip_white.setRange(0.0, 100.0)
        self.spin_clip_white.setValue(0.00)
        self.spin_clip_white.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_clip_white.setFixedWidth(55)
        self.spin_clip_white.setStyleSheet("background: #ffffff; border: 1px solid #cbd5e1; border-radius: 3px; font-size: 11px;")

        clip_row.addWidget(self.spin_clip_black)
        clip_row.addWidget(lbl_clip, stretch=1)
        clip_row.addWidget(self.spin_clip_white)
        card_layout.addLayout(clip_row)

        layout.addWidget(card)

        # 5. Eyedroppers row (ACDSee Image 4)
        eyedropper_row = QHBoxLayout()
        eyedropper_row.setSpacing(4)
        self.btn_eyedrop_black = QPushButton("🖋️ Black")
        self.btn_eyedrop_black.setToolTip("Set Black Point (Shadows)")
        self.btn_eyedrop_gray = QPushButton("🖋️ Gray")
        self.btn_eyedrop_gray.setToolTip("Set Gray Point (Midtones)")
        self.btn_eyedrop_white = QPushButton("🖋️ White")
        self.btn_eyedrop_white.setToolTip("Set White Point (Highlights)")

        self._normal_eyedrop_style = """
            QPushButton { background: #ffffff; border: 1px solid #cbd5e1; border-radius: 3px; font-size: 10px; padding: 4px 6px; font-weight: 500; color: #0f172a; }
            QPushButton:hover { background: #f1f5f9; border-color: #0284c7; }
        """
        self._active_eyedrop_style = """
            QPushButton { background: #0284c7; border: 1.5px solid #0369a1; border-radius: 3px; font-size: 10px; padding: 4px 6px; font-weight: 600; color: #ffffff; }
            QPushButton:hover { background: #0369a1; }
        """

        for btn in (self.btn_eyedrop_black, self.btn_eyedrop_gray, self.btn_eyedrop_white):
            btn.setStyleSheet(self._normal_eyedrop_style)
            eyedropper_row.addWidget(btn)

        self.btn_eyedrop_black.clicked.connect(lambda: self.toggle_eyedropper("black"))
        self.btn_eyedrop_gray.clicked.connect(lambda: self.toggle_eyedropper("gray"))
        self.btn_eyedrop_white.clicked.connect(lambda: self.toggle_eyedropper("white"))

        # Color swatch square and label
        self.lbl_target_swatch = QLabel()
        self.lbl_target_swatch.setFixedSize(14, 14)
        self.lbl_target_swatch.setStyleSheet("background-color: #ffffff; border: 1px solid #94a3b8; border-radius: 2px;")
        eyedropper_row.addWidget(self.lbl_target_swatch)

        self.lbl_target_color = QLabel("R:240 G:240 B:240")
        self.lbl_target_color.setStyleSheet("font-size: 10px; color: #475569; border: 1px solid #cbd5e1; border-radius: 3px; padding: 2px 4px; background: #ffffff;")
        eyedropper_row.addWidget(self.lbl_target_color)
        layout.addLayout(eyedropper_row)

        # 6. Auto... button (ACDSee Image 4)
        row_auto = QHBoxLayout()
        btn_auto = QPushButton("Auto...")
        btn_auto.setToolTip("Auto calculate Levels for current channel")
        btn_auto.setStyleSheet("""
            QPushButton { background: #ffffff; border: 1px solid #cbd5e1; border-radius: 4px; padding: 4px 14px; font-size: 11px; font-weight: 500; }
            QPushButton:hover { background: #f1f5f9; border-color: #0284c7; color: #0284c7; }
        """)
        btn_auto.clicked.connect(self._auto_levels)
        row_auto.addWidget(btn_auto)
        row_auto.addStretch()
        layout.addLayout(row_auto)

        # 7. Exposure warning + Reset row (ACDSee)
        layout.addSpacing(6)
        layout.addLayout(self._create_bottom_row(self.reset_levels_tab))

        layout.addStretch()
        self.tabs.addTab(self._wrap_in_scroll(tab), "Levels")

    # ------------------------------------------------------------------
    # TAB 4: CURVES
    # ------------------------------------------------------------------
    def _build_curves_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.setSpacing(8)

        # 1. Presets row (ACDSee)
        presets_widget, self.cmb_curves = self._create_presets_row(
            ["Color shift"],
            self._on_curves_preset_changed
        )
        self.cmb_curves.setCurrentIndex(-1)
        layout.addWidget(presets_widget)

        # 2. Channel (ACDSee Image 5)
        row_channel = QHBoxLayout()
        row_channel.addWidget(QLabel("Channel:"))
        self.cmb_curves_channel = QComboBox()
        self.cmb_curves_channel.addItems(["RGB", "Red", "Green", "Blue"])
        self.cmb_curves_channel.setStyleSheet("""
            QComboBox { background: #ffffff; border: 1px solid #cbd5e1; border-radius: 3px; padding: 2px 6px; font-size: 11px; }
        """)
        self.cmb_curves_channel.currentTextChanged.connect(self._on_curves_channel_changed)
        row_channel.addWidget(self.cmb_curves_channel)
        row_channel.addStretch()
        layout.addLayout(row_channel)

        # 3. Show Histogram checkbox (ACDSee Image 5)
        self.chk_show_histogram = QCheckBox("Show Histogram")
        self.chk_show_histogram.setChecked(True)
        self.chk_show_histogram.setStyleSheet("""
            QCheckBox { font-size: 11px; font-weight: 500; color: #334155; spacing: 6px; }
            QCheckBox::indicator { width: 14px; height: 14px; border: 1.5px solid #94a3b8; border-radius: 3px; background: #ffffff; }
            QCheckBox::indicator:checked { background: #0284c7; border-color: #0284c7; }
        """)
        self.chk_show_histogram.toggled.connect(self._on_curves_show_histogram_toggled)
        layout.addWidget(self.chk_show_histogram)

        self.curve_editor = CurveEditor()
        self.curve_editor.curve_changed.connect(lambda: self.adjustments_changed.emit())
        self.curve_editor.drag_ended.connect(self._commit_change)
        layout.addWidget(self.curve_editor)

        lbl_hint = QLabel("Click to add a point, drag to shape the curve, double-click a point to remove it.")
        lbl_hint.setWordWrap(True)
        lbl_hint.setStyleSheet("color: #64748b; font-size: 10px;")
        layout.addWidget(lbl_hint)

        # 4. Exposure warning + Reset row (ACDSee)
        layout.addSpacing(6)
        layout.addLayout(self._create_bottom_row(self.reset_curves_tab))

        layout.addStretch()
        self.tabs.addTab(self._wrap_in_scroll(tab), "Curves")

    # ------------------------------------------------------------------
    # Channel & Eyedropper Handlers
    # ------------------------------------------------------------------
    def _on_levels_channel_changed(self, new_channel: str):
        if not new_channel or new_channel == self._current_levels_channel:
            return
        # 1. Save current spinbox values to previous channel
        old = self._current_levels_channel
        self.levels_data[old]["shadows"] = self.spin_shadows.value()
        self.levels_data[old]["midtones"] = self.spin_midtones_val.value()
        self.levels_data[old]["highlights"] = self.spin_highlights.value()

        # 2. Switch active channel
        self._current_levels_channel = new_channel
        data = self.levels_data[new_channel]

        # 3. Load into spinboxes without emitting adjustments_changed
        self.spin_shadows.blockSignals(True)
        self.spin_midtones_val.blockSignals(True)
        self.spin_highlights.blockSignals(True)

        self.spin_shadows.setValue(data["shadows"])
        self.spin_midtones_val.setValue(data["midtones"])
        self.spin_highlights.setValue(data["highlights"])

        self.spin_shadows.blockSignals(False)
        self.spin_midtones_val.blockSignals(False)
        self.spin_highlights.blockSignals(False)

        # 4. Update histogram widget
        if self._cached_histograms and new_channel in self._cached_histograms:
            self.levels_hist.set_histogram(self._cached_histograms[new_channel], new_channel)
        else:
            self.levels_hist.set_histogram(None, new_channel)
        self.levels_hist.set_levels(data["shadows"], data["midtones"], data["highlights"])
        self.update_clipped_pct()

    def _on_levels_spinboxes_changed(self):
        ch = self._current_levels_channel
        s = self.spin_shadows.value()
        m = self.spin_midtones_val.value()
        h = self.spin_highlights.value()
        self.levels_data[ch]["shadows"] = s
        self.levels_data[ch]["midtones"] = m
        self.levels_data[ch]["highlights"] = h
        self.levels_hist.set_levels(s, m, h)
        self.update_clipped_pct()
        self.adjustments_changed.emit()

    def _on_levels_hist_dragged(self, s: int, m: float, h: int):
        ch = self._current_levels_channel
        self.levels_data[ch]["shadows"] = s
        self.levels_data[ch]["midtones"] = m
        self.levels_data[ch]["highlights"] = h
        self.spin_shadows.blockSignals(True)
        self.spin_midtones_val.blockSignals(True)
        self.spin_highlights.blockSignals(True)
        self.spin_shadows.setValue(s)
        self.spin_midtones_val.setValue(m)
        self.spin_highlights.setValue(h)
        self.spin_shadows.blockSignals(False)
        self.spin_midtones_val.blockSignals(False)
        self.spin_highlights.blockSignals(False)
        self.update_clipped_pct()
        self.adjustments_changed.emit()

    def _on_curves_channel_changed(self, new_channel: str):
        if not new_channel or new_channel == self._current_curves_channel:
            return
        old = self._current_curves_channel
        self.curves_data[old] = list(self.curve_editor.points)

        self._current_curves_channel = new_channel
        pts = self.curves_data[new_channel]
        self.curve_editor.set_channel(new_channel, pts)
        if self._cached_histograms:
            hist_key = "Luminance" if new_channel == "RGB" else new_channel
            self.curve_editor.set_histogram(self._cached_histograms.get(hist_key))

    def _on_curves_show_histogram_toggled(self, checked: bool):
        self.curve_editor.show_histogram = checked
        self.curve_editor.update()

    def toggle_eyedropper(self, mode: str):
        """Toggle active eyedropper picker mode ('black', 'gray', 'white')."""
        try:
            if self.active_picker == mode:
                self.active_picker = None
            else:
                self.active_picker = mode

            # Update button styles
            self.btn_eyedrop_black.setStyleSheet(self._active_eyedrop_style if self.active_picker == "black" else self._normal_eyedrop_style)
            self.btn_eyedrop_gray.setStyleSheet(self._active_eyedrop_style if self.active_picker == "gray" else self._normal_eyedrop_style)
            self.btn_eyedrop_white.setStyleSheet(self._active_eyedrop_style if self.active_picker == "white" else self._normal_eyedrop_style)

            self.eyedropper_mode_changed.emit(self.active_picker)
        except Exception as e:
            import traceback
            traceback.print_exc()

    def apply_eyedropper_sample(self, r: int, g: int, b: int):
        """
        Called when a pixel on the image is clicked with an eyedropper.
        Samples RGB, updates the target color label, and sets the corresponding
        channel's shadows/midtones/highlights matching ACDSee.
        """
        try:
            # 1. Update target color label & swatch
            self.lbl_target_color.setText(f"R:{r} G:{g} B:{b}")
            self.lbl_target_swatch.setStyleSheet(f"background-color: rgb({r},{g},{b}); border: 1px solid #94a3b8; border-radius: 2px;")

            curr_ch = self.cmb_levels_channel.currentText()
            luma = int(round(0.299 * r + 0.587 * g + 0.114 * b))

            # Block spinbox signals during programmatic update to prevent intermediate re-renders
            self.spin_shadows.blockSignals(True)
            self.spin_midtones_val.blockSignals(True)
            self.spin_highlights.blockSignals(True)

            # 2. Apply based on active picker
            if self.active_picker == "black":
                if curr_ch == "Red":
                    self.levels_data["Red"]["shadows"] = r
                    self.spin_shadows.setValue(r)
                elif curr_ch == "Green":
                    self.levels_data["Green"]["shadows"] = g
                    self.spin_shadows.setValue(g)
                elif curr_ch == "Blue":
                    self.levels_data["Blue"]["shadows"] = b
                    self.spin_shadows.setValue(b)
                elif curr_ch == "Luminance":
                    # ACDSee: Black dropper in Luminance sets black point across RGB
                    self.levels_data["Red"]["shadows"] = r
                    self.levels_data["Green"]["shadows"] = g
                    self.levels_data["Blue"]["shadows"] = b
                    self.levels_data["Luminance"]["shadows"] = luma
                    self.spin_shadows.setValue(luma)

            elif self.active_picker == "white":
                if curr_ch == "Red":
                    self.levels_data["Red"]["highlights"] = r
                    self.spin_highlights.setValue(r)
                elif curr_ch == "Green":
                    self.levels_data["Green"]["highlights"] = g
                    self.spin_highlights.setValue(g)
                elif curr_ch == "Blue":
                    self.levels_data["Blue"]["highlights"] = b
                    self.spin_highlights.setValue(b)
                elif curr_ch == "Luminance":
                    # ACDSee: White dropper in Luminance sets white point across RGB
                    self.levels_data["Red"]["highlights"] = r
                    self.levels_data["Green"]["highlights"] = g
                    self.levels_data["Blue"]["highlights"] = b
                    self.levels_data["Luminance"]["highlights"] = luma
                    self.spin_highlights.setValue(luma)

            elif self.active_picker == "gray":
                if curr_ch == "Red":
                    gamma = float(np.log(max(1, min(254, r)) / 255.0) / np.log(0.5))
                    gamma = round(float(np.clip(gamma, 0.10, 9.99)), 2)
                    self.levels_data["Red"]["midtones"] = gamma
                    self.spin_midtones_val.setValue(gamma)
                elif curr_ch == "Green":
                    gamma = float(np.log(max(1, min(254, g)) / 255.0) / np.log(0.5))
                    gamma = round(float(np.clip(gamma, 0.10, 9.99)), 2)
                    self.levels_data["Green"]["midtones"] = gamma
                    self.spin_midtones_val.setValue(gamma)
                elif curr_ch == "Blue":
                    gamma = float(np.log(max(1, min(254, b)) / 255.0) / np.log(0.5))
                    gamma = round(float(np.clip(gamma, 0.10, 9.99)), 2)
                    self.levels_data["Blue"]["midtones"] = gamma
                    self.spin_midtones_val.setValue(gamma)
                elif curr_ch == "Luminance":
                    # In ACDSee, Gray dropper in Luminance balances all 3 color channels to remove color cast
                    gamma_r = round(float(np.clip(np.log(max(1, min(254, r)) / 255.0) / np.log(0.5), 0.10, 9.99)), 2)
                    gamma_g = round(float(np.clip(np.log(max(1, min(254, g)) / 255.0) / np.log(0.5), 0.10, 9.99)), 2)
                    gamma_b = round(float(np.clip(np.log(max(1, min(254, b)) / 255.0) / np.log(0.5), 0.10, 9.99)), 2)
                    self.levels_data["Red"]["midtones"] = gamma_r
                    self.levels_data["Green"]["midtones"] = gamma_g
                    self.levels_data["Blue"]["midtones"] = gamma_b
                    gamma_l = round(float(np.clip(np.log(max(1, min(254, luma)) / 255.0) / np.log(0.5), 0.10, 9.99)), 2)
                    self.levels_data["Luminance"]["midtones"] = gamma_l
                    self.spin_midtones_val.setValue(gamma_l)

            self.spin_shadows.blockSignals(False)
            self.spin_midtones_val.blockSignals(False)
            self.spin_highlights.blockSignals(False)

            # 3. Update histogram & clipped %
            self.levels_hist.set_levels(self.spin_shadows.value(), self.spin_midtones_val.value(), self.spin_highlights.value())
            self.update_clipped_pct()
            self.adjustments_changed.emit()
            self._commit_change()
        except Exception as e:
            import traceback
            traceback.print_exc()

    def update_clipped_pct(self):
        """Recalculate clipped % for current channel using the 256-bin histogram."""
        ch = self._current_levels_channel
        if not hasattr(self, "_cached_histograms") or ch not in self._cached_histograms:
            return
        hist = self._cached_histograms[ch]
        total = float(np.sum(hist))
        if total == 0:
            return
        s = int(self.spin_shadows.value())
        h = int(self.spin_highlights.value())
        clip_black = float(np.sum(hist[:s + 1]) / total) * 100.0
        clip_white = float(np.sum(hist[h:]) / total) * 100.0
        self.spin_clip_black.blockSignals(True)
        self.spin_clip_white.blockSignals(True)
        self.spin_clip_black.setValue(round(clip_black, 2))
        self.spin_clip_white.setValue(round(clip_white, 2))
        self.spin_clip_black.blockSignals(False)
        self.spin_clip_white.blockSignals(False)

    def update_histograms(self, qimg_or_pixmap=None):
        """Compute 256-bin histograms for Luminance, Red, Green, Blue and update widgets."""
        if qimg_or_pixmap is None or self.isHidden():
            return
        if isinstance(qimg_or_pixmap, QPixmap):
            qimg = qimg_or_pixmap.toImage()
        else:
            qimg = qimg_or_pixmap

        if qimg.isNull():
            return

        qimg_32 = qimg.convertToFormat(QImage.Format.Format_ARGB32)
        ptr = qimg_32.bits()
        ptr.setsize(qimg_32.sizeInBytes())
        arr = np.frombuffer(ptr, dtype=np.uint8)

        total_pixels = len(arr) // 4
        if total_pixels > 500000:
            stride = total_pixels // 500000
            b = arr[0::4 * stride]
            g = arr[1::4 * stride]
            r = arr[2::4 * stride]
        else:
            b = arr[0::4]
            g = arr[1::4]
            r = arr[2::4]

        # Fast integer approximation: (299*R + 587*G + 114*B) >> 10 (<1ms)
        luma = ((299 * r.astype(np.uint32) + 587 * g.astype(np.uint32) + 114 * b.astype(np.uint32)) >> 10).astype(np.uint8)

        self._cached_histograms = {
            "Red": np.bincount(r, minlength=256)[:256].copy(),
            "Green": np.bincount(g, minlength=256)[:256].copy(),
            "Blue": np.bincount(b, minlength=256)[:256].copy(),
            "Luminance": np.bincount(luma, minlength=256)[:256].copy(),
        }

        # Update Levels histogram widget
        curr_lev_ch = self._current_levels_channel
        if curr_lev_ch in self._cached_histograms:
            self.levels_hist.set_histogram(self._cached_histograms[curr_lev_ch], curr_lev_ch)

        # Update Curves histogram
        curr_curv_ch = self._current_curves_channel
        curv_key = "Luminance" if curr_curv_ch == "RGB" else curr_curv_ch
        if curv_key in self._cached_histograms:
            self.curve_editor.set_histogram(self._cached_histograms[curv_key])

        self.update_clipped_pct()

    # ------------------------------------------------------------------
    # Shared small helpers
    # ------------------------------------------------------------------
    def _create_presets_row(self, presets: List[str], on_select_callback) -> Tuple[QWidget, QComboBox]:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 2)
        layout.setSpacing(3)

        lbl = QLabel("Presets")
        lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #475569;")
        layout.addWidget(lbl)

        row = QHBoxLayout()
        row.setSpacing(4)
        cmb = QComboBox()
        cmb.setStyleSheet("""
            QComboBox {
                background: #ffffff; border: 1px solid #cbd5e1; border-radius: 3px;
                padding: 3px 8px; font-size: 11px; color: #0f172a;
            }
            QComboBox::drop-down { border: none; width: 18px; }
            QComboBox QAbstractItemView { background: #ffffff; color: #0f172a; selection-background-color: #e2e8f0; selection-color: #0f172a; }
        """)
        cmb.addItems(presets)
        cmb.currentTextChanged.connect(on_select_callback)
        row.addWidget(cmb, stretch=1)

        btn_save = QPushButton("💾")
        btn_save.setToolTip("Save Current Settings as Preset")
        btn_save.setFixedSize(32, 26)
        btn_save.setStyleSheet("""
            QPushButton { background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 3px; font-size: 13px; color: #166534; font-family: 'Segoe UI Emoji', 'Segoe UI', Arial, sans-serif; }
            QPushButton:hover { background: #dcfce7; border-color: #22c55e; }
        """)
        row.addWidget(btn_save)

        btn_del = QPushButton("❌")
        btn_del.setToolTip("Delete Selected Preset")
        btn_del.setFixedSize(32, 26)
        btn_del.setStyleSheet("""
            QPushButton { background: #fef2f2; border: 1px solid #fecaca; border-radius: 3px; font-size: 11px; color: #ef4444; font-weight: bold; font-family: 'Segoe UI Emoji', 'Segoe UI', Arial, sans-serif; }
            QPushButton:hover { background: #fee2e2; border-color: #dc2626; color: #dc2626; }
        """)
        row.addWidget(btn_del)

        layout.addLayout(row)
        return container, cmb

    def _create_bottom_row(self, reset_callback) -> QHBoxLayout:
        btn_row = QHBoxLayout()
        chk_warn = QCheckBox("⚠️ Exposure warning")
        chk_warn.setToolTip("Highlight blown highlights in blue and crushed shadows in red")
        chk_warn.setStyleSheet("""
            QCheckBox { font-size: 11px; font-weight: 500; color: #334155; spacing: 6px; }
            QCheckBox::indicator { width: 14px; height: 14px; border: 1.5px solid #94a3b8; border-radius: 3px; background: #ffffff; }
            QCheckBox::indicator:checked { background: #0284c7; border-color: #0284c7; }
        """)
        chk_warn.setChecked(self._exposure_warning)
        chk_warn.toggled.connect(self._on_exposure_warning_toggled)
        self._warning_checkboxes.append(chk_warn)
        btn_row.addWidget(chk_warn)

        btn_row.addStretch()

        btn_reset = self._reset_button()
        btn_reset.clicked.connect(reset_callback)
        btn_row.addWidget(btn_reset)
        return btn_row

    def _on_exposure_warning_toggled(self, checked: bool):
        self._exposure_warning = checked
        for cb in self._warning_checkboxes:
            if cb.isChecked() != checked:
                cb.blockSignals(True)
                cb.setChecked(checked)
                cb.blockSignals(False)
        self.adjustments_changed.emit()
        self._commit_change()

    def _card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet("""
            QFrame { background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 4px; padding: 4px; }
            QLabel { font-size: 11px; font-weight: 600; color: #334155; }
            QSpinBox, QDoubleSpinBox {
                background: #ffffff; border: 1px solid #cbd5e1; border-radius: 3px;
                padding: 2px 4px; font-size: 11px; color: #0f172a;
            }
        """)
        return card

    def _reset_button(self) -> QPushButton:
        btn = QPushButton("🔄 Reset")
        btn.setStyleSheet("""
            QPushButton { background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 4px; padding: 5px 14px; font-size: 11px; font-weight: 500; color: #0f172a; }
            QPushButton:hover { background-color: #f1f5f9; border-color: #0284c7; color: #0284c7; }
        """)
        return btn

    def _create_control_card(self, label_text: str, min_val: int, max_val: int, default_val: int, control_type: str) -> QFrame:
        card = self._card()
        card.setStyleSheet(card.styleSheet() + """
            QSpinBox::up-button, QSpinBox::down-button { width: 0px; height: 0px; border: none; }
            QSpinBox::up-arrow, QSpinBox::down-arrow { image: none; }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(6, 6, 6, 6)
        card_layout.setSpacing(6)

        header_row = QHBoxLayout()
        lbl = QLabel(label_text if control_type != "gamma" else "Gamma (1.00)")
        if control_type == "gamma":
            self.lbl_gamma = lbl
        header_row.addWidget(lbl)
        header_row.addStretch()
        card_layout.addLayout(header_row)

        row = QHBoxLayout()
        slider = GradientSlider()
        slider.setRange(min_val, max_val)
        slider.setValue(default_val)

        spin = QSpinBox()
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        spin.setRange(min_val, max_val)
        spin.setValue(default_val if control_type != "gamma" else 50)

        slider.valueChanged.connect(spin.setValue)
        spin.valueChanged.connect(slider.setValue)

        if control_type == "bright":
            self.slider_bright = slider
            self.spin_bright = spin
        elif control_type == "contrast":
            self.slider_contrast = slider
            self.spin_contrast = spin
        elif control_type == "gamma":
            self.slider_gamma = slider
            self.spin_gamma = spin
            spin.valueChanged.connect(lambda v: self.lbl_gamma.setText(f"Gamma ({v / 50.0:.2f})"))

        slider.sliderReleased.connect(self._commit_change)
        spin.editingFinished.connect(self._commit_change)
        spin.valueChanged.connect(lambda: self.adjustments_changed.emit())

        row.addWidget(slider)
        row.addWidget(spin)
        card_layout.addLayout(row)
        return card

    # -- Preset handlers --------------------------------------------------
    def _on_auto_exp_preset_changed(self, name: str):
        if name == "Boost contrast":
            self.slider_auto_exp.setValue(50)
            self.radio_auto_contrast_color.setChecked(True)
        elif name == "Auto Contrast":
            self.slider_auto_exp.setValue(50)
            self.radio_auto_contrast.setChecked(True)
        elif name == "Default":
            self.slider_auto_exp.setValue(0)
            self.radio_auto_contrast_color.setChecked(True)
        self._commit_change()

    def _on_brightness_preset_changed(self, name: str):
        if name == "Boost contrast":
            self.slider_bright.setValue(0)
            self.slider_contrast.setValue(25)
            self.slider_gamma.setValue(50)
        elif name == "Brighten shadows":
            self.slider_bright.setValue(15)
            self.slider_contrast.setValue(-10)
            self.slider_gamma.setValue(65)
        elif name == "Default":
            self.slider_bright.setValue(0)
            self.slider_contrast.setValue(0)
            self.slider_gamma.setValue(50)
        self._commit_change()

    def _on_levels_preset_changed(self, name: str):
        if name == "Brighten shadows":
            self.spin_shadows.setValue(0)
            self.spin_midtones_val.setValue(1.30)
            self.spin_highlights.setValue(255)
        elif name == "Darken":
            self.spin_shadows.setValue(0)
            self.spin_midtones_val.setValue(0.80)
            self.spin_highlights.setValue(255)
        elif name == "Midtones only":
            self.spin_shadows.setValue(0)
            self.spin_midtones_val.setValue(1.15)
            self.spin_highlights.setValue(255)
        elif name == "Default":
            self.spin_shadows.setValue(0)
            self.spin_midtones_val.setValue(1.00)
            self.spin_highlights.setValue(255)
        self._commit_change()

    def _on_curves_preset_changed(self, name: str):
        if name == "Color shift":
            self.curves_data["Green"] = [(0, 0), (118, 88), (255, 255)]
            if hasattr(self, "cmb_curves_channel"):
                if self.cmb_curves_channel.currentText() != "Green":
                    self.cmb_curves_channel.setCurrentText("Green")
                else:
                    self.curve_editor.set_channel("Green", self.curves_data["Green"])
            else:
                self.curve_editor.points = list(self.curves_data["Green"])
                self.curve_editor.update()
            self.curve_editor.curve_changed.emit()
        elif name == "Default":
            self.curve_editor.reset()
        self._commit_change()

    def _auto_levels(self):
        """Auto calculate levels based on current channel histogram if available."""
        ch = self._current_levels_channel
        if ch in self._cached_histograms:
            hist = self._cached_histograms[ch]
            cum = np.cumsum(hist)
            total = cum[-1]
            if total > 0:
                # 0.5% cutoff for black and white points
                bp = int(np.searchsorted(cum, total * 0.005))
                wp = int(np.searchsorted(cum, total * 0.995))
                self.spin_shadows.setValue(max(0, min(240, bp)))
                self.spin_midtones_val.setValue(1.00)
                self.spin_highlights.setValue(max(bp + 5, min(255, wp)))
                self._commit_change()
                return

        self.spin_shadows.setValue(12)
        self.spin_midtones_val.setValue(1.05)
        self.spin_highlights.setValue(243)
        self._commit_change()

    # -- Action buttons & History -----------------------------------------
    def _commit_change(self):
        """Called whenever an adjustment interaction finishes (slider released, spinbox entered, etc.)."""
        if not hasattr(self, "_last_committed_state") or self._last_committed_state is None:
            self._last_committed_state = self.get_full_state()
            return

        new_state = self.get_full_state()
        if self._states_differ(new_state, self._last_committed_state):
            self._undo_stack.append(self._last_committed_state)
            self._redo_stack.clear()
            self._last_committed_state = copy.deepcopy(new_state)
            self._update_undo_redo_buttons()

    def _states_differ(self, s1: Dict[str, Any], s2: Dict[str, Any]) -> bool:
        if s1 is None or s2 is None:
            return True
        for k in ("auto_exp_strength", "auto_exp_radio", "brightness", "contrast", "gamma", "grayscale", "grayscale_mode", "bw_threshold", "levels_data", "curves_data", "exposure_warning"):
            if s1.get(k) != s2.get(k):
                return True
        return False

    def get_full_state(self) -> Dict[str, Any]:
        """Captures a complete snapshot of all adjustment sidebar controls."""
        ch_l = self._current_levels_channel
        if hasattr(self, "spin_shadows"):
            self.levels_data[ch_l]["shadows"] = self.spin_shadows.value()
            self.levels_data[ch_l]["midtones"] = round(self.spin_midtones_val.value(), 2)
            self.levels_data[ch_l]["highlights"] = self.spin_highlights.value()

        ch_c = self._current_curves_channel
        if hasattr(self, "curve_editor"):
            self.curves_data[ch_c] = list(self.curve_editor.points)

        return {
            "auto_exp_strength": self.spin_auto_exp.value() if hasattr(self, "spin_auto_exp") else 0,
            "auto_exp_radio": "contrast" if hasattr(self, "radio_auto_contrast") and self.radio_auto_contrast.isChecked() else "contrast_color",
            "brightness": self.slider_bright.value() if hasattr(self, "slider_bright") else 0,
            "contrast": self.slider_contrast.value() if hasattr(self, "slider_contrast") else 0,
            "gamma": self.slider_gamma.value() if hasattr(self, "slider_gamma") else 50,
            "grayscale": self.chk_grayscale.isChecked() if hasattr(self, "chk_grayscale") else False,
            "grayscale_mode": "binary" if hasattr(self, "radio_bw_binary") and self.radio_bw_binary.isChecked() else "full_range",
            "bw_threshold": self.spin_bw_threshold.value() if hasattr(self, "spin_bw_threshold") else 128,
            "levels_channel": self._current_levels_channel,
            "levels_data": copy.deepcopy(self.levels_data),
            "curves_channel": self._current_curves_channel,
            "curves_data": copy.deepcopy(self.curves_data),
            "exposure_warning": self._exposure_warning,
        }

    def set_full_state(self, state: Dict[str, Any]):
        """Restores all controls from a complete snapshot without recursive side effects."""
        widgets_to_block = [
            getattr(self, "slider_auto_exp", None), getattr(self, "spin_auto_exp", None),
            getattr(self, "radio_auto_contrast", None), getattr(self, "radio_auto_contrast_color", None),
            getattr(self, "slider_bright", None), getattr(self, "spin_bright", None),
            getattr(self, "slider_contrast", None), getattr(self, "spin_contrast", None),
            getattr(self, "slider_gamma", None), getattr(self, "spin_gamma", None),
            getattr(self, "chk_grayscale", None),
            getattr(self, "cmb_levels_channel", None), getattr(self, "spin_shadows", None),
            getattr(self, "spin_midtones_val", None), getattr(self, "spin_highlights", None),
            getattr(self, "cmb_curves_channel", None), getattr(self, "curve_editor", None)
        ]
        for w in widgets_to_block:
            if w is not None:
                w.blockSignals(True)

        for cb in self._warning_checkboxes:
            cb.blockSignals(True)

        auto_str = state.get("auto_exp_strength", 0)
        self.slider_auto_exp.setValue(auto_str)
        self.spin_auto_exp.setValue(auto_str)

        if state.get("auto_exp_radio") == "contrast":
            self.radio_auto_contrast.setChecked(True)
        else:
            self.radio_auto_contrast_color.setChecked(True)

        b_val = state.get("brightness", 0)
        self.slider_bright.setValue(b_val)
        self.spin_bright.setValue(b_val)

        c_val = state.get("contrast", 0)
        self.slider_contrast.setValue(c_val)
        self.spin_contrast.setValue(c_val)

        g_val = state.get("gamma", 50)
        self.slider_gamma.setValue(g_val)
        self.spin_gamma.setValue(g_val)
        if hasattr(self, "lbl_gamma"):
            self.lbl_gamma.setText(f"Gamma ({g_val / 50.0:.2f})")

        is_gray = state.get("grayscale", False)
        self.chk_grayscale.setChecked(is_gray)
        gray_m = state.get("grayscale_mode", "full_range")
        if hasattr(self, "radio_bw_binary"):
            if gray_m == "binary":
                self.radio_bw_binary.setChecked(True)
            else:
                self.radio_gray_full.setChecked(True)
        thresh = state.get("bw_threshold", 128)
        if hasattr(self, "spin_bw_threshold"):
            self.spin_bw_threshold.setValue(thresh)
            self.slider_bw_threshold.setValue(thresh)
        if hasattr(self, "bw_options_widget"):
            self.bw_options_widget.setEnabled(is_gray)
        if hasattr(self, "bw_thresh_widget"):
            self.bw_thresh_widget.setVisible(is_gray and gray_m == "binary")

        # Levels
        self.levels_data = copy.deepcopy(state.get("levels_data", self.levels_data))
        lev_ch = state.get("levels_channel", "Luminance")
        self._current_levels_channel = lev_ch
        self.cmb_levels_channel.setCurrentText(lev_ch)
        ch_lev = self.levels_data[lev_ch]
        self.spin_shadows.setValue(ch_lev["shadows"])
        self.spin_midtones_val.setValue(ch_lev["midtones"])
        self.spin_highlights.setValue(ch_lev["highlights"])
        self.levels_hist.set_levels(ch_lev["shadows"], ch_lev["midtones"], ch_lev["highlights"])
        if self._cached_histograms and lev_ch in self._cached_histograms:
            self.levels_hist.set_histogram(self._cached_histograms[lev_ch], lev_ch)

        # Curves
        self.curves_data = copy.deepcopy(state.get("curves_data", self.curves_data))
        curv_ch = state.get("curves_channel", "RGB")
        self._current_curves_channel = curv_ch
        self.cmb_curves_channel.setCurrentText(curv_ch)
        self.curve_editor.set_channel(curv_ch, self.curves_data[curv_ch])
        if self._cached_histograms:
            hist_key = "Luminance" if curv_ch == "RGB" else curv_ch
            self.curve_editor.set_histogram(self._cached_histograms.get(hist_key))

        # Exposure warning
        self._exposure_warning = state.get("exposure_warning", False)
        for cb in self._warning_checkboxes:
            cb.setChecked(self._exposure_warning)

        for w in widgets_to_block:
            if w is not None:
                w.blockSignals(False)

        for cb in self._warning_checkboxes:
            cb.blockSignals(False)

        self.update_clipped_pct()
        self.adjustments_changed.emit()

    def _on_undo_clicked(self):
        if self._undo_stack:
            prev = self._undo_stack.pop()
            curr = self.get_full_state()
            self._redo_stack.append(curr)
            self.set_full_state(prev)
            self._last_committed_state = copy.deepcopy(prev)
            self._update_undo_redo_buttons()
        else:
            # Internal stack is empty, check if viewer_app can undo an applied commit
            self.undo_applied_requested.emit()

    def _on_redo_clicked(self):
        if self._redo_stack:
            nxt = self._redo_stack.pop()
            curr = self.get_full_state()
            self._undo_stack.append(curr)
            self.set_full_state(nxt)
            self._last_committed_state = copy.deepcopy(nxt)
            self._update_undo_redo_buttons()
        else:
            # Internal stack is empty, check if viewer_app can redo an applied commit
            self.redo_applied_requested.emit()

    def _update_undo_redo_buttons(self, can_undo_applied: Optional[bool] = None, can_redo_applied: Optional[bool] = None):
        if can_undo_applied is not None:
            self._can_undo_applied = can_undo_applied
        if can_redo_applied is not None:
            self._can_redo_applied = can_redo_applied

        can_undo = (len(self._undo_stack) > 0) or getattr(self, "_can_undo_applied", False)
        can_redo = (len(self._redo_stack) > 0) or getattr(self, "_can_redo_applied", False)

        self.btn_undo.setEnabled(can_undo)
        self.btn_redo.setEnabled(can_redo)

        enabled_style = """
            QPushButton { background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 4px; padding: 4px 10px; font-size: 11px; font-weight: 500; color: #0f172a; font-family: 'Segoe UI', 'Segoe UI Emoji', Arial, sans-serif; }
            QPushButton:hover { background-color: #e2e8f0; border-color: #0284c7; color: #0284c7; }
        """
        disabled_style = """
            QPushButton { background-color: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 4px; padding: 4px 10px; font-size: 11px; font-weight: 500; color: #94a3b8; font-family: 'Segoe UI', 'Segoe UI Emoji', Arial, sans-serif; }
        """
        self.btn_undo.setStyleSheet(enabled_style if can_undo else disabled_style)
        self.btn_redo.setStyleSheet(enabled_style if can_redo else disabled_style)

    # ------------------------------------------------------------------
    def _on_close_clicked(self):
        self.blockSignals(True)
        self.reset_all_adjustments()
        self.blockSignals(False)
        self.close_requested.emit()

    # -- reset helpers ----------------------------------------------------
    def reset_auto_exposure_tab(self):
        if hasattr(self, "cmb_auto_exp") and self.cmb_auto_exp:
            self.cmb_auto_exp.blockSignals(True)
            self.cmb_auto_exp.setCurrentIndex(0)
            self.cmb_auto_exp.blockSignals(False)
        self.slider_auto_exp.blockSignals(True)
        self.slider_auto_exp.setValue(0)
        self.slider_auto_exp.blockSignals(False)
        self.spin_auto_exp.blockSignals(True)
        self.spin_auto_exp.setValue(0)
        self.spin_auto_exp.blockSignals(False)
        self.radio_auto_contrast_color.blockSignals(True)
        self.radio_auto_contrast_color.setChecked(True)
        self.radio_auto_contrast_color.blockSignals(False)
        self.radio_auto_contrast.blockSignals(True)
        self.radio_auto_contrast.setChecked(False)
        self.radio_auto_contrast.blockSignals(False)
        self._exposure_warning = False
        for cb in self._warning_checkboxes:
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        self.adjustments_changed.emit()
        self._commit_change()

    def reset_brightness_tab(self):
        if hasattr(self, "cmb_brightness") and self.cmb_brightness:
            self.cmb_brightness.blockSignals(True)
            self.cmb_brightness.setCurrentIndex(0)
            self.cmb_brightness.blockSignals(False)
        self.slider_bright.blockSignals(True)
        self.slider_bright.setValue(0)
        self.slider_bright.blockSignals(False)
        self.spin_bright.blockSignals(True)
        self.spin_bright.setValue(0)
        self.spin_bright.blockSignals(False)
        self.slider_contrast.blockSignals(True)
        self.slider_contrast.setValue(0)
        self.slider_contrast.blockSignals(False)
        self.spin_contrast.blockSignals(True)
        self.spin_contrast.setValue(0)
        self.spin_contrast.blockSignals(False)
        self.slider_gamma.blockSignals(True)
        self.slider_gamma.setValue(50)
        self.slider_gamma.blockSignals(False)
        self.spin_gamma.blockSignals(True)
        self.spin_gamma.setValue(50)
        self.spin_gamma.blockSignals(False)
        self.chk_grayscale.blockSignals(True)
        self.chk_grayscale.setChecked(False)
        self.chk_grayscale.blockSignals(False)
        if hasattr(self, "radio_gray_full"):
            self.radio_gray_full.blockSignals(True)
            self.radio_gray_full.setChecked(True)
            self.radio_gray_full.blockSignals(False)
        if hasattr(self, "spin_bw_threshold"):
            self.spin_bw_threshold.blockSignals(True)
            self.spin_bw_threshold.setValue(128)
            self.spin_bw_threshold.blockSignals(False)
            self.slider_bw_threshold.blockSignals(True)
            self.slider_bw_threshold.setValue(128)
            self.slider_bw_threshold.blockSignals(False)
        if hasattr(self, "bw_options_widget"):
            self.bw_options_widget.setEnabled(False)
        if hasattr(self, "bw_thresh_widget"):
            self.bw_thresh_widget.setVisible(False)
        self._exposure_warning = False
        for cb in self._warning_checkboxes:
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        self.adjustments_changed.emit()
        self._commit_change()

    def reset_levels_tab(self):
        if hasattr(self, "cmb_levels") and self.cmb_levels:
            self.cmb_levels.blockSignals(True)
            self.cmb_levels.setCurrentIndex(-1)
            self.cmb_levels.blockSignals(False)
        for ch in self.levels_data:
            self.levels_data[ch] = {"shadows": 0, "midtones": 1.00, "highlights": 255, "clip_black": 0.0, "clip_white": 0.0}
        self.spin_shadows.blockSignals(True)
        self.spin_shadows.setValue(0)
        self.spin_shadows.blockSignals(False)
        self.spin_midtones_val.blockSignals(True)
        self.spin_midtones_val.setValue(1.00)
        self.spin_midtones_val.blockSignals(False)
        self.spin_highlights.blockSignals(True)
        self.spin_highlights.setValue(255)
        self.spin_highlights.blockSignals(False)
        self.levels_hist.set_levels(0, 1.00, 255)
        if self.active_picker:
            self.toggle_eyedropper(self.active_picker)
        self.update_clipped_pct()
        self._exposure_warning = False
        for cb in self._warning_checkboxes:
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        self.adjustments_changed.emit()
        self._commit_change()

    def reset_curves_tab(self):
        if hasattr(self, "cmb_curves") and self.cmb_curves:
            self.cmb_curves.blockSignals(True)
            self.cmb_curves.setCurrentIndex(-1)
            self.cmb_curves.blockSignals(False)
        for ch in self.curves_data:
            self.curves_data[ch] = [(0, 0), (255, 255)]
        self.curve_editor.reset()
        self._exposure_warning = False
        for cb in self._warning_checkboxes:
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        self.adjustments_changed.emit()
        self._commit_change()

    def reset_all_adjustments(self):
        self.reset_auto_exposure_tab()
        self.reset_brightness_tab()
        self.reset_levels_tab()
        self.reset_curves_tab()
        self._exposure_warning = False
        for cb in self._warning_checkboxes:
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._last_committed_state = self.get_full_state()
        self._update_undo_redo_buttons()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self.active_picker:
                self.toggle_eyedropper(self.active_picker)
            else:
                self._on_close_clicked()
            event.accept()
        else:
            super().keyPressEvent(event)

    def get_adjustment_params(self) -> Dict[str, Any]:
        """Return current adjustment parameter values for the vectorized processing engine."""
        # Ensure current channel spinbox values are recorded
        ch_l = self._current_levels_channel
        self.levels_data[ch_l]["shadows"] = self.spin_shadows.value()
        self.levels_data[ch_l]["midtones"] = self.spin_midtones_val.value()
        self.levels_data[ch_l]["highlights"] = self.spin_highlights.value()

        # Ensure current curve points are recorded
        ch_c = self._current_curves_channel
        self.curves_data[ch_c] = list(self.curve_editor.points)

        # Build LUT for each curve channel
        curve_luts: Dict[str, Optional[np.ndarray]] = {}
        for ch_name, pts in self.curves_data.items():
            if pts == [(0, 0), (255, 255)]:
                curve_luts[ch_name] = None
            else:
                xs = np.array([p[0] for p in pts], dtype=np.float64)
                ys = np.array([p[1] for p in pts], dtype=np.float64)
                lut = np.interp(np.arange(256, dtype=np.float64), xs, ys)
                curve_luts[ch_name] = np.clip(lut, 0, 255).astype(np.uint8)

        return {
            "auto_exposure": self.spin_auto_exp.value() != 0,
            "auto_exposure_strength": self.spin_auto_exp.value(),
            "auto_contrast_color": self.radio_auto_contrast_color.isChecked(),
            "brightness": self.slider_bright.value(),
            "contrast": self.slider_contrast.value(),
            "gamma": self.spin_gamma.value() / 50.0 if self.spin_gamma.value() > 0 else 1.0,
            "levels": {
                k: {
                    "shadows": v["shadows"],
                    "midtones": v["midtones"],
                    "highlights": v["highlights"],
                }
                for k, v in self.levels_data.items()
            },
            "black_point": self.levels_data["Luminance"]["shadows"],
            "white_point": self.levels_data["Luminance"]["highlights"],
            "midtone_val": self.levels_data["Luminance"]["midtones"],
            "shadows": 0,
            "midtones": 0,
            "highlights": 0,
            "grayscale": self.chk_grayscale.isChecked(),
            "grayscale_mode": "binary" if hasattr(self, "radio_bw_binary") and self.radio_bw_binary.isChecked() else "full_range",
            "bw_threshold": self.spin_bw_threshold.value() if hasattr(self, "spin_bw_threshold") else 128,
            "exposure_warning": self._exposure_warning,
            "curve_lut": curve_luts.get("RGB"),
            "curve_luts": curve_luts,
        }