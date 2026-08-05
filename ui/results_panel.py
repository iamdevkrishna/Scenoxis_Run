"""
ui/results_panel.py
Custom QWidget that renders the full results area:
  - App results: icon + name + subtitle
  - Calc result: large equation display
  - Chat/Page: QTextBrowser with rendered markdown HTML
  - YouTube: format list + download progress bar
  - Thinking: animated shimmer bar
  - Border-scan animation for page analysis
"""
import math
import os
from typing import Optional

from PySide6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve,
    QPoint, QSize, Property, QObject, Signal, QRect,
)
from PySide6.QtGui import (
    QColor, QFont, QFontDatabase, QIcon, QPixmap,
    QPainter, QPen, QLinearGradient, QPainterPath, QBrush,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QTextBrowser,
    QProgressBar, QFrame, QSizePolicy, QScrollArea,
    QStackedWidget, QAbstractItemView, QToolButton, QLineEdit, QSpacerItem,
    QPushButton
)

from ui.result_item import ResultItem, ResultKind


# ─────────────────────────────────────────────────────────────────────────────
# Icon helpers
# ─────────────────────────────────────────────────────────────────────────────

_icon_cache: dict[str, Optional[QPixmap]] = {}


def _extract_win32_icon(exe_path: str, size: int = 32) -> Optional[QPixmap]:
    cache_key = f"{exe_path}:{size}"
    if cache_key in _icon_cache:
        return _icon_cache[cache_key]

    pix: Optional[QPixmap] = None
    try:
        import ctypes
        import ctypes.wintypes as wt

        SHGFI_ICON      = 0x0100
        SHGFI_LARGEICON = 0x0000

        class _SHFI(ctypes.Structure):
            _fields_ = [
                ("hIcon",         wt.HANDLE),
                ("iIcon",         ctypes.c_int),
                ("dwAttributes",  wt.DWORD),
                ("szDisplayName", ctypes.c_wchar * 260),
                ("szTypeName",    ctypes.c_wchar * 80),
            ]

        shell32 = ctypes.windll.shell32
        user32  = ctypes.windll.user32
        gdi32   = ctypes.windll.gdi32

        info = _SHFI()
        ret = shell32.SHGetFileInfoW(
            exe_path, 0, ctypes.byref(info), ctypes.sizeof(info),
            SHGFI_ICON | SHGFI_LARGEICON
        )
        if not ret or not info.hIcon:
            raise RuntimeError("SHGetFileInfoW returned no icon")

        class _BMIH(ctypes.Structure):
            _fields_ = [
                ("biSize",          ctypes.c_uint32),
                ("biWidth",         ctypes.c_int32),
                ("biHeight",        ctypes.c_int32),
                ("biPlanes",        ctypes.c_uint16),
                ("biBitCount",      ctypes.c_uint16),
                ("biCompression",   ctypes.c_uint32),
                ("biSizeImage",     ctypes.c_uint32),
                ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32),
                ("biClrUsed",       ctypes.c_uint32),
                ("biClrImportant",  ctypes.c_uint32),
            ]

        bmi = _BMIH()
        bmi.biSize        = ctypes.sizeof(_BMIH)
        bmi.biWidth       = size
        bmi.biHeight      = -size
        bmi.biPlanes      = 1
        bmi.biBitCount    = 32
        bmi.biCompression = 0

        screen_dc = user32.GetDC(None)
        mem_dc    = gdi32.CreateCompatibleDC(screen_dc)
        pbits     = ctypes.c_void_p()
        hbm = gdi32.CreateDIBSection(
            mem_dc, ctypes.byref(bmi), 0, ctypes.byref(pbits), None, 0
        )
        old = gdi32.SelectObject(mem_dc, hbm)
        gdi32.PatBlt(mem_dc, 0, 0, size, size, 0x00000042)
        user32.DrawIconEx(mem_dc, 0, 0, info.hIcon, size, size, 0, None, 0x3)

        n   = size * size * 4
        buf = (ctypes.c_char * n)()
        gdi32.GetBitmapBits(hbm, n, buf)

        gdi32.SelectObject(mem_dc, old)
        gdi32.DeleteObject(hbm)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(None, screen_dc)
        user32.DestroyIcon(info.hIcon)

        from PySide6.QtGui import QImage
        img = QImage(buf, size, size, size * 4, QImage.Format.Format_ARGB32)
        result = QPixmap.fromImage(img.copy())
        pix = result if not result.isNull() else None

    except Exception:
        pass

    _icon_cache[cache_key] = pix
    return pix


def _load_icon(path: Optional[str], size: int = 32) -> Optional[QPixmap]:
    if not path:
        return None
    if os.path.exists(path):
        pix = _extract_win32_icon(path, size)
        if pix:
            return pix
    try:
        icon = QIcon(path)
        if not icon.isNull():
            p = icon.pixmap(QSize(size, size))
            return p if not p.isNull() else None
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Shimmer thinking animation — modern skeleton-loader style
# ─────────────────────────────────────────────────────────────────────────────

class ShimmerWidget(QWidget):
    """
    A sleek horizontal shimmer bar that sweeps left→right repeatedly.
    Much more modern than the old braille spinner text.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self):
        self._phase = 0.0
        self._timer.start(16)  # ~60fps

    def stop(self):
        self._timer.stop()

    def _tick(self):
        self._phase = (self._phase + 0.015) % 1.0
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        margin_x = 16
        bar_y = h // 2 - 2
        bar_h = 3
        bar_w = w - margin_x * 2
        bar_r = 1.5

        # Background track
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 8))
        p.drawRoundedRect(margin_x, bar_y, bar_w, bar_h, bar_r, bar_r)

        # Shimmer highlight — a glowing blob that sweeps across
        blob_w = bar_w * 0.35
        blob_x = margin_x + self._phase * (bar_w + blob_w) - blob_w

        grad = QLinearGradient(blob_x, 0, blob_x + blob_w, 0)
        grad.setColorAt(0.0, QColor(255, 255, 255, 0))
        grad.setColorAt(0.3, QColor(255, 255, 255, 45))
        grad.setColorAt(0.5, QColor(255, 255, 255, 70))
        grad.setColorAt(0.7, QColor(255, 255, 255, 45))
        grad.setColorAt(1.0, QColor(255, 255, 255, 0))

        # Clip to bar bounds
        clip = QPainterPath()
        clip.addRoundedRect(margin_x, bar_y, bar_w, bar_h, bar_r, bar_r)
        p.setClipPath(clip)
        p.fillRect(int(blob_x), bar_y, int(blob_w), bar_h, QBrush(grad))

        # Three floating dots below the bar
        p.setClipping(False)
        dot_y = bar_y + bar_h + 8
        dot_r = 2
        for i in range(3):
            offset = (self._phase + i * 0.12) % 1.0
            alpha = int(15 + 40 * math.sin(offset * math.pi))
            dot_x = margin_x + 4 + i * 10
            p.setBrush(QColor(255, 255, 255, alpha))
            p.drawEllipse(dot_x, dot_y, dot_r * 2, dot_r * 2)

        p.end()


# ─────────────────────────────────────────────────────────────────────────────
# App result row — monochrome with glow
# ─────────────────────────────────────────────────────────────────────────────

class AppResultWidget(QWidget):
    """Single app result row — compact, vertically centered, with text glow."""

    def __init__(self, item: ResultItem, parent=None):
        super().__init__(parent)
        self.setFixedHeight(44)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 12, 0)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # App icon — 24x24
        self._icon_label = QLabel()
        self._icon_label.setFixedSize(24, 24)
        pix = _load_icon(item.icon_path or item.action_data.get("exe_path", ""), 32)
        if pix:
            self._icon_label.setPixmap(pix.scaled(
                24, 24,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        else:
            fallback = QPixmap(24, 24)
            fallback.fill(QColor(0, 0, 0, 0))
            fp = QPainter(fallback)
            fp.setRenderHint(QPainter.RenderHint.Antialiasing)
            fp.setBrush(QColor(255, 255, 255, 15))
            fp.setPen(Qt.PenStyle.NoPen)
            fp.drawRoundedRect(0, 0, 24, 24, 6, 6)
            fp.setPen(QColor(255, 255, 255, 120))
            fp.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
            fp.drawText(fallback.rect(), Qt.AlignmentFlag.AlignCenter, item.title[0].upper())
            fp.end()
            self._icon_label.setPixmap(fallback)
        layout.addWidget(self._icon_label)

        # Text column
        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._name_label = QLabel(item.title)
        self._name_label.setFont(QFont("Segoe UI Variable", 12))
        # White text with subtle glow via stylesheet
        self._name_label.setStyleSheet(
            "color: rgba(255,255,255,0.92);"
        )

        raw_sub = item.subtitle or ""
        if raw_sub.lower().endswith(".exe") or "\\" in raw_sub or "/" in raw_sub:
            sub_text = "Application"
        else:
            sub_text = raw_sub or "Application"
        self._sub_label = QLabel(sub_text)
        self._sub_label.setFont(QFont("Segoe UI Variable", 9))
        self._sub_label.setStyleSheet("color: rgba(255,255,255,0.25);")

        text_col.addWidget(self._name_label)
        text_col.addWidget(self._sub_label)
        layout.addLayout(text_col)
        layout.addStretch()


# ─────────────────────────────────────────────────────────────────────────────
# Convert Result row
# ─────────────────────────────────────────────────────────────────────────────
class ConvertResultWidget(QWidget):
    choose_clicked = Signal()

    def __init__(self, item: ResultItem, parent=None):
        super().__init__(parent)
        self.setFixedHeight(50)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 12, 0)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Text column
        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._name_label = QLabel(item.title)
        self._name_label.setFont(QFont("Segoe UI Variable", 12))
        self._name_label.setStyleSheet("color: rgba(255,255,255,0.92);")

        self._sub_label = QLabel(item.subtitle)
        self._sub_label.setFont(QFont("Segoe UI Variable", 9))
        self._sub_label.setStyleSheet("color: rgba(255,255,255,0.4);")

        text_col.addWidget(self._name_label)
        text_col.addWidget(self._sub_label)
        layout.addLayout(text_col)
        layout.addStretch()

        # Button
        self._btn = QPushButton("Choose File")
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 4px;
                color: rgba(255, 255, 255, 0.9);
                padding: 4px 12px;
                font-family: 'Segoe UI Variable';
                font-size: 13px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.15);
            }
            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.05);
            }
        """)
        self._btn.clicked.connect(self.choose_clicked.emit)
        layout.addWidget(self._btn)


# ─────────────────────────────────────────────────────────────────────────────
# YT Format result row
# ─────────────────────────────────────────────────────────────────────────────
class YtFormatWidget(QWidget):
    folder_clicked = Signal()

    def __init__(self, item: ResultItem, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

        layout = QHBoxLayout(self)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        if item.selectable:
            layout.setContentsMargins(14, 6, 16, 6)
            self._folder_btn = QToolButton()
            self._folder_btn.setText("📁")
            self._folder_btn.setFixedSize(24, 24)
            self._folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._folder_btn.setStyleSheet("""
                QToolButton { background: transparent; border: none; color: rgba(255,255,255,180); font-size: 14px; }
                QToolButton:hover { color: white; }
            """)
            self._folder_btn.setToolTip("Change Download Folder")
            self._folder_btn.clicked.connect(lambda: self.folder_clicked.emit())
            layout.addWidget(self._folder_btn)

            self._label = QLabel(item.title)
            self._label.setFont(QFont("Segoe UI Variable", 12))
            self._label.setStyleSheet("color: rgba(255,255,255,230);")
            layout.addWidget(self._label)
            layout.addStretch()
        else:
            # Shift the header to align perfectly with the format text: 14 (margin) + 24 (button) + 14 (spacing) = 52
            layout.setContentsMargins(52, 4, 16, 4)
            self._label = QLabel(item.title)
            self._label.setFont(QFont("Segoe UI Variable", 10, QFont.Weight.Bold))
            self._label.setStyleSheet("color: rgba(255,255,255,100); letter-spacing: 1px;")
            layout.addWidget(self._label)
            layout.addStretch()

# ─────────────────────────────────────────────────────────────────────────────
# Border-scan animation overlay (page analysis) — now monochrome
# ─────────────────────────────────────────────────────────────────────────────

class BorderScanOverlay(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self._progress = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.hide()

    def start(self):
        self._progress = 0.0
        self.resize(self.parent().size())
        self.show()
        self._timer.start(16)

    def stop(self):
        self._timer.stop()
        self.hide()

    def _tick(self):
        self._progress = (self._progress + 0.008) % 1.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        r = self.rect().adjusted(1, 1, -1, -1)
        radius = 12.0

        path = QPainterPath()
        path.addRoundedRect(r, radius, radius)

        w, h = r.width(), r.height()
        perimeter = 2 * (w + h)
        pos = self._progress * perimeter
        tail_len = perimeter * 0.15

        pen = QPen()
        pen.setWidth(1)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        # Monochrome white comet
        steps = 16
        for i in range(steps):
            t_head = (pos - i * (tail_len / steps)) / perimeter % 1.0
            alpha  = int(80 * (1 - i / steps) ** 2)
            pen.setColor(QColor(255, 255, 255, alpha))
            painter.setPen(pen)
            pt = path.pointAtPercent(t_head)
            pt2 = path.pointAtPercent(max(0.0, t_head - 0.002))
            painter.drawLine(
                QPoint(int(pt.x()), int(pt.y())),
                QPoint(int(pt2.x()), int(pt2.y())),
            )

        painter.end()


# ─────────────────────────────────────────────────────────────────────────────
# Results panel
# ─────────────────────────────────────────────────────────────────────────────

class ResultsPanel(QWidget):
    yt_format_selected = Signal(str, str, str)  # url, format_id, folder_path
    app_selected       = Signal(str)
    action_selected    = Signal(str)
    file_selected      = Signal(str)
    followup_submitted = Signal(str)
    yt_folder_change_requested = Signal()
    chat_height_changed = Signal()
    bookmark_selected = Signal(str)
    image_convert_selected = Signal(str, str)
    image_resize_selected = Signal(int, int)
    file_selected = Signal(str)
    note_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ResultsPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # Stacked widget: 0=empty, 1=list, 2=chat, 3=thinking shimmer
        self._stack = QStackedWidget()
        self._stack.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._stack.setAutoFillBackground(False)
        self._layout.addWidget(self._stack)

        # Page 0: empty
        self._empty_page = QWidget()
        self._stack.addWidget(self._empty_page)

        # Page 1: app / calc / yt-format list
        self._list_widget = QListWidget()
        self._list_widget.setObjectName("ResultsList")
        self._list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list_widget.setAutoFillBackground(False)
        self._list_widget.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        vp = self._list_widget.viewport()
        vp.setAutoFillBackground(False)
        vp.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._stack.addWidget(self._list_widget)

        # Page 2: chat / page analysis
        self._chat_page = QWidget()
        self._chat_page.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._chat_page.setAutoFillBackground(False)
        chat_layout = QVBoxLayout(self._chat_page)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        self._chat_pane = QTextBrowser()
        self._chat_pane.setObjectName("ChatPane")
        self._chat_pane.setOpenExternalLinks(True)
        self._chat_pane.setReadOnly(True)
        self._chat_pane.setAutoFillBackground(False)
        self._chat_pane.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        vp2 = self._chat_pane.viewport()
        vp2.setAutoFillBackground(False)
        vp2.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        chat_layout.addWidget(self._chat_pane)

        # Hovering + / Follow-up Input Box
        self._followup_container = QWidget()
        self._followup_container.setFixedHeight(40)
        fu_layout = QHBoxLayout(self._followup_container)
        fu_layout.setContentsMargins(12, 0, 12, 12)

        self._followup_input = QLineEdit()
        self._followup_input.setObjectName("FollowUpInput")
        self._followup_input.setPlaceholderText("Ask a follow up...")
        self._followup_input.returnPressed.connect(self._on_followup_submitted)
        self._followup_input.hide()

        self._btn_followup = QToolButton()
        self._btn_followup.setText("+")
        self._btn_followup.setToolTip("Ask a follow up (Tab)")
        self._btn_followup.setObjectName("FollowUpBtn")
        self._btn_followup.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_followup.clicked.connect(self.show_followup_input)
        self._btn_followup.setFixedSize(28, 28)
        self._btn_followup.setStyleSheet("""
            QToolButton {
                background-color: rgba(255, 255, 255, 20);
                border: 1px solid rgba(255, 255, 255, 40);
                border-radius: 14px;
                color: rgba(255, 255, 255, 200);
                font-size: 20px; font-weight: bold;
                padding-bottom: 2px;
            }
            QToolButton:hover { background-color: rgba(255, 255, 255, 40); }
        """)
        self._followup_input.setStyleSheet("""
            QLineEdit {
                background-color: rgba(0, 0, 0, 60);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 6px; color: rgba(255, 255, 255, 240);
                padding: 4px 8px; font-size: 13px; font-family: 'Segoe UI Variable', sans-serif;
            }
        """)

        self._fu_spacer_left = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._fu_spacer_right = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        fu_layout.addItem(self._fu_spacer_left)
        fu_layout.addWidget(self._followup_input)
        fu_layout.addWidget(self._btn_followup)
        fu_layout.addItem(self._fu_spacer_right)

        chat_layout.addWidget(self._followup_container)
        self._stack.addWidget(self._chat_page)

        # Page 3: shimmer thinking animation
        self._thinking = ShimmerWidget()
        self._stack.addWidget(self._thinking)

        # Border scan overlay
        self._scan = BorderScanOverlay(self)

        # Download progress bar & label
        self._progress_bar = QProgressBar()
        self._progress_bar.setObjectName("DownloadProgress")
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.hide()
        self._layout.addWidget(self._progress_bar)

        self._download_status_label = QLabel()
        self._download_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._download_status_label.setStyleSheet("color: rgba(255,255,255,150); font-size: 13px; padding-bottom: 4px;")
        self._download_status_label.hide()
        self._layout.addWidget(self._download_status_label)

        # State
        self._current_items: list[ResultItem] = []
        self._yt_url: str = ""
        import os
        self._yt_download_dir = os.path.expanduser("~/Downloads")

        self._list_widget.itemActivated.connect(self._on_item_activated)
        self.setVisible(False)

    # ── Public API ─────────────────────────────────────────────────────────

    def show_thinking(self):
        self._stack.setCurrentIndex(3)
        self._thinking.start()
        self.setVisible(True)
        self._set_height_for_thinking()
        self.reset_followup()

    def reset_followup(self):
        self._followup_input.clear()
        self._followup_input.hide()
        self._btn_followup.show()
        self._fu_spacer_left.changeSize(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._fu_spacer_right.changeSize(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._followup_container.layout().invalidate()

    def show_followup_input(self):
        self._btn_followup.hide()
        self._fu_spacer_left.changeSize(0, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._fu_spacer_right.changeSize(0, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._followup_container.layout().invalidate()
        self._followup_input.show()
        self._followup_input.setFocus()
        
    def _on_followup_submitted(self):
        text = self._followup_input.text().strip()
        if text:
            self.reset_followup()
            self.followup_submitted.emit(text)

    def show_results(self, items: list[ResultItem]):
        self._thinking.stop()
        self._current_items = items
        self._progress_bar.hide()
        self._download_status_label.hide()
        self._scan.stop()

        if not items:
            self._stack.setCurrentIndex(0)
            self.setVisible(False)
            return

        kind = items[0].kind

        if kind in (ResultKind.CHAT, ResultKind.PAGE):
            self._show_chat(items[0])
        elif kind == ResultKind.THINKING:
            self.show_thinking()
        else:
            self._show_list(items)

        self.setVisible(True)

    def clear(self):
        self._thinking.stop()
        self._scan.stop()
        self._list_widget.clear()
        self._chat_pane.clear()
        self._progress_bar.hide()
        self._download_status_label.hide()
        self._current_items = []
        self._stack.setCurrentIndex(0)
        self.setMinimumHeight(0)
        self.setMaximumHeight(16777215)
        self.reset_followup()
        self.setVisible(False)

    def start_border_scan(self):
        self._scan.resize(self.size())
        self._scan.start()

    def stop_border_scan(self):
        self._scan.stop()

    def show_download_progress_mode(self):
        self._stack.setCurrentIndex(0)  # Hide the list
        self._progress_bar.setValue(0)
        self._progress_bar.show()
        self._download_status_label.setText("Preparing download...")
        self._download_status_label.show()
        self.setMinimumHeight(60)
        self.setMaximumHeight(100)

    def update_download_progress(self, downloaded: int, total: int):
        self._progress_bar.show()
        self._download_status_label.show()
        mb_done = downloaded / 1024 / 1024
        
        if total > 0:
            mb_total = total / 1024 / 1024
            self._progress_bar.setValue(int(downloaded / total * 100))
            self._download_status_label.setText(f"Downloading... {mb_done:.1f} MB / {mb_total:.1f} MB")
        else:
            self._progress_bar.setValue(0)
            self._download_status_label.setText(f"Downloading... {mb_done:.1f} MB")

    def select_next(self):
        count = self._list_widget.count()
        if not count: return
        row = self._list_widget.currentRow()
        for i in range(1, count + 1):
            next_row = (row + i) % count
            item = self._list_widget.item(next_row)
            if item and (item.flags() & Qt.ItemFlag.ItemIsSelectable):
                self._list_widget.setCurrentRow(next_row)
                break

    def select_prev(self):
        count = self._list_widget.count()
        if not count: return
        row = self._list_widget.currentRow()
        for i in range(1, count + 1):
            prev_row = (row - i) % count
            item = self._list_widget.item(prev_row)
            if item and (item.flags() & Qt.ItemFlag.ItemIsSelectable):
                self._list_widget.setCurrentRow(prev_row)
                break

    def activate_selected(self):
        item = self._list_widget.currentItem()
        if item:
            self._on_item_activated(item)

    # ── Internal ───────────────────────────────────────────────────────────

    def _show_list(self, items: list[ResultItem]):
        self._list_widget.clear()
        self._yt_url = ""

        for ri in items:
            litem = QListWidgetItem(self._list_widget)
            litem.setData(Qt.ItemDataRole.UserRole, ri)
            if not ri.selectable:
                litem.setFlags(litem.flags() & ~Qt.ItemFlag.ItemIsSelectable & ~Qt.ItemFlag.ItemIsEnabled)

            if ri.kind == ResultKind.APP:
                widget = AppResultWidget(ri)
                litem.setSizeHint(widget.sizeHint())
                self._list_widget.setItemWidget(litem, widget)

            elif ri.kind in (ResultKind.CALC, ResultKind.CONVERT):
                litem.setText(f"  = {ri.title}")
                if ri.raw_text:
                    litem.setToolTip(ri.raw_text)
                font = QFont("Segoe UI Variable Display", 20, QFont.Weight.Thin)
                litem.setFont(font)
                litem.setForeground(QColor(255, 255, 255, 200))
                litem.setSizeHint(QSize(0, 44))

            elif ri.kind in (ResultKind.FILE, ResultKind.ACTION, ResultKind.NOTE):
                # Use AppResultWidget to render files, actions, and notes cleanly
                widget = AppResultWidget(ri)
                litem.setSizeHint(widget.sizeHint())
                self._list_widget.setItemWidget(litem, widget)

            elif ri.kind == ResultKind.YT_FORMAT:
                widget = YtFormatWidget(ri)
                widget.folder_clicked.connect(self.yt_folder_change_requested.emit)
                litem.setSizeHint(widget.sizeHint())
                self._list_widget.setItemWidget(litem, widget)
                self._yt_url = ri.action_data.get("url", "")

            elif ri.kind == ResultKind.IMAGE_CONVERT:
                widget = ConvertResultWidget(ri)
                # When the button is clicked, we trigger the activation on the list item manually
                widget.choose_clicked.connect(lambda r=ri: self._on_item_activated_by_data(r))
                litem.setSizeHint(QSize(0, 50))
                self._list_widget.setItemWidget(litem, widget)

            elif ri.kind == ResultKind.IMAGE_RESIZE:
                widget = ConvertResultWidget(ri)
                widget.choose_clicked.connect(lambda r=ri: self._on_item_activated_by_data(r))
                litem.setSizeHint(QSize(0, 50))
                self._list_widget.setItemWidget(litem, widget)

            else:
                litem.setText(f"  {ri.title}")
                litem.setSizeHint(QSize(0, 36))

        if self._list_widget.count() > 0:
            for i in range(self._list_widget.count()):
                item = self._list_widget.item(i)
                if item.flags() & Qt.ItemFlag.ItemIsSelectable:
                    self._list_widget.setCurrentRow(i)
                    break

        self.setMinimumHeight(0)
        self.setMaximumHeight(16777215)
        self._stack.setCurrentIndex(1)
        self._adjust_list_height()

    def _show_chat(self, item: ResultItem):
        html = item.html
        if not html and item.raw_text:
            try:
                import markdown
                html = markdown.markdown(
                    item.raw_text,
                    extensions=["fenced_code", "tables", "nl2br"],
                )
            except Exception:
                html = f"<pre>{item.raw_text}</pre>"

        styled = f"""
        <style>
          body {{ color: rgba(255,255,255,0.88);
                 font-family: 'Segoe UI Variable', 'Segoe UI', sans-serif;
                 font-size: 13px; line-height: 1.6; margin: 0; padding: 0;
                 word-wrap: break-word; word-break: break-word; }}
          code {{ background: rgba(255,255,255,0.05); border-radius: 3px;
                 padding: 1px 4px; font-size: 12px;
                 font-family: 'Cascadia Code', 'Consolas', monospace; }}
          pre  {{ background: rgba(255,255,255,0.03); border-radius: 6px;
                 padding: 10px 14px; overflow-x: auto;
                 border: 1px solid rgba(255,255,255,0.05); }}
          p    {{ background: transparent; margin: 3px 0; }}
          a    {{ color: rgba(255,255,255,0.70); text-decoration: underline; }}
          strong {{ color: rgba(255,255,255,0.95); }}
          h1,h2,h3 {{ color: rgba(255,255,255,0.92); margin: 8px 0 4px;
                      font-weight: 500; }}
          ul,ol {{ margin: 4px 0; padding-left: 18px; }}
          li   {{ margin: 1px 0; }}
          blockquote {{ margin: 4px 0 12px 10px; padding-left: 12px; border-left: 3px solid rgba(255,255,255,0.2); color: rgba(255,255,255,0.7); font-style: italic; }}
        </style>
        {html}
        """
        self._chat_pane.setHtml(styled)

        if item.action_data.get("show_followup", True):
            self._followup_container.show()
        else:
            self._followup_container.hide()

        self._stack.setCurrentIndex(2)
        QTimer.singleShot(10, self._adjust_chat_height)
        
        if item.action_data.get("scroll_to_bottom", True):
            QTimer.singleShot(20, self._scroll_chat_to_bottom)

    def _on_item_activated(self, litem: QListWidgetItem):
        ri: ResultItem = litem.data(Qt.ItemDataRole.UserRole)
        if not ri:
            return
        if ri.kind == ResultKind.APP:
            self.app_selected.emit(ri.action_data.get("exe_path", ""))
        elif ri.kind == ResultKind.YT_FORMAT:
            if not ri.selectable:
                return
            format_id = ri.action_data.get("format_id")
            if self._yt_url and format_id:
                self.yt_format_selected.emit(self._yt_url, format_id, self._yt_download_dir)
        elif ri.kind == ResultKind.BOOKMARK:
            self.bookmark_selected.emit(ri.action_data.get("url", ""))
        elif ri.kind == ResultKind.IMAGE_CONVERT:
            self.image_convert_selected.emit(
                ri.action_data.get("source_format", ""),
                ri.action_data.get("target_format", "")
            )
        elif ri.kind == ResultKind.IMAGE_RESIZE:
            self.image_resize_selected.emit(
                ri.action_data.get("width", 0),
                ri.action_data.get("height", 0)
            )
        elif ri.kind == ResultKind.ACTION:
            self.action_selected.emit(ri.action_data.get("action", ""))
        elif ri.kind == ResultKind.FILE:
            self.file_selected.emit(ri.action_data.get("path", ""))

    def _on_item_activated_by_data(self, ri: ResultItem):
        if not ri:
            return
        if ri.kind == ResultKind.IMAGE_CONVERT:
            self.image_convert_selected.emit(
                ri.action_data.get("source_format", ""),
                ri.action_data.get("target_format", "")
            )
        elif ri.kind == ResultKind.IMAGE_RESIZE:
            self.image_resize_selected.emit(
                ri.action_data.get("width", 0),
                ri.action_data.get("height", 0)
            )
        elif ri.kind == ResultKind.ACTION:
            self.action_selected.emit(ri.action_data.get("action", ""))
        elif ri.kind == ResultKind.FILE:
            self.file_selected.emit(ri.action_data.get("path", ""))

    def get_selected_item(self) -> Optional[ResultItem]:
        row = self._list_widget.currentRow()
        if row < 0 or row >= len(self._current_items):
            return None
        return self._current_items[row]

    def _adjust_list_height(self):
        count = self._list_widget.count()
        total_h = 0
        for i in range(count):
            item = self._list_widget.item(i)
            sh = item.sizeHint().height()
            total_h += sh if sh > 0 else 44
        padding = 6
        target = min(total_h + padding, 320)
        self.setFixedHeight(target)

    def _adjust_chat_height(self):
        doc_h = self._chat_pane.document().size().height()
        target = min(int(doc_h) + 60, 400)
        self.setFixedHeight(max(target, 100))
        self.chat_height_changed.emit()

    def _scroll_chat_to_bottom(self):
        sb = self._chat_pane.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _set_height_for_thinking(self):
        self.setFixedHeight(36)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._scan.isVisible():
            self._scan.resize(self.size())
