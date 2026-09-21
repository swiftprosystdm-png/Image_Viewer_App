"""
viewer_app.py - Classic Enterprise Document Image Viewer Application (Project 2).

MNC Performance Engine:
- Ultra-Fast Vectorized NumPy LUT Processing Engine (<1ms rendering time).
- RAM Base Frame Caching for instantaneous 60 FPS real-time slider drags.
- Right-Side Image Adjustment Sidebar (Ctrl + L):
  * Brightness / Contrast / Gamma, Levels (with Histogram), Curves
- Zero-Reset Image Processing Pipeline:
  * Adjustments modify ONLY the image rendering layer without resetting zoom or pan.
- Multi-Theme Engine:
  * MNC Dark, MNC Light, MNC Midnight (alters UI only, never original image).
- Comprehensive MNC Menu Bar (File, Edit, View, Zoom, Modify, Tools, Help).
"""

import sys
import os
import time
from typing import List, Optional
import numpy as np

from PyQt6 import sip
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QDateTime, QSize, QPropertyAnimation, QEasingCurve, QThread, QTimer
from PyQt6.QtGui import (
    QPixmap, QImage, QTransform, QWheelEvent, QKeyEvent, QPainter, QAction,
    QKeySequence, QIcon, QColor, QActionGroup, QImageReader
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QFileDialog, QInputDialog, QMessageBox, QFrame, QToolBar, QToolButton,
    QStatusBar, QSizePolicy, QSplitter, QDialog, QLineEdit, QScrollArea, QComboBox
)


from sps_crypto import decrypt_sps_file, encrypt_sps_file, is_sps_file, DEFAULT_PASSPHRASE, _derive_key
from theme_config import setup_high_dpi, get_app_icon, get_light_stylesheet, get_theme_stylesheet, BASE_DIR
from adjustment_sidebar import ImageAdjustmentSidebar
from updater import check_for_updates_async, download_and_apply_update

import traceback

def _global_exception_handler(exc_type, exc_value, exc_traceback):
    """Prevent unhandled Python/Qt exceptions from silently crashing and closing the GUI window."""
    traceback.print_exception(exc_type, exc_value, exc_traceback)
    try:
        with open(os.path.join(BASE_DIR, "crash.log"), "a", encoding="utf-8") as f:
            f.write(f"--- Crash logged at {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
    except Exception:
        pass

sys.excepthook = _global_exception_handler

SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp",
    ".j2k", ".jp2", ".jpf", ".jpx", ".jpm", ".jxr", ".ico", ".svg", ".pdf"
}
ALL_SUPPORTED_EXTENSIONS = SUPPORTED_IMAGE_EXTENSIONS.union({".sps", ".pdf"})
APP_TITLE = "SPS_TDM_Image_Viewer"
APP_VERSION = "vBeta"


def _background_decode_to_qimage(file_path: str, passphrase: str) -> "tuple[QImage, dict]":
    """
    Thread-safe image decode for background prefetching.
    Uses ONLY QImage (never QPixmap, which is not safe to touch off the
    main GUI thread in Qt). Raises on any failure - caller should catch.
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".sps" or is_sps_file(file_path):
        image_bytes, metadata = decrypt_sps_file(file_path, passphrase=passphrase)
        if image_bytes.startswith(b"%PDF"):
            from PyQt6.QtPdf import QPdfDocument
            from PyQt6.QtCore import QBuffer, QIODevice, QSize
            buf = QBuffer()
            buf.setData(image_bytes)
            buf.open(QIODevice.OpenModeFlag.ReadOnly)
            pdf_doc = QPdfDocument(None)
            pdf_doc.load(buf)
            if pdf_doc.status() == QPdfDocument.Status.Ready and pdf_doc.pageCount() > 0:
                pt_size = pdf_doc.pagePointSize(0)
                scale = 150.0 / 72.0
                render_size = QSize(max(1, int(pt_size.width() * scale)), max(1, int(pt_size.height() * scale)))
                qimg = pdf_doc.render(0, render_size)
                metadata["page_count"] = pdf_doc.pageCount()
                metadata["pdf_page"] = 0
                metadata["format"] = "PDF"
                pdf_doc.close()
                buf.close()
                metadata["file_size"] = os.path.getsize(file_path)
                return qimg, metadata
            pdf_doc.close()
            buf.close()

        qimg = QImage()
        loaded = qimg.loadFromData(image_bytes)
        if not loaded or qimg.isNull():
            from io import BytesIO
            from PIL import Image as PILImage
            with PILImage.open(BytesIO(image_bytes)) as pil_img:
                pil_img_rgba = pil_img.convert("RGBA")
                data = pil_img_rgba.tobytes("raw", "RGBA")
                qimg = QImage(data, pil_img_rgba.width, pil_img_rgba.height, QImage.Format.Format_RGBA8888).copy()
                loaded = not qimg.isNull()
        if not loaded or qimg.isNull():
            raise ValueError("Decrypted binary content could not be parsed as an image.")
        metadata["file_size"] = os.path.getsize(file_path)
        return qimg, metadata
    elif ext == ".pdf":
        from PyQt6.QtPdf import QPdfDocument
        from PyQt6.QtCore import QSize
        pdf_doc = QPdfDocument(None)
        pdf_doc.load(file_path)
        if pdf_doc.status() == QPdfDocument.Status.Ready and pdf_doc.pageCount() > 0:
            pt_size = pdf_doc.pagePointSize(0)
            scale = 150.0 / 72.0
            render_size = QSize(max(1, int(pt_size.width() * scale)), max(1, int(pt_size.height() * scale)))
            qimg = pdf_doc.render(0, render_size)
            metadata = {
                "original_filename": os.path.basename(file_path),
                "file_size": os.path.getsize(file_path),
                "format": "PDF",
                "page_count": pdf_doc.pageCount(),
                "pdf_page": 0
            }
            pdf_doc.close()
            return qimg, metadata
        pdf_doc.close()
        raise ValueError(f"Failed to parse PDF document:\n{file_path}")
    else:
        reader = QImageReader(file_path)
        reader.setAutoTransform(True)
        qimg = reader.read()
        if qimg.isNull():
            qimg = QImage(file_path)
        if qimg.isNull():
            from PIL import Image as PILImage
            with PILImage.open(file_path) as pil_img:
                pil_img_rgba = pil_img.convert("RGBA")
                data = pil_img_rgba.tobytes("raw", "RGBA")
                qimg = QImage(data, pil_img_rgba.width, pil_img_rgba.height, QImage.Format.Format_RGBA8888).copy()
        if qimg.isNull():
            raise ValueError(f"Failed to parse image file:\n{file_path}")
        metadata = {
            "original_filename": os.path.basename(file_path),
            "file_size": os.path.getsize(file_path),
            "format": os.path.splitext(file_path)[1].upper().replace(".", "")
        }
        return qimg, metadata


class ImagePrefetchWorker(QThread):
    """
    Decodes ONE neighboring image (standard or encrypted .sps) on a
    background thread while the user is looking at the current image, so
    Next/Previous navigation can use an already-decoded frame instantly.
    Never touches any widget - only pure QImage decoding.
    """
    prefetch_done = pyqtSignal(str, object, object)  # (file_path, QImage or None, metadata or None)

    def __init__(self, file_path: str, passphrase: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.passphrase = passphrase
        # Also stashed here (not just emitted) so a navigation that catches
        # this worker still running can wait() for it and read the result
        # directly, instead of starting a whole separate redundant decode.
        self.result_qimg = None
        self.result_metadata = None

    def run(self):
        try:
            qimg, metadata = _background_decode_to_qimage(self.file_path, self.passphrase)
            self.result_qimg = qimg
            self.result_metadata = metadata
            self.prefetch_done.emit(self.file_path, qimg, metadata)
        except Exception:
            # Wrong passphrase for a differently-locked file, unreadable
            # file, etc. - just skip caching it silently.
            self.prefetch_done.emit(self.file_path, None, None)


class SpsKeyPrewarmWorker(QThread):
    """
    Pre-warms PBKDF2 derived keys in background for any .sps files in the folder,
    eliminating cold key derivation latency when navigating to them.
    """
    def __init__(self, sps_paths: List[str], passphrase: str, parent=None):
        super().__init__(parent)
        self.sps_paths = sps_paths
        self.passphrase = passphrase

    def run(self):
        for path in self.sps_paths:
            try:
                if os.path.exists(path) and os.path.getsize(path) >= 48:
                    with open(path, "rb") as f:
                        magic = f.read(4)
                        if magic == b"SPS1":
                            salt = f.read(16)
                            _derive_key(self.passphrase, salt)
            except Exception:
                pass


class RenameFileDialog(QDialog):
    """Rename File popup dialog matching user reference screenshot."""

    INVALID_CHARS = {'\\', '/', ':', '*', '?', '"', '<', '>', '|'}

    def __init__(self, current_file_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Rename File")
        self.setMinimumWidth(440)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                color: #0f172a;
            }
        """)

        self.old_path = current_file_path
        self.dir_name = os.path.dirname(current_file_path)
        self.full_old_name = os.path.basename(current_file_path)
        self.stem, self.ext = os.path.splitext(self.full_old_name)

        self.new_filename = self.full_old_name

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        # Header Area (Top UI)
        header_layout = QVBoxLayout()
        header_layout.setSpacing(2)
        
        title_lbl = QLabel("✏️ Rename File")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #0f172a;")
        header_layout.addWidget(title_lbl)

        sub_lbl = QLabel(f"Extension '{self.ext}' will be preserved automatically.")
        sub_lbl.setStyleSheet("font-size: 11px; color: #64748b;")
        header_layout.addWidget(sub_lbl)

        layout.addLayout(header_layout)

        # Separator line
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setFrameShadow(QFrame.Shadow.Sunken)
        sep1.setStyleSheet("background-color: #e2e8f0; max-height: 1px;")
        layout.addWidget(sep1)

        # Middle Form Area
        form_layout = QHBoxLayout()
        form_layout.setSpacing(10)

        lbl = QLabel("Filename:")
        lbl.setStyleSheet("font-weight: 600; color: #334155; font-size: 12px;")
        form_layout.addWidget(lbl)

        self.input_name = QLineEdit(self.full_old_name)
        self.input_name.setStyleSheet("""
            QLineEdit {
                background: #ffffff;
                border: 1.5px solid #0284c7;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
                color: #0f172a;
                font-weight: 500;
            }
            QLineEdit:focus {
                border: 2px solid #0284c7;
            }
        """)
        # Pre-select stem name for immediate editing
        self.input_name.setSelection(0, len(self.stem))
        form_layout.addWidget(self.input_name)
        layout.addLayout(form_layout)

        # Separator line before buttons
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setFrameShadow(QFrame.Shadow.Sunken)
        sep2.setStyleSheet("background-color: #e2e8f0; max-height: 1px;")
        layout.addWidget(sep2)

        # Footer Buttons Row (Bottom UI)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.btn_ok = QPushButton("OK")
        self.btn_ok.setFixedWidth(90)
        self.btn_ok.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
                color: #ffffff;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
            QPushButton:pressed {
                background-color: #075985;
            }
        """)
        self.btn_ok.clicked.connect(self._validate_and_accept)
        btn_layout.addWidget(self.btn_ok)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedWidth(90)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 6px 14px;
                color: #0f172a;
                font-weight: 500;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #f1f5f9;
            }
        """)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

        self.input_name.returnPressed.connect(self._validate_and_accept)

    def _validate_and_accept(self):
        raw_name = self.input_name.text().strip()
        if not raw_name:
            QMessageBox.warning(self, "Rename Error", "Filename cannot be empty.")
            return

        # Check invalid Windows characters
        found_invalid = [c for c in raw_name if c in self.INVALID_CHARS]
        if found_invalid:
            chars_str = ' '.join(sorted(list(self.INVALID_CHARS)))
            QMessageBox.warning(
                self, "Rename Error",
                f"A file name cannot contain any of the following characters:\n{chars_str}"
            )
            return

        # Preserve original extension automatically
        input_stem, input_ext = os.path.splitext(raw_name)
        if not input_ext or input_ext.lower() != self.ext.lower():
            if not raw_name.lower().endswith(self.ext.lower()):
                final_name = raw_name + self.ext
            else:
                final_name = raw_name
        else:
            final_name = raw_name

        # Check duplicate filename in same directory
        target_path = os.path.join(self.dir_name, final_name)
        if os.path.exists(target_path) and target_path.lower() != self.old_path.lower():
            QMessageBox.warning(
                self, "Rename Error",
                f"A file with the name '{final_name}' already exists in this folder."
            )
            return

        self.new_filename = final_name
class ClickableLabel(QLabel):
    """Clickable QLabel emitting clicked signal."""

    clicked = pyqtSignal()

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


def smooth_scroll_bar(scrollbar, delta: int, duration: int = 50):
    """Smoothly scroll a QScrollBar using target-accumulation QPropertyAnimation for butter-smooth 60 FPS gliding."""
    if not scrollbar or scrollbar.maximum() <= 0:
        return

    # Target accumulation: if an animation is already in flight, add delta to the existing target
    # rather than resetting velocity to 0. This creates seamless, stutter-free acceleration when keys are held.
    target_val = getattr(scrollbar, "_smooth_target", None)
    if target_val is None:
        target_val = scrollbar.value()

    new_target = max(scrollbar.minimum(), min(scrollbar.maximum(), target_val + delta))
    scrollbar._smooth_target = new_target

    existing = getattr(scrollbar, "_smooth_anim", None)
    if existing is not None:
        try:
            if not sip.isdeleted(existing):
                existing.stop()
        except RuntimeError:
            pass
        scrollbar._smooth_anim = None

    start_val = scrollbar.value()
    if start_val == new_target:
        scrollbar._smooth_target = None
        return

    anim = QPropertyAnimation(scrollbar, b"value", scrollbar.parent() or scrollbar)
    anim.setDuration(duration)
    anim.setStartValue(start_val)
    anim.setEndValue(new_target)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    scrollbar._smooth_anim = anim

    def _on_finished():
        setattr(scrollbar, "_smooth_anim", None)
        setattr(scrollbar, "_smooth_target", None)

    anim.finished.connect(_on_finished)
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


class ImageGraphicsView(QGraphicsView):

    """High-quality QGraphicsView viewport for document image viewing."""
    
    zoom_changed = pyqtSignal(float)
    file_dropped = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing |
            QPainter.RenderHint.SmoothPixmapTransform |
            QPainter.RenderHint.TextAntialiasing
        )
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.horizontalScrollBar().setSingleStep(40)
        self.verticalScrollBar().setSingleStep(40)
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setStyleSheet("background-color: #e2e8f0;")
        
        self._zoom_factor = 1.0

        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            win = self.window()
            if hasattr(win, 'sidebar') and getattr(win.sidebar, 'active_picker', None):
                try:
                    pt = event.position().toPoint() if hasattr(event, 'position') else event.pos()
                    scene_pos = self.mapToScene(pt)
                    if hasattr(win, 'on_image_pixel_picked') and win.on_image_pixel_picked(scene_pos):
                        event.accept()
                        return
                except Exception as e:
                    traceback.print_exc()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Double-clicking on image view toggles between Fit to Window and Actual Size (100%)."""
        if event.button() == Qt.MouseButton.LeftButton:
            win = self.window()
            if hasattr(win, 'fit_to_view') and hasattr(win, 'zoom_100'):
                rect = self.transform().mapRect(QRectF(0, 0, 1, 1))
                current_zoom = rect.width()
                if abs(current_zoom - 1.0) < 0.05:
                    win.fit_to_view()
                else:
                    win.zoom_100()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                file_path = urls[0].toLocalFile()
                if file_path and os.path.exists(file_path):
                    self.file_dropped.emit(file_path)
                    event.acceptProposedAction()
                    return
        super().dropEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        """Smooth mouse wheel zoom in/out centered at mouse cursor position."""
        modifiers = event.modifiers()
        
        # If Shift is held, scroll vertically smoothly
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            v_bar = self.verticalScrollBar()
            delta = event.angleDelta().y()
            if v_bar and v_bar.maximum() > 0 and delta != 0:
                smooth_scroll_bar(v_bar, -delta)
                event.accept()
                return

        # Default mouse wheel action: Smooth Cursor-Centered Zoom in/out
        delta = event.angleDelta().y()
        if delta == 0:
            return

        if delta > 0:
            factor = 1.15
        else:
            factor = 1 / 1.15

        new_zoom = self._zoom_factor * factor
        if 0.05 <= new_zoom <= 30.0:
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
            self.scale(factor, factor)
            self._zoom_factor = new_zoom
            self.zoom_changed.emit(self._zoom_factor)
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

        event.accept()

    def reset_zoom(self):
        self.resetTransform()
        self._zoom_factor = 1.0
        self.zoom_changed.emit(self._zoom_factor)


class SPSImageViewerWindow(QMainWindow):
    """Classic Enterprise Document Image Viewer Window."""

    def __init__(self, start_file: Optional[str] = None):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(get_app_icon())
        self.setMinimumSize(600, 440)

        # Dynamically set initial size to fit current screen/monitor responsively
        screen = QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            w = min(1240, max(800, int(avail.width() * 0.90)))
            h = min(820, max(560, int(avail.height() * 0.88)))
            self.resize(w, h)
        else:
            self.resize(1200, 800)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.current_theme_name: str = "Light Theme"
        self.current_file_path: Optional[str] = None
        self.current_passphrase: str = DEFAULT_PASSPHRASE
        self.folder_files: List[str] = []
        self._cached_folder_path: Optional[str] = None  # avoids re-scanning the folder on every navigation
        self._force_dropdown_refresh: bool = False  # set True after in-place folder_files edits (rename/delete)
        # Small LRU cache of already-decoded frames, so Next/Previous can
        # reuse a background-prefetched image instead of re-decoding it.
        self._decode_cache: dict = {}          # file_path -> {"qimg": QImage, "pixmap": QPixmap, "metadata": dict}
        self._decode_cache_order: list = []    # oldest-first LRU order
        self._decode_cache_limit: int = 30
        self._prefetch_workers: dict = {}      # file_path -> ImagePrefetchWorker currently running
        self._sps_prewarm_worker: Optional[SpsKeyPrewarmWorker] = None
        self.current_folder_index: int = -1
        self.current_rotation: int = 0
        self.is_inverted: bool = False
        self.is_modified: bool = False         # Tracks unsaved adjustments for current image
        self.current_pixmap: Optional[QPixmap] = None
        self.base_qimage: Optional[QImage] = None  # RAM base frame cache
        self.is_encrypted_file: bool = False
        self.file_metadata: dict = {}
        self.image_states: dict = {}
        self.load_duration_sec: float = 0.0
        self.pdf_page_count: int = 1
        self.current_pdf_page: int = 0
        self._active_pdf_doc = None
        self._active_pdf_buf = None
        self._applied_undo_stack: List[Tuple[QImage, Dict[str, Any]]] = []
        self._applied_redo_stack: List[Tuple[QImage, Dict[str, Any]]] = []

        self._init_ui()
        self._create_menus()
        self._create_toolbars()

        if start_file and os.path.exists(start_file):
            self.load_image(start_file, preserve_view=False)
        else:
            self.show_default_logo()

        # Check for updates silently on startup
        check_for_updates_async(self, silent=True, callback=self._on_update_check_finished)

    def showEvent(self, event):
        super().showEvent(event)
        if self.current_file_path:
            self.fit_to_view()
        else:
            self.show_default_logo()
        QTimer.singleShot(50, self._setup_toolbar_overflow)
        QTimer.singleShot(250, self._setup_toolbar_overflow)

    def show_default_logo(self):
        """Display Swift-ProSys-Logo.png centered in the viewport when no image is loaded."""
        self.current_file_path = None
        self.current_folder_index = -1
        self.current_pixmap = None
        self.base_qimage = None
        self.is_encrypted_file = False
        self.file_metadata = {}

        logo_path = os.path.join(BASE_DIR, "Swift-ProSys-Logo.png")
        if os.path.exists(logo_path):
            logo_pixmap = QPixmap(logo_path)
            if not logo_pixmap.isNull():
                self.pixmap_item.setPixmap(logo_pixmap)
                self.scene.setSceneRect(QRectF(logo_pixmap.rect()))
                self.view.resetTransform()
                
                vw = self.view.viewport().width()
                vh = self.view.viewport().height()
                if vw > 0 and vh > 0 and (logo_pixmap.width() > vw or logo_pixmap.height() > vh):
                    self.view.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
                else:
                    self.view.centerOn(self.pixmap_item)
                
                rect = self.view.transform().mapRect(QRectF(0, 0, 1, 1))
                self.view._zoom_factor = rect.width() if rect.width() > 0 else 1.0
        else:
            self.pixmap_item.setPixmap(QPixmap())
            self.scene.clear()

        self.setWindowTitle(APP_TITLE)
        if hasattr(self, 'status_bar'):
            self.status_bar.showMessage("Ready. Select or drag & drop an image or .sps file.")

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Main Splitter for Viewport & Right Adjustment Sidebar

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Graphics Scene and Viewport
        self.scene = QGraphicsScene(self)
        self.view = ImageGraphicsView(self)
        self.view.setScene(self.scene)
        self.view.zoom_changed.connect(self._on_zoom_changed)
        self.view.file_dropped.connect(lambda path: self.load_image(path, preserve_view=False))
        
        self.pixmap_item = QGraphicsPixmapItem()
        self.pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.scene.addItem(self.pixmap_item)

        self.splitter.addWidget(self.view)

        # Right Adjustment Sidebar (Ctrl + L)
        self.sidebar = ImageAdjustmentSidebar(self)
        self.sidebar.adjustments_changed.connect(self._on_adjustments_changed)
        self.sidebar.close_requested.connect(self.toggle_adjustment_sidebar)
        self.sidebar.save_requested.connect(self.save_current_image)
        self.sidebar.save_as_requested.connect(self.save_image_copy)
        self.sidebar.discard_requested.connect(self.discard_adjustments)
        self.sidebar.apply_requested.connect(self.apply_adjustments_to_image)
        self.sidebar.done_requested.connect(self.done_adjustments)
        self.sidebar.cancel_requested.connect(self.cancel_adjustments)
        self.sidebar.undo_applied_requested.connect(self.undo_applied_image)
        self.sidebar.redo_applied_requested.connect(self.redo_applied_image)
        self.sidebar.eyedropper_mode_changed.connect(self._on_eyedropper_mode_changed)
        self.sidebar.chk_grayscale.toggled.connect(self._sync_grayscale_ui)
        self.sidebar.hide()

        self.splitter.addWidget(self.sidebar)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)

        main_layout.addWidget(self.splitter)

        # Status Bar
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready. Select or drag & drop an image or .sps file.")

        self.setAcceptDrops(True)
        self.view.setFocus()

    def _create_menus(self):
        menubar = self.menuBar()

        # File Menu
        file_menu = menubar.addMenu("File")

        open_folder_act = QAction("Open File...", self)
        open_folder_act.triggered.connect(self.select_and_open_file)
        file_menu.addAction(open_folder_act)

        open_new_window_act = QAction("Open Next Image in New Window", self)
        open_new_window_act.setShortcut("Ctrl+Shift+N")
        open_new_window_act.setToolTip("Opens the next image in a separate viewer window, so you can compare it against the current one side by side.")
        open_new_window_act.triggered.connect(self.open_current_in_new_window)
        file_menu.addAction(open_new_window_act)

        file_menu.addSeparator()

        save_act = QAction("Save", self)
        save_act.setShortcut(QKeySequence.StandardKey.Save)
        save_act.setToolTip("Save all active image adjustments to current file (Ctrl+S)")
        save_act.triggered.connect(self.save_current_image)
        file_menu.addAction(save_act)

        save_as_act = QAction("Save Copy As...", self)
        save_as_act.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_as_act.setToolTip("Save image copy to a new file (Ctrl+Shift+S)")
        save_as_act.triggered.connect(self.save_image_copy)
        file_menu.addAction(save_as_act)

        discard_act = QAction("Discard Adjustments", self)
        discard_act.setShortcut(QKeySequence("Ctrl+D"))
        discard_act.setToolTip("Discard image adjustments and revert to original (Ctrl+D)")
        discard_act.triggered.connect(self.discard_adjustments)
        file_menu.addAction(discard_act)

        file_menu.addSeparator()

        exit_act = QAction("Exit", self)
        exit_act.setShortcut("Ctrl+Q")
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        # Edit Menu
        edit_menu = menubar.addMenu("Edit")

        undo_act = QAction("Undo", self)
        undo_act.setShortcut(QKeySequence.StandardKey.Undo)
        undo_act.triggered.connect(self.undo_adjustment)
        edit_menu.addAction(undo_act)

        redo_act = QAction("Redo", self)
        redo_act.setShortcut(QKeySequence.StandardKey.Redo)
        redo_act.triggered.connect(self.redo_adjustment)
        edit_menu.addAction(redo_act)

        edit_menu.addSeparator()

        copy_path_act = QAction("Copy File Path", self)
        copy_path_act.triggered.connect(self.copy_path_to_clipboard)
        edit_menu.addAction(copy_path_act)

        edit_menu.addSeparator()

        rename_act = QAction("Rename File...", self)
        rename_act.setShortcut(QKeySequence("F2"))
        rename_act.triggered.connect(self.rename_current_image)
        edit_menu.addAction(rename_act)

        delete_act = QAction("Delete File", self)
        delete_act.setShortcut(QKeySequence.StandardKey.Delete)
        delete_act.triggered.connect(self.delete_current_image)
        edit_menu.addAction(delete_act)


        # View Menu
        view_menu = menubar.addMenu("View")
        next_act = QAction("Next Image", self)
        next_act.setShortcut(QKeySequence("Ctrl+N"))
        next_act.triggered.connect(self.show_next_image)
        view_menu.addAction(next_act)

        prev_act = QAction("Previous Image", self)
        prev_act.setShortcut(QKeySequence("Ctrl+P"))
        prev_act.triggered.connect(self.show_prev_image)
        view_menu.addAction(prev_act)

        view_menu.addSeparator()

        sidebar_act = QAction("Image Adjustments Sidebar", self)
        sidebar_act.setShortcut(QKeySequence("Ctrl+L"))
        sidebar_act.triggered.connect(self.toggle_adjustment_sidebar)
        view_menu.addAction(sidebar_act)

        # Zoom Menu
        zoom_menu = menubar.addMenu("Zoom")
        zoom_in_act = QAction("Zoom In", self)
        zoom_in_act.setShortcut(QKeySequence("Ctrl++"))
        zoom_in_act.triggered.connect(self.zoom_in)
        zoom_menu.addAction(zoom_in_act)

        zoom_out_act = QAction("Zoom Out", self)
        zoom_out_act.setShortcut(QKeySequence("Ctrl+-"))
        zoom_out_act.triggered.connect(self.zoom_out)
        zoom_menu.addAction(zoom_out_act)

        fit_act = QAction("Fit to Window", self)
        fit_act.setShortcut(QKeySequence("Ctrl+F"))
        fit_act.triggered.connect(self.fit_to_view)
        zoom_menu.addAction(fit_act)

        actual_act = QAction("Actual Size (100%)", self)
        actual_act.setShortcut(QKeySequence("/"))
        actual_act.triggered.connect(self.zoom_100)
        zoom_menu.addAction(actual_act)

        # Modify Menu
        modify_menu = menubar.addMenu("Modify")
        rot_r_act = QAction("Rotate Right 90°", self)
        rot_r_act.setShortcut(QKeySequence("Ctrl+R"))
        rot_r_act.triggered.connect(lambda: self.rotate_image(90))
        modify_menu.addAction(rot_r_act)

        rot_l_act = QAction("Rotate Left 90°", self)
        rot_l_act.setShortcut(QKeySequence("Ctrl+Shift+R"))
        rot_l_act.triggered.connect(lambda: self.rotate_image(-90))
        modify_menu.addAction(rot_l_act)


        modify_menu.addSeparator()

        invert_act = QAction("Invert Colors", self)
        invert_act.setShortcut(QKeySequence("Ctrl+I"))
        invert_act.triggered.connect(self.toggle_invert_colors)
        modify_menu.addAction(invert_act)

        self.act_grayscale = QAction("Grayscale (Pure Black to Pure White)", self)
        self.act_grayscale.setCheckable(True)
        self.act_grayscale.setShortcut(QKeySequence("Ctrl+G"))
        self.act_grayscale.triggered.connect(self.toggle_grayscale)
        modify_menu.addAction(self.act_grayscale)

        self.act_binary_bw = QAction("Pure Black & White (Binary 2-Tone)", self)
        self.act_binary_bw.setCheckable(True)
        self.act_binary_bw.setShortcut(QKeySequence("Ctrl+B"))
        self.act_binary_bw.triggered.connect(self.toggle_binary_bw)
        modify_menu.addAction(self.act_binary_bw)

        reset_adj_act = QAction("Reset All Adjustments", self)
        reset_adj_act.triggered.connect(self.sidebar.reset_all_adjustments)
        modify_menu.addAction(reset_adj_act)

        # Tools Menu
        tools_menu = menubar.addMenu("Tools")
        prop_act = QAction("File Properties", self)
        prop_act.triggered.connect(self.show_file_properties)
        tools_menu.addAction(prop_act)

        # Help Menu
        help_menu = menubar.addMenu("Help")

        shortcuts_action = QAction("Keyboard Shortcuts", self)
        shortcuts_action.setShortcut(QKeySequence("Ctrl+K"))
        shortcuts_action.triggered.connect(self.show_keyboard_shortcuts)
        help_menu.addAction(shortcuts_action)

        update_act = QAction("Check for Updates...", self)
        update_act.triggered.connect(lambda: check_for_updates_async(self, silent=False, callback=self._on_update_check_finished))
        help_menu.addAction(update_act)

        about_act = QAction("About SPS Image Viewer", self)
        about_act.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_act)

        # Right-aligned Corner Container in MenuBar (Version label + Update button)
        corner_widget = QWidget(self)
        corner_layout = QHBoxLayout(corner_widget)
        corner_layout.setContentsMargins(0, 0, 6, 0)
        corner_layout.setSpacing(10)

        version_lbl = QLabel(f"Version : v{APP_VERSION}", self)
        version_lbl.setStyleSheet("""
            QLabel {
                color: #64748b;
                font-size: 11px;
                font-weight: 600;
            }
        """)
        corner_layout.addWidget(version_lbl)

        self.btn_update = QPushButton("Check for Updates", self)
        self.btn_update.setCursor(Qt.CursorShape.PointingHandCursor)
        self._set_update_button_style(is_available=False)
        self.btn_update.clicked.connect(self._on_update_button_clicked)
        corner_layout.addWidget(self.btn_update)

        menubar.setCornerWidget(corner_widget, Qt.Corner.TopRightCorner)

    def _set_update_button_style(self, is_available: bool = False):
        if is_available:
            self.btn_update.setStyleSheet("""
                QPushButton {
                    background-color: #10b981;
                    color: #ffffff;
                    border: none;
                    border-radius: 3px;
                    padding: 3px 10px;
                    font-size: 11px;
                    font-weight: 600;
                    margin-top: 2px;
                    margin-bottom: 2px;
                }
                QPushButton:hover {
                    background-color: #059669;
                }
                QPushButton:pressed {
                    background-color: #047857;
                }
            """)
        else:
            self.btn_update.setStyleSheet("""
                QPushButton {
                    background-color: #0284c7;
                    color: #ffffff;
                    border: none;
                    border-radius: 3px;
                    padding: 3px 10px;
                    font-size: 11px;
                    font-weight: 600;
                    margin-top: 2px;
                    margin-bottom: 2px;
                }
                QPushButton:hover {
                    background-color: #0369a1;
                }
                QPushButton:pressed {
                    background-color: #075985;
                }
            """)

    def _on_update_button_clicked(self):
        if hasattr(self, '_latest_download_url') and self._latest_download_url:
            ver = getattr(self, '_latest_version', 'new version')
            prompt = f"A new version ({ver}) is available!\n\nDo you want to update now?"
            reply = QMessageBox.question(self, "Update Available", prompt, 
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                download_and_apply_update(self._latest_download_url, getattr(self, '_latest_asset_name', ''), self)
        else:
            check_for_updates_async(self, silent=False, callback=self._on_update_check_finished)

    def _on_update_check_finished(self, success: bool, msg: str, download_url: str, asset_name: str, latest_version: str):
        """Callback when update check completes. Shows button with Update_{version} if an update is found."""
        if success and latest_version:
            self._latest_download_url = download_url
            self._latest_asset_name = asset_name
            self._latest_version = latest_version
            self.btn_update.setText(f"Update_{latest_version}")
            self._set_update_button_style(is_available=True)
            self.btn_update.show()
        else:
            self._latest_download_url = None
            self._latest_asset_name = None
            self._latest_version = None
            self.btn_update.setText("Check for Updates")
            self._set_update_button_style(is_available=False)
            self.btn_update.show()

    def _create_toolbars(self):
        # 1. Navigation & View Toolbar
        tb_nav = QToolBar("Navigation Controls", self)
        tb_nav.setObjectName("NavToolBar")
        tb_nav.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb_nav)

        btn_browse = QToolButton()
        btn_browse.setText("📁 Browse")
        btn_browse.setToolTip("Browse and open image or .sps file")
        btn_browse.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn_browse.clicked.connect(self.select_and_open_file)
        tb_nav.addWidget(btn_browse)

        tb_nav.addSeparator()

        # Image dropdown and clickable counter section
        image_selector_group = QWidget()
        image_selector_group.setFixedHeight(30)
        image_selector_layout = QHBoxLayout(image_selector_group)
        image_selector_layout.setContentsMargins(4, 0, 4, 0)
        image_selector_layout.setSpacing(6)

        image_label = QLabel("Images:")
        image_label.setStyleSheet("font-weight: bold; color: #0f172a;")
        image_selector_layout.addWidget(image_label)

        self.image_dropdown = QComboBox()
        self.image_dropdown.setFixedSize(140, 26)
        self.image_dropdown.setStyleSheet("""
            QComboBox {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 3px;
                padding: 2px 6px;
                font-size: 11px;
                color: #0f172a;
            }
            QComboBox::drop-down {
                border: none;
            }
        """)
        self.image_dropdown.currentIndexChanged.connect(self.on_image_dropdown_changed)
        image_selector_layout.addWidget(self.image_dropdown)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("background-color: #cbd5e1; max-width: 2px;")
        image_selector_layout.addWidget(separator)

        self.image_count_label = ClickableLabel()
        self.image_count_label.setFixedSize(70, 26)
        self.image_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_count_label.setText("0 / 0 ")
        self.image_count_label.setStyleSheet("""
            QLabel {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 3px;
                font-weight: bold;
                color: #0f172a;
                font-size: 11px;
            }
            QLabel:hover {
                background-color: #e2e8f0;
                border-color: #0284c7;
            }
        """)
        self.image_count_label.clicked.connect(self._on_image_count_label_clicked)
        image_selector_layout.addWidget(self.image_count_label)

        tb_nav.addWidget(image_selector_group)

        btn_prev = QToolButton()
        btn_prev.setText("◀")
        btn_prev.setToolTip("Previous Image (Ctrl+P / Backspace)")
        btn_prev.clicked.connect(self.show_prev_image)
        tb_nav.addWidget(btn_prev)

        btn_next = QToolButton()
        btn_next.setText("▶")
        btn_next.setToolTip("Next Image (Ctrl+N / Space)")
        btn_next.clicked.connect(self.show_next_image)
        tb_nav.addWidget(btn_next)

        tb_nav.addSeparator()

        btn_fit = QToolButton()
        btn_fit.setText("↔ Fit")
        btn_fit.setToolTip("Fit Image to Window (Ctrl+F)")
        btn_fit.clicked.connect(self.fit_to_view)
        tb_nav.addWidget(btn_fit)

        btn_100 = QToolButton()
        btn_100.setText("1:1")
        btn_100.setToolTip("Actual Size 100% Zoom (Slash '/')")
        btn_100.clicked.connect(self.zoom_100)
        tb_nav.addWidget(btn_100)

        btn_zoom_in = QToolButton()
        btn_zoom_in.setText("🔍+")
        btn_zoom_in.setToolTip("Zoom In (Ctrl++)")
        btn_zoom_in.clicked.connect(self.zoom_in)
        tb_nav.addWidget(btn_zoom_in)

        btn_zoom_out = QToolButton()
        btn_zoom_out.setText("🔍-")
        btn_zoom_out.setToolTip("Zoom Out (Ctrl+-)")
        btn_zoom_out.clicked.connect(self.zoom_out)
        tb_nav.addWidget(btn_zoom_out)

        btn_new_window = QToolButton()
        btn_new_window.setText("🗗 New Window")
        btn_new_window.setToolTip("Open next image in a new window (Ctrl+Shift+N)")
        btn_new_window.clicked.connect(self.open_current_in_new_window)
        tb_nav.addWidget(btn_new_window)

        # 2. Edit & Actions Toolbar
        tb_edit = QToolBar("Edit & Adjustments", self)
        tb_edit.setObjectName("EditToolBar")
        tb_edit.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb_edit)

        btn_rot_l = QToolButton()
        btn_rot_l.setText("⟲ 90°")
        btn_rot_l.setToolTip("Rotate Left 90° (Ctrl+Shift+R)")
        btn_rot_l.clicked.connect(lambda: self.rotate_image(-90))
        tb_edit.addWidget(btn_rot_l)

        btn_rot_r = QToolButton()
        btn_rot_r.setText("⟳ 90°")
        btn_rot_r.setToolTip("Rotate Right 90° (Ctrl+R)")
        btn_rot_r.clicked.connect(lambda: self.rotate_image(90))
        tb_edit.addWidget(btn_rot_r)

        btn_invert = QToolButton()
        btn_invert.setText("🌗 Invert")
        btn_invert.setToolTip("Invert Colors (Ctrl+I)")
        btn_invert.clicked.connect(self.toggle_invert_colors)
        tb_edit.addWidget(btn_invert)

        self.btn_grayscale = QToolButton()
        self.btn_grayscale.setText("⬛ Grayscale")
        self.btn_grayscale.setCheckable(True)
        self.btn_grayscale.setToolTip("Toggle Full-Range Grayscale (Pure Black to Pure White) (Ctrl+G)")
        self.btn_grayscale.clicked.connect(self.toggle_grayscale)
        tb_edit.addWidget(self.btn_grayscale)

        self.btn_binary_bw = QToolButton()
        self.btn_binary_bw.setText("🔲 Pure B&W")
        self.btn_binary_bw.setCheckable(True)
        self.btn_binary_bw.setToolTip("Toggle Pure Black & White (Binary / 2-Tone) (Ctrl+B)")
        self.btn_binary_bw.clicked.connect(self.toggle_binary_bw)
        tb_edit.addWidget(self.btn_binary_bw)

        tb_edit.addSeparator()

        # Save, Discard, Save As, Delete
        self.btn_save = QToolButton()
        self.btn_save.setObjectName("btn_save")
        self.btn_save.setText("💾 Save")
        self.btn_save.setToolTip("Save Adjustments to File (Ctrl+S)")
        self.btn_save.clicked.connect(self.save_current_image)
        tb_edit.addWidget(self.btn_save)

        self.btn_discard = QToolButton()
        self.btn_discard.setObjectName("btn_discard")
        self.btn_discard.setText("↩ Discard")
        self.btn_discard.setToolTip("Discard Adjustments and Revert to Original (Ctrl+D)")
        self.btn_discard.clicked.connect(self.discard_adjustments)
        tb_edit.addWidget(self.btn_discard)

        btn_save_as = QToolButton()
        btn_save_as.setText("📁 Save As")
        btn_save_as.setToolTip("Save Image Copy As (Ctrl+Shift+S)")
        btn_save_as.clicked.connect(self.save_image_copy)
        tb_edit.addWidget(btn_save_as)

        btn_delete = QToolButton()
        btn_delete.setObjectName("btn_delete")
        btn_delete.setText("🗑 Delete")
        btn_delete.setToolTip("Delete File Permanently (Delete)")
        btn_delete.clicked.connect(self.delete_current_image)
        tb_edit.addWidget(btn_delete)

        tb_edit.addSeparator()

        btn_sidebar = QToolButton()
        btn_sidebar.setText("☀ Adjustments")
        btn_sidebar.setToolTip("Toggle Image Adjustments Sidebar (Ctrl+L)")
        btn_sidebar.clicked.connect(self.toggle_adjustment_sidebar)
        tb_edit.addWidget(btn_sidebar)

        btn_info = QToolButton()
        btn_info.setText("ℹ")
        btn_info.setToolTip("Show Document File Properties")
        btn_info.clicked.connect(self.show_file_properties)
        tb_edit.addWidget(btn_info)

        self._setup_toolbar_overflow()

    def _setup_toolbar_overflow(self):
        """Ensure the toolbar overflow (3 dots / more actions) button is crisp and visible."""
        pix = QPixmap(24, 24)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#334155"))
        p.setPen(Qt.PenStyle.NoPen)
        for x in [5, 12, 19]:
            p.drawEllipse(x - 2, 10, 4, 4)
        p.end()
        dots_icon = QIcon(pix)

        for tb in self.findChildren(QToolBar):
            ext = tb.findChild(QToolButton, "qt_toolbar_ext_button")
            if ext:
                ext.setIcon(dots_icon)
                ext.setText("...")
                ext.setToolTip("More Tools & Actions (···)")


    def show_keyboard_shortcuts(self):
        """Show keyboard shortcuts reference with proper geometry and scrollbars"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Keyboard Shortcuts")
        dialog.setGeometry(300, 200, 700, 550)
        dialog.setMinimumSize(550, 400)

        dialog.setStyleSheet("""
            QDialog, QWidget#ScrollContent {
                background-color: #ffffff;
                color: #0f172a;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                color: #0f172a;
                font-size: 12px;
                background-color: transparent;
            }
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-weight: 500;
                min-width: 90px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
            QPushButton:pressed {
                background-color: #075985;
            }
            QPushButton#CloseBtn {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
            }
            QPushButton#CloseBtn:hover {
                background-color: #f1f5f9;
            }
            QScrollArea {
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                background-color: #ffffff;
            }
            QScrollBar:vertical {
                border: none;
                background: #f1f5f9;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: #cbd5e1;
                min-height: 20px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical:hover {
                background: #94a3b8;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
            }
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header_lbl = QLabel("⌨️ Keyboard Shortcuts Reference")
        header_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #0f172a; background-color: transparent;")
        layout.addWidget(header_lbl)

        # Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 4px;")
        scroll.viewport().setStyleSheet("background-color: #ffffff;")

        content_widget = QWidget()
        content_widget.setObjectName("ScrollContent")
        content_widget.setStyleSheet("background-color: #ffffff;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(16, 16, 16, 16)
        content_layout.setSpacing(12)

        shortcuts_data = [
            ("Navigation", [
                ("Next Image", "Ctrl+N  /  Space  /  PageDown  /  Right Arrow"),
                ("Previous Image", "Ctrl+P  /  Backspace  /  PageUp  /  Left Arrow"),
                ("Scroll Image", "Arrow Keys (Up, Down, Left, Right)"),
                ("Pan Image", "Ctrl + Arrow Keys"),
            ]),
            ("Zooming", [
                ("Zoom In", "Ctrl + '+'  /  '+'"),
                ("Zoom Out", "Ctrl + '-'  /  '-'"),
                ("Fit to Window", "Ctrl+F"),
                ("Actual Size (100%)", "/ (Slash)"),
                ("Smooth Zoom", "Mouse Scroll Wheel"),
            ]),
            ("Image Adjustments & Effects", [
                ("Invert Colors", "Ctrl+I"),
                ("Grayscale", "Ctrl+G"),
                ("Rotate Right 90°", "Ctrl+R"),
                ("Rotate Left 90°", "Ctrl+Shift+R"),
                ("Toggle Adjustments Sidebar", "Ctrl+L"),
            ]),
            ("File Operations & General", [
                ("Rename File", "F2"),
                ("Delete File", "Delete"),
                ("Save Copy As", "Ctrl+S"),
                ("Keyboard Shortcuts Reference", "Ctrl+K"),
                ("Exit Application", "Ctrl+Q"),
                ("Close Sidebar / Dialog", "Escape"),
            ]),
        ]

        for section_title, items in shortcuts_data:
            sec_lbl = QLabel(section_title)
            sec_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #0284c7; margin-top: 4px; background-color: transparent;")
            content_layout.addWidget(sec_lbl)

            table_frame = QFrame()
            table_frame.setStyleSheet("background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 4px; padding: 4px;")
            table_layout = QVBoxLayout(table_frame)
            table_layout.setContentsMargins(8, 6, 8, 6)
            table_layout.setSpacing(6)

            for action_name, shortcut_str in items:
                row_layout = QHBoxLayout()
                lbl_act = QLabel(action_name)
                lbl_act.setStyleSheet("font-weight: 500; color: #1e293b; background-color: transparent;")
                lbl_key = QLabel(shortcut_str)
                lbl_key.setStyleSheet("font-weight: bold; color: #0f172a; background-color: #e2e8f0; padding: 2px 6px; border-radius: 3px;")
                row_layout.addWidget(lbl_act)
                row_layout.addStretch()
                row_layout.addWidget(lbl_key)
                table_layout.addLayout(row_layout)

            content_layout.addWidget(table_frame)

        content_layout.addStretch()
        scroll.setWidget(content_widget)
        layout.addWidget(scroll)

        # Buttons layout
        button_layout = QHBoxLayout()

        # Add Export button
        export_btn = QPushButton("📄 Export to Text")
        export_btn.clicked.connect(lambda: self.export_shortcuts_to_text(shortcuts_data))
        button_layout.addWidget(export_btn)

        button_layout.addStretch()

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setObjectName("CloseBtn")
        close_btn.clicked.connect(dialog.accept)
        close_btn.setFixedWidth(100)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

        dialog.exec()

    def export_shortcuts_to_text(self, shortcuts_data):
        """Export shortcuts list to a formatted text file."""
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Shortcuts Reference", "Keyboard_Shortcuts.txt", "Text Files (*.txt)")
        if not file_path:
            return

        try:
            lines = [
                "==========================================",
                "SPS IMAGE VIEWER - KEYBOARD SHORTCUTS",
                "==========================================",
                ""
            ]
            for section_title, items in shortcuts_data:
                lines.append(f"[{section_title.upper()}]")
                for action_name, shortcut_str in items:
                    lines.append(f"  {action_name:<30} : {shortcut_str}")
                lines.append("")

            with open(file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))

        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export shortcuts file:\n{str(e)}")

    def on_image_dropdown_changed(self, index: int):
        """Handler when user selects an image from the dropdown."""
        if hasattr(self, 'image_dropdown') and self.image_dropdown.signalsBlocked():
            return
        if not self.confirm_save_if_modified():
            self.image_dropdown.blockSignals(True)
            self.image_dropdown.setCurrentIndex(self.current_folder_index)
            self.image_dropdown.blockSignals(False)
            return
        if 0 <= index < len(self.folder_files):
            target_file = self.folder_files[index]
            if target_file != self.current_file_path:
                self.load_image(target_file, preserve_view=True)

    def _on_image_count_label_clicked(self):
        """Handler when user clicks the image count label. Prompts for target image index."""
        if not self.folder_files:
            return
        total = len(self.folder_files)
        curr = self.current_folder_index + 1 if self.current_folder_index >= 0 else 1
        num, ok = QInputDialog.getInt(
            self, "Go to Image", f"Enter image number (1 - {total}):",
            value=curr, min=1, max=total
        )
        if ok and 1 <= num <= total:
            if not self.confirm_save_if_modified():
                return
            target_file = self.folder_files[num - 1]
            self.load_image(target_file, preserve_view=False)

    def rename_current_image(self):
        """Show Rename File dialog, validate input, and rename file on disk."""
        if not self.current_file_path or not os.path.exists(self.current_file_path):
            QMessageBox.information(self, "Rename File", "No active image file loaded to rename.")
            return

        dialog = RenameFileDialog(self.current_file_path, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_name = dialog.new_filename
            old_path = self.current_file_path
            dir_name = os.path.dirname(old_path)
            new_path = os.path.join(dir_name, new_name)

            try:
                os.rename(old_path, new_path)
            except Exception as e:
                QMessageBox.critical(self, "Rename Error", f"Failed to rename file on disk:\n{str(e)}")
                return

            # Transfer cached image state if exists
            if old_path in self.image_states:
                self.image_states[new_path] = self.image_states.pop(old_path)

            self.current_file_path = new_path
            if 0 <= self.current_folder_index < len(self.folder_files):
                self.folder_files[self.current_folder_index] = new_path
            self._force_dropdown_refresh = True

            self.setWindowTitle(f"{new_name} - {APP_TITLE}")
            self.status_bar.showMessage(f"File successfully renamed to: {new_name}", 4000)

    def delete_current_image(self):
        """Delete currently displayed image file from disk after user confirmation."""
        if not self.current_file_path or not os.path.exists(self.current_file_path):
            QMessageBox.information(self, "Delete File", "No active image file loaded to delete.")
            return

        filename = os.path.basename(self.current_file_path)
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete this file permanently?\n\n{filename}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        target_path = self.current_file_path
        try:
            os.remove(target_path)
        except Exception as e:
            QMessageBox.critical(self, "Delete Error", f"Failed to delete file from disk:\n{str(e)}")
            return

        if target_path in self.image_states:
            del self.image_states[target_path]

        idx = self.current_folder_index
        if target_path in self.folder_files:
            self.folder_files.remove(target_path)
        self._force_dropdown_refresh = True

        if self.folder_files:
            next_idx = min(idx, len(self.folder_files) - 1)
            next_file = self.folder_files[next_idx]
            self.load_image(next_file, preserve_view=False)
            self.status_bar.showMessage(f"Deleted {filename}. Loaded next image.", 4000)
        else:
            self.show_default_logo()
            self.status_bar.showMessage(f"Deleted {filename}. No images remaining in folder.", 4000)

    def toggle_adjustment_sidebar(self):
        if not self.sidebar.isHidden():
            self.sidebar.hide()
            # Reset all image adjustments when closing sidebar
            self.is_inverted = False
            self.sidebar.reset_all_adjustments()
            self._render_scene_pixmap(fit=False)
            self.view.viewport().unsetCursor()
        else:
            self.sidebar.show()
            if self.base_qimage and not self.base_qimage.isNull():
                self.sidebar.update_histograms(self.base_qimage)

    def _on_eyedropper_mode_changed(self, mode: Optional[str]):
        try:
            if mode:
                self.view.viewport().setCursor(Qt.CursorShape.CrossCursor)
            else:
                self.view.viewport().unsetCursor()
        except Exception as e:
            traceback.print_exc()

    def on_image_pixel_picked(self, scene_pos: QPointF) -> bool:
        try:
            if not self.base_qimage or self.base_qimage.isNull():
                return False

            if self.current_rotation != 0:
                inv_transform, ok = QTransform().rotate(self.current_rotation).inverted()
                if ok:
                    pt = inv_transform.map(scene_pos)
                    ix, iy = int(round(pt.x())), int(round(pt.y()))
                else:
                    ix, iy = int(round(scene_pos.x())), int(round(scene_pos.y()))
            else:
                ix, iy = int(round(scene_pos.x())), int(round(scene_pos.y()))

            if 0 <= ix < self.base_qimage.width() and 0 <= iy < self.base_qimage.height():
                color = self.base_qimage.pixelColor(ix, iy)
                self.sidebar.apply_eyedropper_sample(color.red(), color.green(), color.blue())
                return True
            return False
        except Exception as e:
            traceback.print_exc()
            return False

    def set_application_theme(self, theme_name: str = "Light Theme"):
        self.current_theme_name = "Light Theme"
        app = QApplication.instance()
        if app:
            app.setStyleSheet(get_light_stylesheet())
        self.status_bar.showMessage("Application Theme: Light Theme active.", 3000)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        modifiers = event.modifiers()
        is_ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        is_shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

        if key == Qt.Key.Key_Escape:
            if hasattr(self, 'sidebar') and not self.sidebar.isHidden():
                if getattr(self.sidebar, 'active_picker', None):
                    self.sidebar.toggle_eyedropper(self.sidebar.active_picker)
                    event.accept()
                else:
                    self.cancel_adjustments()
                    event.accept()
            else:
                self.close()
                event.accept()

        elif key == Qt.Key.Key_Delete:
            self.delete_current_image()
            event.accept()

        elif key == Qt.Key.Key_PageUp:
            self.show_prev_image()
            event.accept()

        elif key == Qt.Key.Key_PageDown:
            self.show_next_image()
            event.accept()

        elif key == Qt.Key.Key_F2:
            self.rename_current_image()
            event.accept()

        elif is_ctrl and is_shift and key == Qt.Key.Key_R:
            self.rotate_image(-90)
            event.accept()

        elif key == Qt.Key.Key_Slash:
            self.zoom_100()
            event.accept()

        elif key == Qt.Key.Key_Space:
            self.show_next_image()
            event.accept()

        elif key == Qt.Key.Key_Backspace:
            self.show_prev_image()
            event.accept()

        elif is_ctrl and key == Qt.Key.Key_L:
            self.toggle_adjustment_sidebar()
            event.accept()

        elif is_ctrl and key == Qt.Key.Key_N:
            self.show_next_image()
            event.accept()

        elif is_ctrl and key == Qt.Key.Key_P:
            self.show_prev_image()
            event.accept()

        elif is_ctrl and key == Qt.Key.Key_F:
            self.fit_to_view()
            event.accept()

        elif is_ctrl and key == Qt.Key.Key_R:
            self.rotate_image(90)
            event.accept()

        elif is_ctrl and key == Qt.Key.Key_I:
            self.toggle_invert_colors()
            event.accept()

        elif is_ctrl and key == Qt.Key.Key_G:
            self.toggle_grayscale()
            event.accept()

        elif is_ctrl and is_shift and key == Qt.Key.Key_S:
            self.save_image_copy()
            event.accept()

        elif is_ctrl and key == Qt.Key.Key_S:
            self.save_current_image()
            event.accept()

        elif is_ctrl and key == Qt.Key.Key_D:
            self.discard_adjustments()
            event.accept()

        elif is_ctrl and (key == Qt.Key.Key_Y or (is_shift and key == Qt.Key.Key_Z)):
            self.redo_adjustment()
            event.accept()

        elif is_ctrl and key == Qt.Key.Key_Z:
            self.undo_adjustment()
            event.accept()

        elif is_ctrl and key == Qt.Key.Key_K:
            self.show_keyboard_shortcuts()
            event.accept()

        elif key == Qt.Key.Key_Up:
            v_scroll = self.view.verticalScrollBar()
            if v_scroll and v_scroll.maximum() > 0:
                step = 600 if is_ctrl else 140
                duration = 60 if is_ctrl else 50
                smooth_scroll_bar(v_scroll, -step, duration=duration)
            else:
                self.show_prev_image()
            event.accept()

        elif key == Qt.Key.Key_Down:
            v_scroll = self.view.verticalScrollBar()
            if v_scroll and v_scroll.maximum() > 0:
                step = 600 if is_ctrl else 140
                duration = 60 if is_ctrl else 50
                smooth_scroll_bar(v_scroll, step, duration=duration)
            else:
                self.show_next_image()
            event.accept()

        elif key == Qt.Key.Key_Right:
            h_scroll = self.view.horizontalScrollBar()
            if h_scroll and h_scroll.maximum() > 0:
                step = 600 if is_ctrl else 140
                duration = 60 if is_ctrl else 50
                smooth_scroll_bar(h_scroll, step, duration=duration)
            else:
                self.show_next_image()
            event.accept()

        elif key == Qt.Key.Key_Left:
            h_scroll = self.view.horizontalScrollBar()
            if h_scroll and h_scroll.maximum() > 0:
                step = 600 if is_ctrl else 140
                duration = 60 if is_ctrl else 50
                smooth_scroll_bar(h_scroll, -step, duration=duration)
            else:
                self.show_prev_image()
            event.accept()

        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            rect = self.view.transform().mapRect(QRectF(0, 0, 1, 1))
            current_zoom = rect.width()
            if abs(current_zoom - 1.0) < 0.05:
                self.fit_to_view()
            else:
                self.zoom_100()
            event.accept()


        elif key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.zoom_in()
            event.accept()

        elif key == Qt.Key.Key_Minus:
            self.zoom_out()
            event.accept()

        elif key == Qt.Key.Key_0:
            self.fit_to_view()
            event.accept()

        elif key == Qt.Key.Key_1:
            self.zoom_100()
            event.accept()

        else:
            super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                file_path = urls[0].toLocalFile()
                if file_path and os.path.exists(file_path):
                    self.load_image(file_path, preserve_view=False)
                    event.acceptProposedAction()

    def open_current_in_new_window(self):
        """Opens the NEXT image (in the current folder) in a brand-new,
        independent viewer window - handy for comparing the current image
        against the next one side by side (e.g. drag one window to the
        left half of the screen, one to the right). Falls back to the
        current image if there's no next one (e.g. already on the last
        image, or no folder context)."""
        if not self.current_file_path:
            QMessageBox.information(self, "No Image Open", "Open an image first, then use this to view it in a second window.")
            return

        target_path = self.current_file_path
        if self.folder_files and 0 <= self.current_folder_index + 1 < len(self.folder_files):
            target_path = self.folder_files[self.current_folder_index + 1]

        # Constructed with start_file=None so it doesn't try to auto-load
        # with the default passphrase first (which would pop an
        # unnecessary password prompt for files using a custom one).
        new_window = SPSImageViewerWindow(start_file=None)
        new_window.current_passphrase = self.current_passphrase
        new_window.load_image(target_path, passphrase=self.current_passphrase, preserve_view=False)

        if not hasattr(self, "_child_windows"):
            self._child_windows = []
        # Drop references to any windows the user has already closed, so
        # this list doesn't grow forever over a long session.
        self._child_windows = [w for w in self._child_windows if w.isVisible()]
        self._child_windows.append(new_window)

        new_window.show()
        new_window.raise_()
        new_window.activateWindow()

    def select_and_open_file(self):
        file_dialog = QFileDialog(self, "Open Document Image or .sps / .pdf File")
        file_dialog.setNameFilter(
            "All Supported Documents & Images (*.sps *.pdf *.jpg *.jpeg *.png *.bmp *.gif *.tif *.tiff *.webp *.j2k *.jp2 *.jpf *.jpx *.jpm *.jxr *.ico *.svg);;"
            "PDF Documents (*.pdf);;"
            "SPS Encrypted Files (*.sps);;"
            "Standard & JPEG 2000 / Vector Images (*.jpg *.jpeg *.png *.bmp *.gif *.tif *.tiff *.webp *.j2k *.jp2 *.jpf *.jpx *.jpm *.jxr *.ico *.svg);;"
            "All Files (*.*)"
        )
        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            if selected_files:
                self.load_image(selected_files[0], preserve_view=False)

    def select_and_open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder Containing Images or Documents")
        if folder:
            files = [
                os.path.join(folder, f) for f in sorted(os.listdir(folder))
                if os.path.splitext(f)[1].lower() in ALL_SUPPORTED_EXTENSIONS
            ]
            if files:
                self.load_image(files[0], preserve_view=False)

    def save_image_copy(self):
        """Save Copy As (Ctrl+Shift+S) with all active adjustments and rotation applied."""
        if not self.current_pixmap or not self.base_qimage:
            return
        default_name = ""
        if self.current_file_path:
            base, ext = os.path.splitext(os.path.basename(self.current_file_path))
            default_name = f"{base}_edited{ext if ext.lower() not in ('.sps', '.pdf') else '.png'}"

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Image Copy As", default_name,
            "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg);;PDF Document (*.pdf);;WebP Image (*.webp);;BMP Image (*.bmp);;TIFF Image (*.tif *.tiff);;SPS Encrypted File (*.sps)"
        )
        if not file_path:
            return

        adj_params = dict(self.sidebar.get_adjustment_params())
        adj_params["exposure_warning"] = False  # Display aid only, never save to file
        adjusted_qimg = self._apply_full_adjustments_fast(self.base_qimage, adj_params)
        if self.current_rotation != 0:
            transform = QTransform().rotate(self.current_rotation)
            adjusted_qimg = adjusted_qimg.transformed(transform, Qt.TransformationMode.SmoothTransformation)

        ext = os.path.splitext(file_path)[1].lower()
        try:
            if ext == ".sps":
                from PyQt6.QtCore import QBuffer, QIODevice
                buf = QBuffer()
                buf.open(QIODevice.OpenModeFlag.WriteOnly)
                orig_fmt = self.file_metadata.get("format", "").upper()
                is_gray = adjusted_qimg.format() == QImage.Format.Format_Grayscale8
                if is_gray:
                    adjusted_qimg.save(buf, "JPEG" if orig_fmt in ("JPG", "JPEG") else "PNG", 95)
                elif orig_fmt in ("JPG", "JPEG") or not adjusted_qimg.hasAlphaChannel():
                    adjusted_qimg.save(buf, "JPEG", 95)
                else:
                    adjusted_qimg.save(buf, "PNG")
                raw_bytes = bytes(buf.data())
                meta = dict(self.file_metadata)
                meta["original_filename"] = os.path.basename(file_path)
                if is_gray:
                    meta["depth"] = 8
                    meta["color_mode"] = "Grayscale"
                encrypt_sps_file(raw_bytes, meta, file_path, passphrase=self.current_passphrase)
            elif ext == ".pdf":
                from PyQt6.QtGui import QPdfWriter, QPageSize, QPainter
                from PyQt6.QtCore import QSizeF, QMarginsF
                writer = QPdfWriter(file_path)
                writer.setPageSize(QPageSize(QSizeF(adjusted_qimg.width(), adjusted_qimg.height()), QPageSize.Unit.Point))
                writer.setResolution(72)
                writer.setPageMargins(QMarginsF(0, 0, 0, 0))
                painter = QPainter(writer)
                painter.drawImage(0, 0, adjusted_qimg)
                painter.end()
            else:
                saved = adjusted_qimg.save(file_path)
                if not saved:
                    from PIL import Image as PILImage
                    if adjusted_qimg.format() == QImage.Format.Format_Grayscale8:
                        ptr = adjusted_qimg.bits()
                        ptr.setsize(adjusted_qimg.sizeInBytes())
                        pil_img = PILImage.frombytes("L", (adjusted_qimg.width(), adjusted_qimg.height()), bytes(ptr))
                        pil_img.save(file_path)
                    else:
                        qimg_rgba = adjusted_qimg.convertToFormat(QImage.Format.Format_RGBA8888)
                        ptr = qimg_rgba.bits()
                        ptr.setsize(qimg_rgba.sizeInBytes())
                        pil_img = PILImage.frombytes("RGBA", (qimg_rgba.width(), qimg_rgba.height()), bytes(ptr))
                        pil_img.save(file_path)

            self.status_bar.showMessage(f"Saved image copy to: {os.path.basename(file_path)}", 4000)
        except Exception as ex:
            QMessageBox.critical(self, "Save As Error", f"Failed to save image copy:\n{str(ex)}")

    def save_current_image(self) -> bool:
        """Save all active adjustments permanently into the current image file (ACDSee Save)."""
        if not self.current_file_path or not os.path.exists(self.current_file_path):
            return False
        if not self.base_qimage or self.base_qimage.isNull():
            return False

        adj_params = dict(self.sidebar.get_adjustment_params())
        adj_params["exposure_warning"] = False  # Display aid only, never save to file
        adjusted_qimg = self._apply_full_adjustments_fast(self.base_qimage, adj_params)
        if self.current_rotation != 0:
            transform = QTransform().rotate(self.current_rotation)
            adjusted_qimg = adjusted_qimg.transformed(transform, Qt.TransformationMode.SmoothTransformation)

        target_path = self.current_file_path
        ext = os.path.splitext(target_path)[1].lower()

        try:
            if ext == ".sps" or is_sps_file(target_path):
                from PyQt6.QtCore import QBuffer, QIODevice
                buf = QBuffer()
                buf.open(QIODevice.OpenModeFlag.WriteOnly)
                orig_fmt = self.file_metadata.get("format", "").upper()
                is_gray = adjusted_qimg.format() == QImage.Format.Format_Grayscale8
                if is_gray:
                    adjusted_qimg.save(buf, "JPEG" if orig_fmt in ("JPG", "JPEG") else "PNG", 95)
                elif orig_fmt in ("JPG", "JPEG") or not adjusted_qimg.hasAlphaChannel():
                    adjusted_qimg.save(buf, "JPEG", 95)
                else:
                    adjusted_qimg.save(buf, "PNG")
                raw_bytes = bytes(buf.data())
                meta = dict(self.file_metadata)
                if is_gray:
                    meta["depth"] = 8
                    meta["color_mode"] = "Grayscale"
                encrypt_sps_file(raw_bytes, meta, target_path, passphrase=self.current_passphrase)
            elif ext == ".pdf":
                from PyQt6.QtGui import QPdfWriter, QPageSize, QPainter
                from PyQt6.QtCore import QSizeF, QMarginsF
                writer = QPdfWriter(target_path)
                writer.setPageSize(QPageSize(QSizeF(adjusted_qimg.width(), adjusted_qimg.height()), QPageSize.Unit.Point))
                writer.setResolution(72)
                writer.setPageMargins(QMarginsF(0, 0, 0, 0))
                painter = QPainter(writer)
                painter.drawImage(0, 0, adjusted_qimg)
                painter.end()
            else:
                saved = adjusted_qimg.save(target_path)
                if not saved:
                    from PIL import Image as PILImage
                    if adjusted_qimg.format() == QImage.Format.Format_Grayscale8:
                        ptr = adjusted_qimg.bits()
                        ptr.setsize(adjusted_qimg.sizeInBytes())
                        pil_img = PILImage.frombytes("L", (adjusted_qimg.width(), adjusted_qimg.height()), bytes(ptr))
                        pil_img.save(target_path)
                    else:
                        qimg_rgba = adjusted_qimg.convertToFormat(QImage.Format.Format_RGBA8888)
                        ptr = qimg_rgba.bits()
                        ptr.setsize(qimg_rgba.sizeInBytes())
                        pil_img = PILImage.frombytes("RGBA", (qimg_rgba.width(), qimg_rgba.height()), bytes(ptr))
                        pil_img.save(target_path)

            # Update in-memory base cache with the newly saved image
            self.base_qimage = adjusted_qimg
            self.current_pixmap = QPixmap.fromImage(adjusted_qimg)
            self._cache_put(target_path, self.base_qimage, dict(self.file_metadata))

            # Reset adjustments to neutral since they are now baked into base image
            self.current_rotation = 0
            self.is_inverted = False
            self.sidebar.blockSignals(True)
            self.sidebar.reset_all_adjustments()
            self.sidebar.blockSignals(False)
            self._sync_grayscale_ui()
            self._set_modified(False)

            self._render_scene_pixmap(fit=False)
            self.sidebar.update_histograms(self.base_qimage)
            self.status_bar.showMessage(f"Saved changes to: {os.path.basename(target_path)}", 4000)
            return True
        except Exception as ex:
            QMessageBox.critical(self, "Save Error", f"Failed to save image changes:\n{str(ex)}")
            return False

    def discard_adjustments(self):
        """Discard all adjustments on the current image and revert to original on disk (ACDSee Discard)."""
        if not self.current_file_path or not os.path.exists(self.current_file_path):
            return

        # Evict from decode cache and reload clean original image from disk
        self._decode_cache.pop(self.current_file_path, None)
        ext = os.path.splitext(self.current_file_path)[1].lower()
        if ext == ".sps" or is_sps_file(self.current_file_path):
            self._load_sps_image(self.current_file_path, self.current_passphrase)
        else:
            self._load_standard_image(self.current_file_path)

        self.current_rotation = 0
        self.is_inverted = False
        self.sidebar.blockSignals(True)
        self.sidebar.reset_all_adjustments()
        self.sidebar.blockSignals(False)
        self._sync_grayscale_ui()
        self._applied_undo_stack.clear()
        self._applied_redo_stack.clear()
        self._update_sidebar_undo_redo()
        self._set_modified(False)

        self._render_scene_pixmap(fit=False)
        self.sidebar.update_histograms(self.base_qimage)
        self.status_bar.showMessage(f"Discarded adjustments for {os.path.basename(self.current_file_path)}. Reverted to original.", 4000)

    def apply_adjustments_to_image(self):
        """
        Commit current adjustments into the working image (base_qimage),
        push previous base_qimage snapshot to applied undo stack,
        and reset sidebar sliders to neutral (matching ACDSee Edit Apply).
        """
        if not self.base_qimage or self.base_qimage.isNull():
            return

        if not self._is_adjustment_active():
            self.status_bar.showMessage("No adjustments to apply.", 3000)
            return

        adj_params = dict(self.sidebar.get_adjustment_params())
        adj_params["exposure_warning"] = False  # Display aid only, never bake into image
        adjusted_qimg = self._apply_full_adjustments_fast(self.base_qimage, adj_params)
        if self.current_rotation != 0:
            transform = QTransform().rotate(self.current_rotation)
            adjusted_qimg = adjusted_qimg.transformed(transform, Qt.TransformationMode.SmoothTransformation)
            self.current_rotation = 0

        # Save snapshot of previous base_qimage and current sidebar state for Undo
        prev_snapshot = (self.base_qimage.copy(), self.sidebar.get_full_state())
        self._applied_undo_stack.append(prev_snapshot)
        self._applied_redo_stack.clear()

        # Update base_qimage with newly baked image
        self.base_qimage = adjusted_qimg
        self.current_pixmap = QPixmap.fromImage(adjusted_qimg)
        self.is_inverted = False

        # Reset sidebar adjustments to neutral
        self.sidebar.blockSignals(True)
        self.sidebar.reset_all_adjustments()
        self.sidebar.blockSignals(False)
        self._sync_grayscale_ui()

        self._set_modified(True)
        self._render_scene_pixmap(fit=False)
        self.sidebar.update_histograms(self.base_qimage)
        self._update_sidebar_undo_redo()
        self.status_bar.showMessage("Applied adjustments to working image.", 4000)

    def done_adjustments(self):
        """Commit current adjustments (if any) to working image and close sidebar (ACDSee Done)."""
        if self._is_adjustment_active():
            self.apply_adjustments_to_image()
        self.toggle_adjustment_sidebar()

    def cancel_adjustments(self):
        """Discard uncommitted adjustments and close sidebar (ACDSee Cancel)."""
        self.sidebar.blockSignals(True)
        self.sidebar.reset_all_adjustments()
        self.sidebar.blockSignals(False)
        self._sync_grayscale_ui()
        self.current_rotation = 0
        self.is_inverted = False
        self._render_scene_pixmap(fit=False)
        self._set_modified(len(self._applied_undo_stack) > 0)
        self.toggle_adjustment_sidebar()
        self.status_bar.showMessage("Cancelled uncommitted adjustments.", 3000)

    def undo_adjustment(self):
        """Undo last adjustment (Ctrl+Z). Delegated to sidebar or applied image stack."""
        if hasattr(self, 'sidebar'):
            self.sidebar._on_undo_clicked()
            self._sync_grayscale_ui()

    def redo_adjustment(self):
        """Redo adjustment (Ctrl+Y or Ctrl+Shift+Z). Delegated to sidebar or applied image stack."""
        if hasattr(self, 'sidebar'):
            self.sidebar._on_redo_clicked()
            self._sync_grayscale_ui()

    def undo_applied_image(self):
        """Revert last 'Apply' commit, restoring previous base_qimage and sidebar state."""
        if not self._applied_undo_stack:
            return

        curr_snapshot = (self.base_qimage.copy(), self.sidebar.get_full_state())
        self._applied_redo_stack.append(curr_snapshot)

        prev_qimg, prev_state = self._applied_undo_stack.pop()
        self.base_qimage = prev_qimg
        self.current_pixmap = QPixmap.fromImage(prev_qimg)

        self.sidebar.set_full_state(prev_state)
        self._sync_grayscale_ui()
        self._set_modified(len(self._applied_undo_stack) > 0 or self._is_adjustment_active())
        self._render_scene_pixmap(fit=False)
        self.sidebar.update_histograms(self.base_qimage)
        self._update_sidebar_undo_redo()
        self.status_bar.showMessage("Undid applied adjustments.", 3000)

    def redo_applied_image(self):
        """Redo previously undone 'Apply' commit."""
        if not self._applied_redo_stack:
            return

        curr_snapshot = (self.base_qimage.copy(), self.sidebar.get_full_state())
        self._applied_undo_stack.append(curr_snapshot)

        nxt_qimg, nxt_state = self._applied_redo_stack.pop()
        self.base_qimage = nxt_qimg
        self.current_pixmap = QPixmap.fromImage(nxt_qimg)

        self.sidebar.set_full_state(nxt_state)
        self._sync_grayscale_ui()
        self._set_modified(True)
        self._render_scene_pixmap(fit=False)
        self.sidebar.update_histograms(self.base_qimage)
        self._update_sidebar_undo_redo()
        self.status_bar.showMessage("Redid applied adjustments.", 3000)

    def _update_sidebar_undo_redo(self):
        if hasattr(self, 'sidebar'):
            can_undo_applied = len(self._applied_undo_stack) > 0
            can_redo_applied = len(self._applied_redo_stack) > 0
            self.sidebar._update_undo_redo_buttons(can_undo_applied=can_undo_applied, can_redo_applied=can_redo_applied)

    def confirm_save_if_modified(self) -> bool:
        """ACDSee-style confirmation prompt when navigating away or closing with unsaved adjustments."""
        if not self.is_modified or not self.current_file_path:
            return True

        filename = os.path.basename(self.current_file_path)
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Save Changes?")
        msg_box.setText(f"The image '{filename}' has unsaved adjustments.\n\nDo you want to save the changes before continuing?")
        msg_box.setIcon(QMessageBox.Icon.Question)
        btn_save = msg_box.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        btn_discard = msg_box.addButton("Discard", QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = msg_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        msg_box.setDefaultButton(btn_save)

        msg_box.exec()
        clicked = msg_box.clickedButton()

        if clicked == btn_save:
            return self.save_current_image()
        elif clicked == btn_discard:
            self.discard_adjustments()
            return True
        else:
            return False

    def _set_modified(self, modified: bool):
        self.is_modified = modified
        if hasattr(self, 'btn_save'):
            self.btn_save.setProperty("modified", "true" if modified else "false")
            self.btn_save.style().unpolish(self.btn_save)
            self.btn_save.style().polish(self.btn_save)
        self._update_window_title()

    def _update_window_title(self):
        if self.current_file_path:
            filename = os.path.basename(self.current_file_path)
            mod = "* " if self.is_modified else ""
            self.setWindowTitle(f"{mod}{filename} - {APP_TITLE}")
        else:
            self.setWindowTitle(APP_TITLE)

    def closeEvent(self, event):
        if self.confirm_save_if_modified():
            event.accept()
        else:
            event.ignore()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._setup_toolbar_overflow()

    def _cache_put(self, file_path: str, qimg: QImage, metadata: dict, pixmap: Optional[QPixmap] = None):
        existing = self._decode_cache.get(file_path)
        if pixmap is None and existing and isinstance(existing, dict) and existing.get("pixmap") is not None:
            pixmap = existing["pixmap"]

        if file_path in self._decode_cache:
            self._decode_cache_order.remove(file_path)
        self._decode_cache[file_path] = {"qimg": qimg, "pixmap": pixmap, "metadata": metadata}
        self._decode_cache_order.append(file_path)
        while len(self._decode_cache_order) > self._decode_cache_limit:
            oldest = self._decode_cache_order.pop(0)
            self._decode_cache.pop(oldest, None)

    def _join_in_flight_prefetch(self, file_path: str):
        """
        If navigation lands on a file whose background prefetch is already
        running, wait for that one decode to finish instead of starting a brand new,
        fully redundant decode.
        """
        worker = self._prefetch_workers.get(file_path)
        if worker is None:
            return None
        worker.wait()  # blocks only for whatever decode time remains
        if worker.result_qimg is not None and not worker.result_qimg.isNull():
            return worker.result_qimg, dict(worker.result_metadata)
        return None

    def _on_prefetch_done(self, file_path: str, qimg, metadata):
        if qimg is not None and not qimg.isNull():
            self._cache_put(file_path, qimg, metadata)

    def _on_prefetch_thread_finished(self, file_path: str, worker: "ImagePrefetchWorker"):
        self._prefetch_workers.pop(file_path, None)
        worker.deleteLater()

    def _prefetch_neighbors(self, direction: int = 1):
        """Kick off background decoding of neighboring images in the direction of travel (with cyclic wrap-around)."""
        if not self.folder_files or self.current_folder_index < 0 or len(self.folder_files) <= 1:
            return

        num_files = len(self.folder_files)
        candidates = []
        if direction >= 0:
            offsets = (1, 2, 3, -1, -2)
        else:
            offsets = (-1, -2, -3, 1, 2)

        for offset in offsets:
            idx = (self.current_folder_index + offset) % num_files
            if idx != self.current_folder_index and self.folder_files[idx] not in candidates:
                candidates.append(self.folder_files[idx])

        max_in_flight = 3
        for path in candidates:
            if len(self._prefetch_workers) >= max_in_flight:
                break
            if path in self._decode_cache or path in self._prefetch_workers:
                continue
            worker = ImagePrefetchWorker(path, self.current_passphrase)
            worker.prefetch_done.connect(self._on_prefetch_done)
            worker.finished.connect(lambda p=path, w=worker: self._on_prefetch_thread_finished(p, w))
            self._prefetch_workers[path] = worker
            worker.start(QThread.Priority.NormalPriority)

    def load_image(self, file_path: str, passphrase: Optional[str] = None, preserve_view: bool = True, direction: int = 1):
        if not os.path.exists(file_path):
            QMessageBox.critical(self, "File Not Found", f"Specified file does not exist:\n{file_path}")
            return

        t0 = time.time()

        saved_transform = QTransform(self.view.transform()) if preserve_view else None
        saved_zoom = self.view._zoom_factor if preserve_view else 1.0
        saved_center = self.view.mapToScene(self.view.viewport().rect().center()) if preserve_view else None

        file_path = os.path.abspath(file_path)
        ext = os.path.splitext(file_path)[1].lower()
        
        folder = os.path.dirname(file_path)
        folder_rescanned = folder != self._cached_folder_path
        if folder_rescanned:
            self.folder_files = [
                os.path.join(folder, f) for f in sorted(os.listdir(folder))
                if os.path.splitext(f)[1].lower() in ALL_SUPPORTED_EXTENSIONS
            ]
            self._cached_folder_path = folder
            # Pre-warm .sps decryption keys in background for instantaneous navigation
            sps_list = [f for f in self.folder_files if f.lower().endswith(".sps")]
            if sps_list:
                if self._sps_prewarm_worker and self._sps_prewarm_worker.isRunning():
                    self._sps_prewarm_worker.quit()
                self._sps_prewarm_worker = SpsKeyPrewarmWorker(sps_list, self.current_passphrase, self)
                self._sps_prewarm_worker.start(QThread.Priority.NormalPriority)
        should_refresh_dropdown = folder_rescanned or self._force_dropdown_refresh
        self._force_dropdown_refresh = False
        if file_path in self.folder_files:
            self.current_folder_index = self.folder_files.index(file_path)
        else:
            self.current_folder_index = -1

        self.current_file_path = file_path

        if ext == ".sps" or is_sps_file(file_path):
            self._load_sps_image(file_path, passphrase)
        else:
            self._load_standard_image(file_path)

        # Reset sidebar adjustments to neutral for each new image
        self.sidebar.blockSignals(True)
        self.sidebar.reset_all_adjustments()
        self.sidebar.blockSignals(False)
        self._sync_grayscale_ui()

        self.is_inverted = False
        self.current_rotation = 0
        self._applied_undo_stack.clear()
        self._applied_redo_stack.clear()
        self._update_sidebar_undo_redo()
        self._set_modified(False)

        self._render_scene_pixmap(fit=False if preserve_view else True)

        self.load_duration_sec = time.time() - t0

        if preserve_view and saved_transform and not saved_transform.isIdentity():
            self.view.setTransform(saved_transform)
            self.view._zoom_factor = saved_zoom
            if saved_center:
                self.view.centerOn(saved_center)

        if not self.sidebar.isHidden() and self.base_qimage and not self.base_qimage.isNull():
            self.sidebar.update_histograms(self.base_qimage)
        self._update_status_bar()

        # Update image dropdown and count label
        if hasattr(self, 'image_dropdown') and hasattr(self, 'image_count_label'):
            self.image_dropdown.blockSignals(True)
            if should_refresh_dropdown:
                self.image_dropdown.clear()
                if self.folder_files:
                    self.image_dropdown.addItems([os.path.basename(f) for f in self.folder_files])
            if self.folder_files:
                if 0 <= self.current_folder_index < len(self.folder_files):
                    self.image_dropdown.setCurrentIndex(self.current_folder_index)
                page_suffix = f" (Page {self.current_pdf_page + 1}/{self.pdf_page_count})" if getattr(self, "pdf_page_count", 1) > 1 else ""
                self.image_count_label.setText(f"{self.current_folder_index + 1} / {len(self.folder_files)}{page_suffix}")
            else:
                self.image_count_label.setText("0 / 0")
            self.image_dropdown.blockSignals(False)

        self._prefetch_neighbors(direction=direction)


    def _load_standard_image(self, file_path: str):
        cached = self._decode_cache.get(file_path)
        if cached is not None:
            self.is_encrypted_file = False
            self.base_qimage = cached["qimg"]
            if cached.get("pixmap") is not None and not cached["pixmap"].isNull():
                self.current_pixmap = cached["pixmap"]
            else:
                self.current_pixmap = QPixmap.fromImage(self.base_qimage)
                cached["pixmap"] = self.current_pixmap
            self.file_metadata = dict(cached["metadata"])
            self.pdf_page_count = self.file_metadata.get("page_count", 1)
            self.current_pdf_page = self.file_metadata.get("pdf_page", 0)
            return

        joined = self._join_in_flight_prefetch(file_path)
        if joined is not None:
            qimg, metadata = joined
            self.is_encrypted_file = False
            self.base_qimage = qimg
            self.current_pixmap = QPixmap.fromImage(qimg)
            self.file_metadata = metadata
            self.pdf_page_count = self.file_metadata.get("page_count", 1)
            self.current_pdf_page = self.file_metadata.get("pdf_page", 0)
            self._cache_put(file_path, qimg, dict(metadata), pixmap=self.current_pixmap)
            return

        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            from PyQt6.QtPdf import QPdfDocument
            from PyQt6.QtCore import QSize
            if hasattr(self, "_active_pdf_doc") and self._active_pdf_doc:
                self._active_pdf_doc.close()
                self._active_pdf_doc = None
            pdf_doc = QPdfDocument(self)
            pdf_doc.load(file_path)
            if pdf_doc.status() == QPdfDocument.Status.Ready and pdf_doc.pageCount() > 0:
                self.pdf_page_count = pdf_doc.pageCount()
                self.current_pdf_page = 0
                self._active_pdf_doc = pdf_doc
                pt_size = pdf_doc.pagePointSize(0)
                scale = 150.0 / 72.0
                render_size = QSize(max(1, int(pt_size.width() * scale)), max(1, int(pt_size.height() * scale)))
                qimg = pdf_doc.render(0, render_size)
                if not qimg.isNull():
                    pixmap = QPixmap.fromImage(qimg)
                    self.is_encrypted_file = False
                    self.current_pixmap = pixmap
                    self.base_qimage = qimg
                    self.file_metadata = {
                        "original_filename": os.path.basename(file_path),
                        "file_size": os.path.getsize(file_path),
                        "format": "PDF",
                        "page_count": self.pdf_page_count,
                        "pdf_page": 0
                    }
                    self._cache_put(file_path, qimg, dict(self.file_metadata), pixmap=self.current_pixmap)
                    return
            QMessageBox.warning(self, "Error Loading PDF", f"Failed to parse PDF document:\n{file_path}")
            return

        reader = QImageReader(file_path)
        reader.setAutoTransform(True)
        qimg = reader.read()
        if qimg.isNull():
            qimg = QImage(file_path)
        if qimg.isNull():
            # Try Pillow fallback (for JPEG 2000 .j2k/.jp2 or specialized image formats)
            try:
                from PIL import Image as PILImage
                with PILImage.open(file_path) as pil_img:
                    pil_img_rgba = pil_img.convert("RGBA")
                    data = pil_img_rgba.tobytes("raw", "RGBA")
                    qimg = QImage(data, pil_img_rgba.width, pil_img_rgba.height, QImage.Format.Format_RGBA8888).copy()
            except Exception:
                pass

        if qimg.isNull():
            QMessageBox.warning(self, "Error Loading Image", f"Failed to parse image file:\n{file_path}")
            return

        self.pdf_page_count = 1
        self.current_pdf_page = 0
        pixmap = QPixmap.fromImage(qimg)
        self.is_encrypted_file = False
        self.current_pixmap = pixmap
        self.base_qimage = qimg
        self.file_metadata = {
            "original_filename": os.path.basename(file_path),
            "file_size": os.path.getsize(file_path),
            "format": os.path.splitext(file_path)[1].upper().replace(".", "")
        }
        self._cache_put(file_path, self.base_qimage, dict(self.file_metadata), pixmap=self.current_pixmap)

    def _load_sps_image(self, file_path: str, passphrase: Optional[str] = None):
        pass_to_use = passphrase or self.current_passphrase

        cached = self._decode_cache.get(file_path)
        if cached is not None:
            self.is_encrypted_file = True
            self.base_qimage = cached["qimg"]
            if cached.get("pixmap") is not None and not cached["pixmap"].isNull():
                self.current_pixmap = cached["pixmap"]
            else:
                self.current_pixmap = QPixmap.fromImage(self.base_qimage)
                cached["pixmap"] = self.current_pixmap
            self.file_metadata = dict(cached["metadata"])
            self.file_metadata["file_size"] = os.path.getsize(file_path)
            self.pdf_page_count = self.file_metadata.get("page_count", 1)
            self.current_pdf_page = self.file_metadata.get("pdf_page", 0)
            return

        joined = self._join_in_flight_prefetch(file_path)
        if joined is not None:
            qimg, metadata = joined
            self.is_encrypted_file = True
            self.base_qimage = qimg
            self.current_pixmap = QPixmap.fromImage(qimg)
            self.file_metadata = metadata
            self.file_metadata["file_size"] = os.path.getsize(file_path)
            self.pdf_page_count = self.file_metadata.get("page_count", 1)
            self.current_pdf_page = self.file_metadata.get("pdf_page", 0)
            self._cache_put(file_path, qimg, dict(self.file_metadata), pixmap=self.current_pixmap)
            return

        try:
            image_bytes, metadata = decrypt_sps_file(file_path, passphrase=pass_to_use)
        except ValueError:
            custom_pass, ok = QInputDialog.getText(
                self, "Encrypted .sps File",
                f"Enter password to unlock:\n{os.path.basename(file_path)}",
                QLineEdit.EchoMode.Password
            )
            if not ok or not custom_pass:
                self.status_bar.showMessage("Decryption cancelled.")
                return
            
            try:
                image_bytes, metadata = decrypt_sps_file(file_path, passphrase=custom_pass)
                self.current_passphrase = custom_pass
            except Exception as ex:
                QMessageBox.critical(self, "Decryption Error", f"Failed to decrypt .sps file:\n{str(ex)}")
                return
        except Exception as ex:
            QMessageBox.critical(self, "Error", f"Failed to process file:\n{str(ex)}")
            return

        if image_bytes.startswith(b"%PDF"):
            from PyQt6.QtPdf import QPdfDocument
            from PyQt6.QtCore import QBuffer, QIODevice, QSize
            if hasattr(self, "_active_pdf_doc") and self._active_pdf_doc:
                self._active_pdf_doc.close()
                self._active_pdf_doc = None
            buf = QBuffer(self)
            buf.setData(image_bytes)
            buf.open(QIODevice.OpenModeFlag.ReadOnly)
            pdf_doc = QPdfDocument(self)
            pdf_doc.load(buf)
            if pdf_doc.status() == QPdfDocument.Status.Ready and pdf_doc.pageCount() > 0:
                self.pdf_page_count = pdf_doc.pageCount()
                self.current_pdf_page = 0
                self._active_pdf_doc = pdf_doc
                self._active_pdf_buf = buf
                pt_size = pdf_doc.pagePointSize(0)
                scale = 150.0 / 72.0
                render_size = QSize(max(1, int(pt_size.width() * scale)), max(1, int(pt_size.height() * scale)))
                qimg = pdf_doc.render(0, render_size)
                pixmap = QPixmap.fromImage(qimg)
                self.is_encrypted_file = True
                self.current_pixmap = pixmap
                self.base_qimage = qimg
                metadata["page_count"] = self.pdf_page_count
                metadata["pdf_page"] = 0
                metadata["format"] = "PDF"
                metadata["file_size"] = os.path.getsize(file_path)
                self.file_metadata = metadata
                self._cache_put(file_path, qimg, dict(self.file_metadata), pixmap=pixmap)
                return

        qimg = QImage()
        loaded = qimg.loadFromData(image_bytes)
        if not loaded or qimg.isNull():
            # Try Pillow fallback (for JPEG 2000 .j2k/.jp2 or other formats
            # Qt's built-in loader doesn't support) - same approach used for
            # standard files in _load_standard_image().
            try:
                from io import BytesIO
                from PIL import Image as PILImage
                with PILImage.open(BytesIO(image_bytes)) as pil_img:
                    pil_img_rgba = pil_img.convert("RGBA")
                    data = pil_img_rgba.tobytes("raw", "RGBA")
                    qimg = QImage(data, pil_img_rgba.width, pil_img_rgba.height, QImage.Format.Format_RGBA8888).copy()
                    loaded = not qimg.isNull()
            except Exception:
                loaded = False

        if not loaded or qimg.isNull():
            QMessageBox.critical(self, "Image Error", "Decrypted binary content could not be parsed as an image.")
            return

        self.pdf_page_count = 1
        self.current_pdf_page = 0
        pixmap = QPixmap.fromImage(qimg)
        self.is_encrypted_file = True
        self.current_pixmap = pixmap
        self.base_qimage = qimg  # RAM Base Frame Cache
        self.file_metadata = metadata
        self.file_metadata["file_size"] = os.path.getsize(file_path)
        self._cache_put(file_path, qimg, dict(self.file_metadata), pixmap=pixmap)

    def _is_adjustment_active(self) -> bool:
        if self.current_rotation != 0 or self.is_inverted:
            return True
        p = self.sidebar.get_adjustment_params()
        levels = p.get("levels", {})
        lum = levels.get("Luminance", {})
        red = levels.get("Red", {})
        grn = levels.get("Green", {})
        blu = levels.get("Blue", {})
        has_levels = (
            lum.get("shadows", 0) > 0 or lum.get("highlights", 255) < 255 or abs(lum.get("midtones", 1.0) - 1.0) > 0.01 or
            red.get("shadows", 0) > 0 or red.get("highlights", 255) < 255 or abs(red.get("midtones", 1.0) - 1.0) > 0.01 or
            grn.get("shadows", 0) > 0 or grn.get("highlights", 255) < 255 or abs(grn.get("midtones", 1.0) - 1.0) > 0.01 or
            blu.get("shadows", 0) > 0 or blu.get("highlights", 255) < 255 or abs(blu.get("midtones", 1.0) - 1.0) > 0.01
        )
        has_curves = any(lut is not None for lut in p.get("curve_luts", {}).values()) or p.get("curve_lut") is not None
        return bool(
            p.get("auto_exposure", False) or
            p.get("brightness", 0) != 0 or
            p.get("contrast", 0) != 0 or
            abs(p.get("gamma", 1.0) - 1.0) > 0.01 or
            p.get("grayscale", False) or
            p.get("exposure_warning", False) or
            has_levels or
            has_curves
        )

    def _on_adjustments_changed(self):
        """Slot called during real-time slider drags."""
        self._sync_grayscale_ui()
        self._set_modified(self._is_adjustment_active())
        self._render_scene_pixmap(fit=False)
        self._update_status_bar()

    def _apply_full_adjustments_fast(self, base_qimg: QImage, p: dict) -> QImage:
        """
        Ultra-Fast C-Level Vectorized NumPy Multi-Channel LUT Engine (<1ms latency).
        Combines Invert, Brightness, Contrast, Gamma, Per-Channel RGB Levels, Per-Channel Curves.
        """
        if not base_qimg or base_qimg.isNull():
            return base_qimg
        auto_exp = p.get("auto_exposure", False)
        auto_exp_strength = p.get("auto_exposure_strength", 0)  # 0 to 100
        bright = p.get("brightness", 0)        # -100 to 100
        contrast = p.get("contrast", 0)        # -100 to 100
        gamma = p.get("gamma", 1.0)             # 0.1 to 3.0
        grayscale = p.get("grayscale", False)
        exposure_warning = p.get("exposure_warning", False)

        levels = p.get("levels", {})
        lum_lev = levels.get("Luminance", {"shadows": p.get("black_point", 0), "midtones": p.get("midtone_val", 1.0), "highlights": p.get("white_point", 255)})
        red_lev = levels.get("Red", {"shadows": 0, "midtones": 1.0, "highlights": 255})
        grn_lev = levels.get("Green", {"shadows": 0, "midtones": 1.0, "highlights": 255})
        blu_lev = levels.get("Blue", {"shadows": 0, "midtones": 1.0, "highlights": 255})

        curve_luts = p.get("curve_luts", {})
        rgb_curve = curve_luts.get("RGB", p.get("curve_lut", None))
        red_curve = curve_luts.get("Red", None)
        grn_curve = curve_luts.get("Green", None)
        blu_curve = curve_luts.get("Blue", None)

        # Check if per-channel levels or curves are non-neutral
        has_channel_levels = (
            red_lev["shadows"] > 0 or red_lev["highlights"] < 255 or abs(red_lev["midtones"] - 1.0) > 0.01 or
            grn_lev["shadows"] > 0 or grn_lev["highlights"] < 255 or abs(grn_lev["midtones"] - 1.0) > 0.01 or
            blu_lev["shadows"] > 0 or blu_lev["highlights"] < 255 or abs(blu_lev["midtones"] - 1.0) > 0.01
        )
        has_curves = (rgb_curve is not None or red_curve is not None or grn_curve is not None or blu_curve is not None)

        is_neutral = (
            not self.is_inverted and not auto_exp and not grayscale and not exposure_warning
            and not has_curves and not has_channel_levels
            and bright == 0 and contrast == 0
            and abs(gamma - 1.0) <= 0.01
            and lum_lev["shadows"] <= 0 and lum_lev["highlights"] >= 255
            and abs(lum_lev["midtones"] - 1.0) <= 0.01
        )
        if is_neutral:
            return base_qimg

        out = base_qimg.convertToFormat(QImage.Format.Format_ARGB32)
        ptr = out.bits()
        ptr.setsize(out.sizeInBytes())
        arr = np.frombuffer(ptr, dtype=np.uint8)

        # Auto Exposure Calculation
        if auto_exp and auto_exp_strength != 0:
            factor = auto_exp_strength / 100.0
            avg_intensity = float(np.mean(arr[0::4]))
            if avg_intensity > 0:
                bright += int((128.0 - avg_intensity) * factor)
            contrast += int(30 * factor)

        # 1. Base Master LUT (Invert, Contrast, Brightness, Master Gamma, Master Luminance Levels)
        base_lut = np.arange(256, dtype=np.float32)

        if self.is_inverted:
            base_lut = 255.0 - base_lut

        # Master Luminance Levels: Black point & White point scaling
        black_pt = lum_lev["shadows"]
        white_pt = lum_lev["highlights"]
        midtone_val = lum_lev["midtones"]

        if white_pt > black_pt and (black_pt > 0 or white_pt < 255):
            base_lut = np.clip((base_lut - black_pt) * (255.0 / max(1.0, float(white_pt - black_pt))), 0.0, 255.0)

        # Master Luminance Levels: Midtone Gamma adjustment
        if abs(midtone_val - 1.0) > 0.01 and midtone_val > 0.05:
            lut_norm = np.clip(base_lut / 255.0, 0.0, 1.0)
            base_lut = np.clip((lut_norm ** (1.0 / midtone_val)) * 255.0, 0.0, 255.0)

        if contrast != 0:
            c_factor = (259.0 * (contrast + 255.0)) / (255.0 * (259.0 - contrast))
            base_lut = np.clip(c_factor * (base_lut - 128.0) + 128.0, 0.0, 255.0)

        if bright != 0:
            base_lut = np.clip(base_lut + (bright * 1.5), 0.0, 255.0)

        if gamma > 0 and abs(gamma - 1.0) > 0.01:
            lut_norm = np.clip(base_lut / 255.0, 0.0, 1.0)
            base_lut = np.clip((lut_norm ** (1.0 / gamma)) * 255.0, 0.0, 255.0)

        # Master RGB Curve
        if rgb_curve is not None:
            base_lut = rgb_curve[np.clip(base_lut, 0, 255).astype(np.uint8)].astype(np.float32)

        # 2. Branch Per-Channel LUTs for Red, Green, Blue
        def _apply_channel_levels_and_curve(in_lut: np.ndarray, lev: dict, ch_curve: Optional[np.ndarray]) -> np.ndarray:
            ch_lut = in_lut.copy()
            s = lev.get("shadows", 0)
            h = lev.get("highlights", 255)
            m = lev.get("midtones", 1.0)
            if h > s and (s > 0 or h < 255):
                ch_lut = np.clip((ch_lut - s) * (255.0 / max(1.0, float(h - s))), 0.0, 255.0)
            if abs(m - 1.0) > 0.01 and m > 0.05:
                norm = np.clip(ch_lut / 255.0, 0.0, 1.0)
                ch_lut = np.clip((norm ** (1.0 / m)) * 255.0, 0.0, 255.0)
            ch_uint8 = np.clip(ch_lut, 0, 255).astype(np.uint8)
            if ch_curve is not None:
                ch_uint8 = ch_curve[ch_uint8]
            return ch_uint8

        lut_r = _apply_channel_levels_and_curve(base_lut, red_lev, red_curve)
        lut_g = _apply_channel_levels_and_curve(base_lut, grn_lev, grn_curve)
        lut_b = _apply_channel_levels_and_curve(base_lut, blu_lev, blu_curve)

        # 3. Apply vectorized LUTs to C byte buffer in 1 millisecond
        arr[0::4] = lut_b[arr[0::4]]  # Blue
        arr[1::4] = lut_g[arr[1::4]]  # Green
        arr[2::4] = lut_r[arr[2::4]]  # Red

        # 4. Grayscale & Binary Black & White
        if grayscale:
            b = arr[0::4].astype(np.float32)
            g = arr[1::4].astype(np.float32)
            r = arr[2::4].astype(np.float32)
            luma = 0.299 * r + 0.587 * g + 0.114 * b

            gray_mode = p.get("grayscale_mode", "full_range")
            if gray_mode == "binary":
                # Pure Black & White (Binary / 2-Tone)
                thresh = float(p.get("bw_threshold", 128))
                luma_out = np.where(luma >= thresh, np.uint8(255), np.uint8(0))
            else:
                # Full Range Grayscale (Pure Black to Pure White with rich photographic tonal depth)
                sub_luma = luma[::4] if len(luma) > 40000 else luma
                counts, _ = np.histogram(sub_luma, bins=256, range=(0, 256))
                total_pixels = len(sub_luma)
                cum = np.cumsum(counts)

                peak_idx = int(np.argmax(counts))
                near_peak = counts[max(0, peak_idx - 15):min(256, peak_idx + 15)].sum()
                is_doc_light = (peak_idx > 140 and near_peak / max(1, total_pixels) > 0.30)
                is_doc_dark = (peak_idx < 115 and near_peak / max(1, total_pixels) > 0.30)

                if is_doc_light:
                    wp = float(peak_idx)
                    prob = counts.astype(np.float64) / max(1, total_pixels)
                    omega = np.cumsum(prob)
                    mu = np.cumsum(prob * np.arange(256))
                    denom = omega * (1.0 - omega)
                    denom[denom < 1e-9] = 1e-9
                    sigma_b = (mu[-1] * omega - mu)**2 / denom
                    otsu_th = int(np.argmax(sigma_b))

                    sub_counts = counts[:otsu_th]
                    sub_total = sub_counts.sum()
                    if sub_total > 0:
                        sub_prob = sub_counts.astype(np.float64) / sub_total
                        sub_omega = np.cumsum(sub_prob)
                        sub_mu = np.cumsum(sub_prob * np.arange(otsu_th))
                        sub_denom = sub_omega * (1.0 - sub_omega)
                        sub_denom[sub_denom < 1e-9] = 1e-9
                        sub_sigma = (sub_mu[-1] * sub_omega - sub_mu)**2 / sub_denom
                        bp = float(np.argmax(sub_sigma))
                    else:
                        bp = float(np.searchsorted(cum, 0.02 * total_pixels))

                    if wp <= bp + 20.0:
                        bp = float(np.searchsorted(cum, 0.02 * total_pixels))
                        wp = float(np.searchsorted(cum, 0.98 * total_pixels))
                elif is_doc_dark:
                    bp = float(peak_idx)
                    prob = counts.astype(np.float64) / max(1, total_pixels)
                    omega = np.cumsum(prob)
                    mu = np.cumsum(prob * np.arange(256))
                    denom = omega * (1.0 - omega)
                    denom[denom < 1e-9] = 1e-9
                    sigma_b = (mu[-1] * omega - mu)**2 / denom
                    otsu_th = int(np.argmax(sigma_b))

                    sub_counts = counts[otsu_th:]
                    sub_total = sub_counts.sum()
                    if sub_total > 0:
                        sub_prob = sub_counts.astype(np.float64) / sub_total
                        sub_omega = np.cumsum(sub_prob)
                        sub_mu = np.cumsum(sub_prob * np.arange(256 - otsu_th))
                        sub_denom = sub_omega * (1.0 - sub_omega)
                        sub_denom[sub_denom < 1e-9] = 1e-9
                        sub_sigma = (sub_mu[-1] * sub_omega - sub_mu)**2 / sub_denom
                        wp = float(otsu_th + np.argmax(sub_sigma))
                    else:
                        wp = float(np.searchsorted(cum, 0.98 * total_pixels))

                    if wp <= bp + 20.0:
                        bp = float(np.searchsorted(cum, 0.02 * total_pixels))
                        wp = float(np.searchsorted(cum, 0.98 * total_pixels))
                else:
                    bp = float(np.searchsorted(cum, 0.015 * total_pixels))
                    wp = float(np.searchsorted(cum, 0.985 * total_pixels))

                scale = 255.0 / max(wp - bp, 15.0)
                stretched = np.clip((luma - bp) * scale, 0.0, 255.0)

                # Photographic S-curve contrast boost (+20) for rich velvety blacks and bright highlights
                c = 20.0
                c_factor = (259.0 * (c + 255.0)) / (255.0 * (259.0 - c))
                luma_out = np.clip(128.0 + c_factor * (stretched - 128.0), 0.0, 255.0).astype(np.uint8)

            arr[0::4] = luma_out
            arr[1::4] = luma_out
            arr[2::4] = luma_out

        # 5. Exposure Warning (ACDSee: Highlights clipped blown-out whites in bright blue, crushed blacks in bright red)
        if exposure_warning:
            b_ch = arr[0::4].astype(np.float32)
            g_ch = arr[1::4].astype(np.float32)
            r_ch = arr[2::4].astype(np.float32)
            luma_vals = 0.299 * r_ch + 0.587 * g_ch + 0.114 * b_ch
            blown = luma_vals >= 254
            crushed = luma_vals <= 1
            if np.any(blown):
                arr[0::4][blown] = 255  # Blue
                arr[1::4][blown] = 0
                arr[2::4][blown] = 0
            if np.any(crushed):
                arr[0::4][crushed] = 0
                arr[1::4][crushed] = 0
                arr[2::4][crushed] = 255  # Red

        # Return true 8-bit single-channel grayscale if grayscale active and not in color exposure warning mode
        if (grayscale or (base_qimg and base_qimg.format() in (
            QImage.Format.Format_Grayscale8,
            QImage.Format.Format_Grayscale16,
            QImage.Format.Format_Mono,
            QImage.Format.Format_MonoLSB
        ))) and not exposure_warning:
            return out.convertToFormat(QImage.Format.Format_Grayscale8)

        return out

    def _render_scene_pixmap(self, fit: bool = False):
        if not self.base_qimage or self.base_qimage.isNull():
            return

        t0 = time.time()
        # Ultra-fast path: Skip numpy processing and QPixmap.fromImage conversion when neutral
        if (not self._is_adjustment_active() and 
            self.current_rotation == 0 and 
            not self.is_inverted and 
            self.current_pixmap is not None and 
            not self.current_pixmap.isNull()):
            pix = self.current_pixmap
        else:
            adj_params = self.sidebar.get_adjustment_params()
            qimg = self._apply_full_adjustments_fast(self.base_qimage, adj_params)

            pix = QPixmap.fromImage(qimg)

            if self.current_rotation != 0:
                transform = QTransform().rotate(self.current_rotation)
                pix = pix.transformed(transform, Qt.TransformationMode.SmoothTransformation)

            self.current_pixmap = pix

        self.pixmap_item.setPixmap(pix)
        self.scene.setSceneRect(QRectF(pix.rect()))
        
        # Log ultra-fast render timing (<0.002s)
        self.load_duration_sec = time.time() - t0

        if fit:
            self.fit_to_view()

    def _update_status_bar(self):
        if not self.current_file_path or not self.current_pixmap:
            self.setWindowTitle(APP_TITLE)
            return

        fname = os.path.basename(self.current_file_path)
        self._update_window_title()
        idx_str = f"{self.current_folder_index + 1}/{len(self.folder_files)}" if self.folder_files else "1/1"
        
        fsize = self.file_metadata.get("file_size", os.path.getsize(self.current_file_path) if os.path.exists(self.current_file_path) else 0)
        fsize_mb = fsize / (1024.0 * 1024.0)

        w, h = self.current_pixmap.width(), self.current_pixmap.height()
        fmt = self.file_metadata.get("format", os.path.splitext(fname)[1].replace(".", "").lower())
        
        mod_time_str = QDateTime.fromSecsSinceEpoch(int(os.path.getmtime(self.current_file_path))).toString("dd-MM-yyyy hh:mm:ss") if os.path.exists(self.current_file_path) else "N/A"
        zoom_pct = int(self.view._zoom_factor * 100)

        p = self.sidebar.get_adjustment_params()
        adj_flag = " | 🎛 Adjusted" if (self.is_modified or any([
            p["auto_exposure"], p["brightness"], p["contrast"],
            abs(p["gamma"] - 1.0) > 0.01, p["black_point"] > 0,
            p["white_point"] < 255, p["shadows"], p["midtones"], p["highlights"]
        ])) else ""

        mod_flag = " | ✏ Modified" if self.is_modified else ""
        enc_flag = " | 🔒 SPS Encrypted" if self.is_encrypted_file else ""

        # Bit depth calculation matching ACDSee: 8b for grayscale, 32b for alpha, 24b for RGB
        is_gray = (
            p.get("grayscale", False) or
            (self.base_qimage is not None and self.base_qimage.format() in (
                QImage.Format.Format_Grayscale8,
                QImage.Format.Format_Grayscale16,
                QImage.Format.Format_Mono,
                QImage.Format.Format_MonoLSB
            ))
        )
        if is_gray:
            bpp_str = "8b"
        elif self.base_qimage is not None and self.base_qimage.hasAlphaChannel():
            bpp_str = "32b"
        else:
            bpp_str = "24b"

        # File size display matching ACDSee ('501.7 KB' or '1.2 MB')
        if fsize < 1024 * 1024:
            fsize_str = f"{fsize / 1024:.1f} KB" if fsize > 0 else "0 KB"
        else:
            fsize_str = f"{fsize / (1024 * 1024):.1f} MB"

        page_str = f" [Page {self.current_pdf_page + 1}/{self.pdf_page_count}]" if getattr(self, "pdf_page_count", 1) > 1 else ""

        status_text = (
            f"{idx_str} | {fname}{page_str} | {fsize_str} | {w}x{h}x{bpp_str} {fmt.lower()} | "
            f"Modified Date: {mod_time_str} | {zoom_pct}% | Render: {self.load_duration_sec:.3f} s{adj_flag}{mod_flag}{enc_flag}"
        )
        self.status_bar.showMessage(status_text)

    def _on_zoom_changed(self, zoom_val: float):
        self._update_status_bar()

    def zoom_in(self):
        self.view.scale(1.25, 1.25)
        self.view._zoom_factor *= 1.25
        self._on_zoom_changed(self.view._zoom_factor)

    def zoom_out(self):
        self.view.scale(0.8, 0.8)
        self.view._zoom_factor *= 0.8
        self._on_zoom_changed(self.view._zoom_factor)

    def zoom_100(self):
        self.view.reset_zoom()

    def fit_to_view(self):
        if self.pixmap_item.pixmap().isNull():
            return
        self.view.resetTransform()
        self.view.fitInView(self.pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
        rect = self.view.transform().mapRect(QRectF(0, 0, 1, 1))
        self.view._zoom_factor = rect.width()
        self._on_zoom_changed(self.view._zoom_factor)

    def rotate_image(self, degrees: int):
        if not self.current_pixmap:
            return
        self.current_rotation = (self.current_rotation + degrees) % 360
        self._set_modified(True)
        self._render_scene_pixmap(fit=False)
        self._update_status_bar()

    def toggle_invert_colors(self):
        if not self.current_pixmap:
            return
        self.is_inverted = not self.is_inverted
        self._set_modified(True)
        self._render_scene_pixmap(fit=False)
        self._update_status_bar()

    def toggle_grayscale(self):
        if not self.current_pixmap:
            return
        if self.sidebar.chk_grayscale.isChecked() and self.sidebar.radio_gray_full.isChecked():
            self.sidebar.chk_grayscale.setChecked(False)
        else:
            self.sidebar.radio_gray_full.setChecked(True)
            self.sidebar.chk_grayscale.setChecked(True)
        self._sync_grayscale_ui()
        self._set_modified(self._is_adjustment_active())
        self.sidebar._commit_change()

    def toggle_binary_bw(self):
        if not self.current_pixmap:
            return
        if self.sidebar.chk_grayscale.isChecked() and self.sidebar.radio_bw_binary.isChecked():
            self.sidebar.chk_grayscale.setChecked(False)
        else:
            self.sidebar.radio_bw_binary.setChecked(True)
            self.sidebar.chk_grayscale.setChecked(True)
        self._sync_grayscale_ui()
        self._set_modified(self._is_adjustment_active())
        self.sidebar._commit_change()

    def _sync_grayscale_ui(self, *args):
        is_active = self.sidebar.chk_grayscale.isChecked() if hasattr(self.sidebar, "chk_grayscale") else False
        is_binary = self.sidebar.radio_bw_binary.isChecked() if hasattr(self.sidebar, "radio_bw_binary") else False
        is_full = is_active and not is_binary
        is_bin_active = is_active and is_binary

        if hasattr(self, "btn_grayscale") and self.btn_grayscale.isChecked() != is_full:
            self.btn_grayscale.blockSignals(True)
            self.btn_grayscale.setChecked(is_full)
            self.btn_grayscale.blockSignals(False)
        if hasattr(self, "act_grayscale") and self.act_grayscale.isChecked() != is_full:
            self.act_grayscale.blockSignals(True)
            self.act_grayscale.setChecked(is_full)
            self.act_grayscale.blockSignals(False)

        if hasattr(self, "btn_binary_bw") and self.btn_binary_bw.isChecked() != is_bin_active:
            self.btn_binary_bw.blockSignals(True)
            self.btn_binary_bw.setChecked(is_bin_active)
            self.btn_binary_bw.blockSignals(False)
        if hasattr(self, "act_binary_bw") and self.act_binary_bw.isChecked() != is_bin_active:
            self.act_binary_bw.blockSignals(True)
            self.act_binary_bw.setChecked(is_bin_active)
            self.act_binary_bw.blockSignals(False)

    def _goto_pdf_page(self, page_index: int):
        """Render and display a specific page of an active PDF document."""
        if not hasattr(self, "_active_pdf_doc") or not self._active_pdf_doc:
            # If _active_pdf_doc is missing or closed (e.g. after cache hit), reload it
            if self.current_file_path and os.path.exists(self.current_file_path):
                ext = os.path.splitext(self.current_file_path)[1].lower()
                if ext == ".sps" or is_sps_file(self.current_file_path):
                    self._load_sps_image(self.current_file_path, self.current_passphrase)
                elif ext == ".pdf":
                    from PyQt6.QtPdf import QPdfDocument
                    self._active_pdf_doc = QPdfDocument(self)
                    self._active_pdf_doc.load(self.current_file_path)
                    self.pdf_page_count = self._active_pdf_doc.pageCount()

        if not hasattr(self, "_active_pdf_doc") or not self._active_pdf_doc:
            return
        if page_index < 0 or page_index >= self._active_pdf_doc.pageCount():
            return
        from PyQt6.QtCore import QSize
        self.current_pdf_page = page_index
        pt_size = self._active_pdf_doc.pagePointSize(page_index)
        scale = 150.0 / 72.0
        render_size = QSize(max(1, int(pt_size.width() * scale)), max(1, int(pt_size.height() * scale)))
        qimg = self._active_pdf_doc.render(page_index, render_size)
        if not qimg.isNull():
            self.base_qimage = qimg
            self.current_pixmap = QPixmap.fromImage(qimg)
            self.file_metadata["pdf_page"] = page_index
            self._render_scene_pixmap(fit=False)
            if not self.sidebar.isHidden():
                self.sidebar.update_histograms(self.base_qimage)
            self._update_status_bar()
            if hasattr(self, 'image_count_label') and self.folder_files:
                page_suffix = f" (Page {self.current_pdf_page + 1}/{self.pdf_page_count})" if getattr(self, "pdf_page_count", 1) > 1 else ""
                self.image_count_label.setText(f"{self.current_folder_index + 1} / {len(self.folder_files)}{page_suffix}")

    def show_prev_image(self):
        if not self.confirm_save_if_modified():
            return
        # If currently in a multi-page PDF and not on the first page:
        if getattr(self, "pdf_page_count", 1) > 1 and getattr(self, "current_pdf_page", 0) > 0:
            self._goto_pdf_page(self.current_pdf_page - 1)
            return
        if not self.folder_files or len(self.folder_files) <= 1:
            return
        if self.current_folder_index <= 0:
            self.current_folder_index = len(self.folder_files) - 1
        else:
            self.current_folder_index -= 1
        self.load_image(self.folder_files[self.current_folder_index], preserve_view=True, direction=-1)

    def show_next_image(self):
        if not self.confirm_save_if_modified():
            return
        # If currently in a multi-page PDF and not on the last page:
        if getattr(self, "pdf_page_count", 1) > 1 and getattr(self, "current_pdf_page", 0) < self.pdf_page_count - 1:
            self._goto_pdf_page(self.current_pdf_page + 1)
            return
        if not self.folder_files or len(self.folder_files) <= 1:
            return
        if self.current_folder_index >= len(self.folder_files) - 1:
            self.current_folder_index = 0
        else:
            self.current_folder_index += 1
        self.load_image(self.folder_files[self.current_folder_index], preserve_view=True, direction=1)

    def copy_path_to_clipboard(self):
        if self.current_file_path:
            QApplication.clipboard().setText(self.current_file_path)
            self.status_bar.showMessage("File path copied to clipboard.", 3000)

    def show_file_properties(self):
        if not self.current_file_path:
            QMessageBox.information(self, "Properties", "No image currently loaded.")
            return

        w = self.current_pixmap.width() if self.current_pixmap else 0
        h = self.current_pixmap.height() if self.current_pixmap else 0
        fsize = self.file_metadata.get("file_size", os.path.getsize(self.current_file_path)) / 1024.0

        info = (
            f"<b>Filename:</b> {os.path.basename(self.current_file_path)}<br>"
            f"<b>Path:</b> {self.current_file_path}<br>"
            f"<b>Dimensions:</b> {w} x {h} pixels<br>"
            f"<b>File Size:</b> {fsize:.1f} KB<br>"
            f"<b>Format:</b> {self.file_metadata.get('format', 'SPS Encrypted')}<br>"
            f"<b>Security:</b> {'🔒 AES-256-GCM Encrypted (.sps)' if self.is_encrypted_file else 'Standard Unencrypted'}"
        )
        QMessageBox.information(self, "Document File Properties", info)

    def show_about_dialog(self):
        QMessageBox.about(
            self,
            "About SPS Image Viewer",
            f"<h3>{APP_TITLE}</h3>"
            f"<p>Version: {APP_VERSION}</p>"
            "<p>Classic enterprise document image viewing software featuring sub-millisecond "
            "vectorized image processing, right-side Image Adjustment Sidebar (Ctrl+L) "
            "Brightness, Contrast, Gamma, Levels, Curves, Multi-Theme Engine, and in-memory <b>.sps</b> decryption.</p>"
        )


def main():
    setup_high_dpi()
    app = QApplication(sys.argv)
    app.setWindowIcon(get_app_icon())
    app.setStyleSheet(get_light_stylesheet())

    start_file = sys.argv[1] if len(sys.argv) > 1 else None

    window = SPSImageViewerWindow(start_file=start_file)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()