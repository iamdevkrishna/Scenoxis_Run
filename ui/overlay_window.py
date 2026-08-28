"""
ui/overlay_window.py
Main Scenoxis Run overlay window.

Design:
  - Frameless, always-on-top, translucent Qt window
  - Acrylic blur via core/dwm_blur.py
  - Rounded-corner clip via QPainterPath in paintEvent
  - Centers on the active monitor
  - Glass card frame holding: search bar + intent badge + divider + results panel
  - All LLM calls dispatched to a QThread worker; UI updates arrive via Qt signals
"""
import logging
import subprocess
from typing import Optional

from PySide6.QtCore import (
    Qt, QThread, Signal, QObject, QTimer, QPropertyAnimation,
    QEasingCurve, QPoint, QSize, QRect,
)
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QFont, QFontDatabase,
    QScreen, QGuiApplication, QKeyEvent, QCursor,
    QPen, QBrush,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QApplication, QSizePolicy,
)

from ui.search_bar import SearchBar
from ui.results_panel import ResultsPanel
from ui.result_item import ResultItem, ResultKind
from core import app_index as app_idx
from core.calculator import is_arithmetic, calculate as calc_core
from agent.classifier import classify_for_live_preview

log = logging.getLogger(__name__)

WINDOW_WIDTH  = 560
CARD_PADDING  = 12
CARD_RADIUS   = 8  # Match Windows 11 native DWM corner radius
ANIM_DURATION = 180


# ─────────────────────────────────────────────────────────────────────────────
# Background worker — runs agent graph on a QThread
# ─────────────────────────────────────────────────────────────────────────────

class AgentWorker(QObject):
    """Runs the LLM agent graph for chat queries."""
    finished = Signal(str, dict)  # query, state_dict
    error    = Signal(str, str)   # query, error

    def __init__(self, query: str, active_tab_url: Optional[str] = None, messages: list = None, image_bytes: bytes = None):
        super().__init__()
        self.query = query
        self.active_tab_url = active_tab_url
        self.messages = messages or []
        self.image_bytes = image_bytes

    def run(self):
        try:
            from agent.graph import run_query
            result = run_query(self.query, self.active_tab_url, self.messages, self.image_bytes)
            self.finished.emit(self.query, result)
        except Exception as exc:
            log.exception("AgentWorker error")
            self.error.emit(self.query, str(exc))


class PageAnalysisWorker(QObject):
    """Runs the page capture + Groq vision call."""
    finished = Signal(str, str) # instruction, result
    error    = Signal(str, str) # instruction, error

    def __init__(self, instruction: str = ""):
        super().__init__()
        self.instruction = instruction

    def run(self):
        try:
            from agent.tools.page_analyzer import analyze_current_page
            result = analyze_current_page.invoke({"instruction": self.instruction})
            self.finished.emit(self.instruction, result)
        except Exception as exc:
            self.error.emit(self.instruction, str(exc))


class YTDownloadWorker(QObject):
    progress = Signal(int, int, str)   # downloaded_bytes, total_bytes, message
    finished = Signal(dict)
    error    = Signal(str)

    def __init__(self, url: str, format_id: str, output_dir: str):
        super().__init__()
        self.url = url
        self.format_id = format_id
        self.output_dir = output_dir

    def run(self):
        try:
            from agent.tools.yt_downloader import download

            def _cb(d):
                if d.get("status") == "downloading":
                    dl   = d.get("downloaded_bytes", 0)
                    tot  = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    msg  = d.get("filename", "") if not dl and not tot else ""
                    self.progress.emit(dl, tot, msg)

            result = download(self.url, self.format_id, output_dir=self.output_dir, progress_callback=_cb)
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class YTListWorker(QObject):
    """Fetches available YT formats on a background thread.
    MUST be at module level — PySide6 Signals don't work in nested classes."""
    done  = Signal(list)
    error = Signal(str)

    def __init__(self, url: str):
        super().__init__()
        self._url = url

    def run(self):
        print(f"[YT] Worker thread started for URL: {self._url}")
        try:
            from agent.tools.yt_downloader import list_formats
            fmts = list_formats(self._url)
            print(f"[YT] list_formats returned {len(fmts)} formats")
            if not fmts:
                print("[YT] ERROR: No formats found")
                self.error.emit("No formats found. Check the URL or try again.")
            else:
                for i, f in enumerate(fmts):
                    print(f"[YT]   format {i+1}: {f['note']}")
                self.done.emit(fmts)
        except Exception as exc:
            print(f"[YT] EXCEPTION in worker: {type(exc).__name__}: {exc}")
            import traceback
            traceback.print_exc()
            self.error.emit(str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Monochrome search icon — QPainter drawn, no emoji
# ─────────────────────────────────────────────────────────────────────────────

class _MonoSearchIcon(QWidget):
    """Pure white magnifying glass drawn with QPainter. No fonts, no emoji."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(22, 22)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

    def paintEvent(self, event):
        from core.config import is_dark_mode
        dark = is_dark_mode()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Circle (lens)
        color = QColor(255, 255, 255, 90) if dark else QColor(0, 0, 0, 90)
        pen = QPen(color, 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(4, 3, 11, 11)

        # Handle (diagonal line)
        p.setPen(QPen(color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(13, 13, 17, 17)

        p.end()


# ─────────────────────────────────────────────────────────────────────────────
# Overlay window
# ─────────────────────────────────────────────────────────────────────────────

class OverlayWindow(QWidget):
    toggle_visibility = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_window()
        self._load_fonts()
        self._build_ui()
        self._apply_stylesheet()
        self._connect_signals()
        self._setup_animations()

        self._conversation_messages: list = []
        self._active_tab_url: Optional[str] = None
        self._active_threads: list[QThread] = []
        self._agent_thread: Optional[QThread] = None
        self._agent_worker: Optional[AgentWorker] = None
        self._pending_yt_url: str = ""
        self._is_animating = False
        self._target_y = 0
        self._is_active = False  # Track logical visibility since we never hide it natively

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._dispatch_agent)

        self.toggle_visibility.connect(self._on_toggle)

    # ─────────────────────────────────────────────────────────────────────
    # Window setup
    # ─────────────────────────────────────────────────────────────────────

    def _setup_window(self):
        # DO NOT use FramelessWindowHint, as it breaks Windows 11 DWM backdrops on Insider builds.
        # Instead, we use CustomizeWindowHint and Tool.
        # Tool hides it from the taskbar and Alt+Tab, and disables standard DWM show animations!
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Window |
            Qt.WindowType.CustomizeWindowHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setWindowTitle("Scenoxis Run")
        self.setObjectName("ScenoxisOverlay")
        self._dialog_open = False    # flag to prevent auto-hide when a dialog is open

    def _load_fonts(self):
        # We use standard system fonts (Segoe UI on Windows)
        pass

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._card = QFrame()
        self._card.setObjectName("GlassCard")
        self._card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self._card.setFixedWidth(WINDOW_WIDTH)
        self._card.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._card.setAutoFillBackground(False)

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(0, CARD_PADDING, 0, CARD_PADDING)
        card_layout.setSpacing(0)

        # ── Top row: search icon + search bar + badge ───────────────────
        top_row = QHBoxLayout()
        top_row.setContentsMargins(CARD_PADDING, 0, CARD_PADDING, 0)
        top_row.setSpacing(6)

        # Search icon — monochrome QPainter-drawn magnifying glass
        self._search_icon = _MonoSearchIcon()
        top_row.addWidget(self._search_icon, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._search = SearchBar()
        top_row.addWidget(self._search, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._badge = QLabel("")
        self._badge.setObjectName("IntentBadge")
        self._badge.setFixedHeight(16)
        self._badge.hide()
        top_row.addWidget(self._badge, alignment=Qt.AlignmentFlag.AlignVCenter)

        card_layout.addLayout(top_row)

        # ── Divider ────────────────────────────────────────────────────
        self._divider = QFrame()
        self._divider.setObjectName("Divider")
        self._divider.setFixedHeight(1)
        self._divider.hide()
        card_layout.addSpacing(4)
        card_layout.addWidget(self._divider)
        card_layout.addSpacing(2)

        # ── Results panel ──────────────────────────────────────────────
        self._results = ResultsPanel()
        card_layout.addWidget(self._results)

        outer.addWidget(self._card, alignment=Qt.AlignmentFlag.AlignCenter)
        self._card.adjustSize()

    def _apply_stylesheet(self):
        import os
        from core.config import is_dark_mode, get_resource_path
        qss_path = get_resource_path("ui", "styles.qss")
        try:
            with open(qss_path, "r", encoding="utf-8") as f:
                qss = f.read()
                if not is_dark_mode():
                    qss = qss.replace("255, 255, 255", "0, 0, 0")
                    qss = qss.replace("rgba(255,255,255", "rgba(0,0,0")
                self.setStyleSheet(qss)
        except FileNotFoundError:
            log.warning("styles.qss not found")

    def _setup_animations(self):
        """Create reusable QPropertyAnimations for smooth show/hide."""
        # Opacity animation
        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._opacity_anim.setDuration(ANIM_DURATION)
        self._opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Y-position slide animation
        self._pos_anim = QPropertyAnimation(self, b"pos", self)
        self._pos_anim.setDuration(ANIM_DURATION)
        self._pos_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _connect_signals(self):
        self._search.textChanged.connect(self._on_text_changed)
        self._search.escape_pressed.connect(self.hide_overlay)
        self._search.enter_pressed.connect(self._on_enter)
        self._search.tab_pressed.connect(self._on_tab_pressed)
        self._search.arrow_up.connect(self._results.select_prev)
        self._search.arrow_down.connect(self._results.select_next)

        self._results.app_selected.connect(self._launch_exe)
        self._results.action_selected.connect(self._run_sys_control)
        self._results.file_selected.connect(self._launch_file)
        self._results.yt_format_selected.connect(self._start_yt_download)
        self._results.followup_submitted.connect(self._on_followup)
        self._results.yt_folder_change_requested.connect(self._on_yt_folder_change)
        self._results.chat_height_changed.connect(self._relayout)
        self._results.bookmark_selected.connect(self._launch_bookmark)
        self._results.image_convert_selected.connect(self._start_image_convert)
        self._results.image_resize_selected.connect(self._start_image_resize)
        self._search.delete_pressed.connect(self._on_delete_pressed)

    # ─────────────────────────────────────────────────────────────────────
    # Show / hide with animations
    # ─────────────────────────────────────────────────────────────────────

    def show_overlay(self):
        if self._is_active:
            return
        
        self._is_active = True
        self._position_on_active_monitor()
        self._hiding = False

        # Grab the active browser URL for context before we steal focus!
        import core.browser_tracker as bt
        self._active_tab_url = bt.get_active_browser_url()
        
        self.raise_()
        self.activateWindow()
        self._search.setFocus()
        self._search.selectAll()

        # Fix Windows 11 DWM initial missing blur bug:
        # If we resize the window simultaneously while moving it on-screen, DWM still ignores it.
        # We MUST resize the window AFTER it is fully painted on the monitor!
        if not getattr(self, "_first_show_done", False):
            self._first_show_done = True
            QTimer.singleShot(50, self._jiggle_for_dwm)

    def _jiggle_for_dwm(self):
        """Force a 1-pixel resize *after* the window is visible to kickstart DWM Acrylic."""
        self.resize(self.width(), self.height() + 1)
        self._relayout()

    def hide_overlay(self):
        if not self._is_active:
            return
        self._is_active = False
        self._hiding = False
        self._results.clear()
        self._badge.hide()
        self._divider.hide()
        self._conversation_messages = []
        
        # Instantly hide by moving off-screen to preserve DWM blur composition!
        self.move(-10000, -10000)
        self.lower()  # Force Windows to give focus back to the previous app

    def _on_anim_finished(self):
        self._is_animating = False

    def _on_toggle(self):
        if self._is_active:
            self.hide_overlay()
        else:
            self.show_overlay()

    def hotkey_callback(self):
        self.toggle_visibility.emit()

    # ─────────────────────────────────────────────────────────────────────
    # Positioning
    # ─────────────────────────────────────────────────────────────────────

    def _position_on_active_monitor(self):
        """Place the window at top-center of the monitor the cursor is on."""
        cursor_pos = QCursor.pos()  # actual mouse position in global coords
        for screen in QGuiApplication.screens():
            if screen.geometry().contains(cursor_pos):
                geo = screen.availableGeometry()
                x = geo.x() + (geo.width() - WINDOW_WIDTH) // 2
                y = geo.y() + int(geo.height() * 0.18)
                self.move(x, y)
                return
        # Fallback: primary screen
        geo = QGuiApplication.primaryScreen().availableGeometry()
        x = geo.x() + (geo.width() - WINDOW_WIDTH) // 2
        y = geo.y() + int(geo.height() * 0.18)
        self.move(x, y)

    # ─────────────────────────────────────────────────────────────────────
    # DWM Acrylic blur
    # ─────────────────────────────────────────────────────────────────────

    def _apply_acrylic(self):
        try:
            from core.config import is_dark_mode
            from core import dwm_blur
            hwnd = int(self.winId())
            # Tint nearly transparent — let DWM just blur, we paint our own
            # dark background inside the rounded clip path in paintEvent
            dwm_blur.apply_blur(hwnd, dark_mode=is_dark_mode(), tint_color=0x01000000)
        except Exception as exc:
            log.debug("_apply_acrylic failed: %s", exc)

    def nativeEvent(self, eventType, message):
        try:
            import ctypes
            from ctypes.wintypes import MSG
            msg = MSG.from_address(message.__int__())
            
            # WM_NCCALCSIZE = 0x0083
            if msg.message == 0x0083:
                # By returning 0 when wParam is True, we tell Windows that our client area 
                # covers the entire window. This hides the standard title bar but preserves 
                # the DWM frame, drop shadow, and Mica/Acrylic backdrops!
                if msg.wParam:
                    return True, 0
            
            # WM_NCHITTEST = 0x0084
            elif msg.message == 0x0084:
                # Return HTCLIENT (1) so the window cannot be moved or resized by dragging
                return True, 1
                
        except Exception as e:
            log.error(f"Error in nativeEvent: {e}")
            
        return super().nativeEvent(eventType, message)

    def showEvent(self, event):
        super().showEvent(event)
        
        # Apply the Acrylic blur synchronously so it's ready before the fade-in animation starts
        self._apply_acrylic()

        # Remove WS_SYSMENU, WS_BORDER, and WS_THICKFRAME to completely hide the 
        # standard Windows 11 1px glowing outline!
        try:
            import ctypes
            hwnd = int(self.winId())
            GWL_STYLE = -16
            WS_SYSMENU = 0x00080000
            WS_BORDER = 0x00800000
            WS_THICKFRAME = 0x00040000
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style & ~WS_SYSMENU & ~WS_BORDER & ~WS_THICKFRAME)
        except Exception as e:
            log.error(f"Failed to remove window buttons: {e}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()

    def event(self, event):
        return super().event(event)


    # ─────────────────────────────────────────────────────────────────────
    # Painting — rounded corners clip
    # ─────────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        """Frosted-glass Spotlight card — dark or light tint painted inside rounded clip."""
        try:
            from PySide6.QtGui import QLinearGradient, QBrush, QPainterPath, QPen, QColor, QPainter
            from core.config import is_dark_mode
            w, h = self.width(), self.height()
            r = CARD_RADIUS

            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            dark = is_dark_mode()

            # We don't clip the path anymore! 
            # Windows 11 DWM native corner rounding (DWMWCP_ROUND) will smoothly clip the window.
            # We just paint the full rect.

            # ── Layer 1: Semi-transparent background ──────────────────────────────
            # Pure black at 110 opacity allows for a very dark tint WITHOUT masking the blur!
            if dark:
                painter.fillRect(self.rect(), QColor(0, 0, 0, 110))
            else:
                painter.fillRect(self.rect(), QColor(245, 245, 245, 140))

            # ── Layer 2: Glossy top reflection (Spotlight signature) ───────────────
            gloss = QLinearGradient(0, 0, 0, 60)
            if dark:
                gloss.setColorAt(0.0, QColor(255, 255, 255, 18))
                gloss.setColorAt(0.5, QColor(255, 255, 255, 5))
                gloss.setColorAt(1.0, QColor(255, 255, 255, 0))
            else:
                gloss.setColorAt(0.0, QColor(255, 255, 255, 80))
                gloss.setColorAt(0.5, QColor(255, 255, 255, 30))
                gloss.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(0, 0, w, 60, QBrush(gloss))

            # ── Layer 3: Subtle inner glow at bottom ──────────────────────────────
            bottom_glow = QLinearGradient(0, h - 20, 0, h)
            if dark:
                bottom_glow.setColorAt(0.0, QColor(255, 255, 255, 0))
                bottom_glow.setColorAt(1.0, QColor(255, 255, 255, 3))
            else:
                bottom_glow.setColorAt(0.0, QColor(0, 0, 0, 0))
                bottom_glow.setColorAt(1.0, QColor(0, 0, 0, 10))
            painter.fillRect(0, h - 20, w, 20, QBrush(bottom_glow))

            # ── Layer 4: Hairline border with gradient opacity ────────────
            painter.setClipping(False)
            border_grad = QLinearGradient(0, 0, 0, h)
            border_grad.setColorAt(0.0, QColor(255, 255, 255, 40))
            border_grad.setColorAt(0.5, QColor(255, 255, 255, 18))
            border_grad.setColorAt(1.0, QColor(255, 255, 255, 10))
            pen = QPen(QBrush(border_grad), 0.5)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(0.5, 0.5, w - 1, h - 1, r, r)

            painter.end()
        except Exception as e:
            log.exception("paintEvent failed")

    # ─────────────────────────────────────────────────────────────────────
    # Input handling
    # ─────────────────────────────────────────────────────────────────────

    def _on_text_changed(self, text: str):
        self._debounce.stop()

        if not text.strip():
            self._results.clear()
            self._badge.hide()
            self._divider.hide()
            self._conversation_messages = []
            self._relayout()
            return

        # ── Instant local preview ──────────────────────────────────────
        preview_intent = classify_for_live_preview(text, app_idx.get_index())

        if preview_intent == "calc":
            r = calc_core(text)
            if not r["error"]:
                self._show_calc_result(text, r["result"])
                self._set_badge("CALC")
                self._debounce.stop()
                return

        if preview_intent == "app_launch":
            entries = app_idx.get_index().search(text, limit=6)
            if entries:
                self._show_app_results(entries)
                self._set_badge("LAUNCH")
                self._debounce.stop()
                return

        if preview_intent == "view_bookmarks":
            self._show_bookmarks()
            self._set_badge("SAVED")
            self._debounce.stop()
            return
            
        if preview_intent == "view_notes":
            self._show_notes()
            self._set_badge("NOTES")
            self._debounce.stop()
            return
            
        if preview_intent in ("sys_control", "media_control"):
            self._show_sys_control_preview(text, preview_intent)
            self._set_badge("SYSTEM" if preview_intent == "sys_control" else "MEDIA")
            self._debounce.stop()
            return
            
        if preview_intent == "convert":
            self._show_convert_preview(text)
            self._set_badge("CONVERT")
            self._debounce.stop()
            return
            
        if preview_intent == "image_convert":
            self._run_image_convert_from_query(text)
            self._debounce.stop()
            return
            
        if preview_intent == "image_resize":
            self._run_image_resize_from_query(text)
            self._debounce.stop()
            return
            
        if preview_intent == "file_search":
            self._show_file_search_preview(text)
            self._set_badge("FILE SEARCH")
            self._debounce.stop()
            return

        # If we got here, it is NOT an instant app launch or math calc.
        # Clear any stale app results from when the query was shorter!
        self._results.clear()
        self._badge.hide()
        self._divider.hide()
        self._relayout()

    def _on_enter(self):
        text = self._search.text().strip()
        if not text:
            return

        # If a selectable list result is showing (apps / yt formats / bookmarks), activate it
        current_items = self._results._current_items
        if current_items and current_items[0].kind in (
            ResultKind.APP, ResultKind.YT_FORMAT, ResultKind.BOOKMARK
        ):
            self._results.activate_selected()
            return

        # Otherwise dispatch (skip debounce — user explicitly pressed Enter)
        self._debounce.stop()
        self._dispatch_agent()

    def _on_tab_pressed(self):
        # If chat page is visible, tab should focus the follow-up input
        if self._results._stack.currentIndex() == 2:
            self._results.show_followup_input()

    def _on_followup(self, text: str):
        # Don't touch the main search bar, just run the agent with the new text
        self._dispatch_agent_with_query(text)

    def _dispatch_agent(self):
        query = self._search.text().strip()
        if not query:
            return

        # 1. Quick local classification
        from agent.classifier import classify
        intent = classify(query, app_index=app_idx.get_index(), active_tab_url=self._active_tab_url)
        log.info("Query '%s' classified as %s", query, intent)
        
        self._dispatch_agent_with_query(query, intent)

    def _dispatch_agent_with_query(self, query: str, intent=None):
        self._current_agent_query = query
        if not intent:
            from agent.classifier import classify
            intent = classify(query, app_idx.get_index(), self._active_tab_url)

        if intent == "page_analyze":
            self._run_page_analysis(query)
            return

        if intent == "yt_download":
            self._run_yt_list(query)
            return

        if intent == "save_bookmark":
            self._save_bookmark(query)
            return
            
        if intent == "view_bookmarks":
            self._show_bookmarks()
            return
            
        if intent == "view_notes":
            self._show_notes()
            return
            
        if intent == "image_convert":
            self._run_image_convert_from_query(query)
            return

        if intent == "image_resize":
            self._run_image_resize_from_query(query)
            return

        if intent == "sys_control":
            self._run_sys_control(query)
            return

        if intent == "media_control":
            self._run_sys_control(query)
            return

        if intent == "file_search":
            self._run_file_search(query)
            return

        if intent == "reminder":
            self._run_reminder(query)
            return

        if intent == "convert":
            # Just let it execute as a preview calculation (it's handled by live preview)
            # If they hit enter, we do nothing or clear.
            return

        # Chat — show thinking then run agent on background thread
        self._results.show_thinking()
        self._results.start_border_scan()
        self._divider.show()
        self._badge.hide()
        self._relayout()
        self._run_agent(query)

    # ─────────────────────────────────────────────────────────────────────
    # Result display helpers
    # ─────────────────────────────────────────────────────────────────────

    def _show_app_results(self, entries):
        items = []
        for e in entries:
            ri = ResultItem(
                kind=ResultKind.APP,
                title=e.name,
                subtitle=e.exe_path,
                icon_path=e.icon_path or e.exe_path,
                action_data={"exe_path": e.exe_path},
                score=0,
            )
            items.append(ri)
        self._divider.show()
        self._results.show_results(items)
        self._relayout()

    def _show_bookmarks(self):
        import core.bookmarks as bm
        bookmarks = bm.get_bookmarks()
        if not bookmarks:
            self._show_chat_result(text="No saved links found. Type `save` to bookmark your current tab.")
            return

        items = []
        for b in bookmarks:
            ri = ResultItem(
                kind=ResultKind.BOOKMARK,
                title=b.get("title", b.get("url")),
                subtitle=b.get("url"),
                action_data={"url": b.get("url")},
                score=0,
            )
            items.append(ri)
        self._divider.show()
        self._results.show_results(items)
        self._relayout()

    def _show_notes(self):
        import core.notes as notes
        import datetime
        n = notes.get_notes()
        if not n:
            self._show_chat_result(text="No saved notes found. Type `note: <your note>` to save one.")
            return

        items = []
        for note_dict in reversed(n):
            if isinstance(note_dict, str):
                text = note_dict
                subtitle = "Old Note"
                note_id = ""
            else:
                text = note_dict.get("text", "")
                ts = note_dict.get("timestamp", 0)
                dt = datetime.datetime.fromtimestamp(ts)
                subtitle = f"{dt.strftime('%A, %b %d %I:%M %p')}  •  Press Delete to delete"
                note_id = note_dict.get("id", "")
                
            ri = ResultItem(
                kind=ResultKind.NOTE,
                title=text,
                subtitle=subtitle,
                action_data={"id": note_id},
                score=0,
                selectable=True
            )
            items.append(ri)
        self._divider.show()
        self._results.show_results(items)
        self._relayout()

    def _delete_note(self, note_id: str):
        if not note_id:
            return
        import core.notes as notes
        if notes.delete_note(note_id):
            self._show_notes()

    def _run_image_convert_from_query(self, query: str):
        from agent.classifier import _CONVERT_RE
        m = _CONVERT_RE.match(query)
        if not m:
            return
        self._run_image_convert_explicit(m.group(1), m.group(2))

    def _run_image_convert_explicit(self, src: str, tgt: str):
        ri = ResultItem(
            kind=ResultKind.IMAGE_CONVERT,
            title=f"Convert {src.upper()} to {tgt.upper()}",
            subtitle="Press Enter to select file...",
            action_data={"source_format": src, "target_format": tgt},
        )
        self._set_badge("CONVERT")
        self._divider.show()
        self._results.show_results([ri])
        self._relayout()

    def _run_image_resize_from_query(self, query: str):
        from agent.classifier import _RESIZE_RE
        m = _RESIZE_RE.match(query)
        if not m:
            return
        self._run_image_resize_explicit(int(m.group(1)), int(m.group(2)))

    def _run_image_resize_explicit(self, width: int, height: int):
        ri = ResultItem(
            kind=ResultKind.IMAGE_RESIZE,
            title=f"Resize to {width}x{height}",
            subtitle="Press Enter to select image...",
            action_data={"width": width, "height": height},
        )
        self._set_badge("RESIZE")
        self._divider.show()
        self._results.show_results([ri])
        self._relayout()

    def _start_image_convert(self, src: str, tgt: str):
        from PySide6.QtWidgets import QFileDialog
        import os
        from core.converter import convert_image
        
        self._dialog_open = True
        
        try:
            # Get input file
            src_filter = f"{src.upper()} Image (*.{src.lower()})"
            src_path, _ = QFileDialog.getOpenFileName(
                self, f"Select {src.upper()} Image", "", src_filter
            )
            if not src_path:
                return
                
            # Get output file
            default_out = os.path.splitext(src_path)[0] + "." + tgt.lower()
            tgt_filter = f"{tgt.upper()} Image (*.{tgt.lower()})"
            tgt_path, _ = QFileDialog.getSaveFileName(
                self, f"Save As {tgt.upper()}", default_out, tgt_filter
            )
            if not tgt_path:
                return
                
            # Convert
            success, final_path = convert_image(src_path, tgt_path, tgt)
            
            if success:
                self._search.setText("")
                msg_html = f"Successfully converted image to <strong>{tgt.upper()}</strong>!<br><br>Saved to: <a href='file:///{final_path.replace(' ', '%20')}'>{final_path}</a>"
                self._show_chat_result(html=msg_html)
            else:
                msg_html = f"Failed to convert image to <strong>{tgt.upper()}</strong>.<br><br>Make sure the input file is a valid image format supported by Pillow."
                self._show_chat_result(html=msg_html)
                
        finally:
            self._dialog_open = False

    def _start_image_resize(self, width: int, height: int):
        from PySide6.QtWidgets import QFileDialog
        import os
        from core.converter import resize_image
        
        self._dialog_open = True
        
        try:
            # Get input file
            src_filter = "Images (*.png *.jpg *.jpeg *.webp *.bmp)"
            src_path, _ = QFileDialog.getOpenFileName(
                self, "Select Image to Resize", "", src_filter
            )
            if not src_path:
                return
                
            # Get output file
            default_out = os.path.splitext(src_path)[0] + f"_{width}x{height}" + os.path.splitext(src_path)[1]
            tgt_path, _ = QFileDialog.getSaveFileName(
                self, "Save Resized Image", default_out, src_filter
            )
            if not tgt_path:
                return
                
            # Convert
            success = resize_image(src_path, tgt_path, width, height)
            
            if success:
                self._search.setText("")
                msg_html = f"Successfully resized image to <strong>{width}x{height}</strong>!<br><br>Saved to: <a href='file:///{tgt_path.replace(' ', '%20')}'>{tgt_path}</a>"
                self._show_chat_result(html=msg_html)
            else:
                msg_html = f"Failed to resize image to <strong>{width}x{height}</strong>."
                self._show_chat_result(html=msg_html)
                
        finally:
            self._dialog_open = False


    def _save_bookmark(self, query: str):
        # Allow pasting the url manually: e.g. "save https://youtube.com/..."
        url = None
        parts = query.split(maxsplit=1)
        if len(parts) > 1 and (parts[1].startswith("http") or "://" in parts[1]):
            url = parts[1].strip()
            
        # Fallback to the active tab if they didn't paste a URL
        if not url:
            url = self._active_tab_url
            
        if not url:
            self._show_chat_result(text="Could not detect an active browser tab to save. Try copying the link and typing `save <url>`.")
            return
            
        import core.bookmarks as bm
        bm.save_bookmark(url)
        self._show_chat_result(text=f"✓ Saved to watch later:\n`{url}`")
        self._set_badge("SAVED")

    def _launch_bookmark(self, url: str):
        if not url:
            return
        import webbrowser
        webbrowser.open(url)
        self.hide_overlay()

    def _on_delete_pressed(self):
        item = self._results.get_selected_item()
        if not item:
            return
        if item.kind == ResultKind.BOOKMARK:
            url = item.action_data.get("url")
            if url:
                import core.bookmarks as bm
                bm.remove_bookmark(url)
                self._show_bookmarks()
        elif item.kind == ResultKind.NOTE:
            note_id = item.action_data.get("id")
            if note_id:
                self._delete_note(note_id)

    def _show_calc_result(self, expr: str, res: str):
        ri = ResultItem(kind=ResultKind.CALC, title=res, raw_text=expr)
        self._results.show_results([ri])

    def _show_sys_control_preview(self, query: str, intent: str):
        action_name = query.title()
        desc = "Press Enter to execute this command."
        ri = ResultItem(kind=ResultKind.ACTION, title=f"Execute: {action_name}", raw_text=desc, action_data={"action": query})
        self._results.show_results([ri])

    def _show_convert_preview(self, query: str):
        import re
        from core.converter import convert
        # Try to parse "amount source to target"
        match = re.match(r"^([\d.,]+)\s+([a-zA-Z]+)\s+to\s+([a-zA-Z]+)", query, re.IGNORECASE)
        if match:
            amount = float(match.group(1).replace(",", ""))
            source = match.group(2)
            target = match.group(3)
            res = convert(amount, source, target)
            if res:
                ri = ResultItem(kind=ResultKind.CONVERT, title=res, raw_text=f"{amount} {source} = {res}")
                self._results.show_results([ri])
                return
        
        # Or parse "convert amount source to target"
        match = re.match(r"^convert\s+([\d.,]+)\s+([a-zA-Z]+)\s+(?:to|into)\s+([a-zA-Z]+)", query, re.IGNORECASE)
        if match:
            amount = float(match.group(1).replace(",", ""))
            source = match.group(2)
            target = match.group(3)
            res = convert(amount, source, target)
            if res:
                ri = ResultItem(kind=ResultKind.CONVERT, title=res, raw_text=f"{amount} {source} = {res}")
                self._results.show_results([ri])
                return
                
        self._results.clear()

    def _show_file_search_preview(self, query: str):
        from core.file_search import search_files
        search_term = query.lower().replace("find ", "").replace("search ", "").strip()
        if len(search_term) < 2:
            self._results.clear()
            return
            
        files = search_files(search_term, limit=6)
        items = []
        for f in files:
            import os
            name = os.path.basename(f)
            items.append(ResultItem(kind=ResultKind.FILE, title=name, raw_text=f, action_data={"path": f}))
            
        if items:
            self._results.show_results(items)
        else:
            self._results.clear()

    def _run_sys_control(self, query: str):
        from core.system_controls import execute_sys_control
        res = execute_sys_control(query)
        self._show_chat_result(text=res, html="")
        
    def _run_file_search(self, query: str):
        # We already preview it, if they hit enter on a file, it should open it.
        # This is handled by _on_item_activated
        pass
        
    def _run_reminder(self, query: str):
        from core.reminders import schedule_reminder
        import re
        match = re.match(r"^(?:remind me in|remind in)\s+(\d+\s*[a-z]+)\s+(.+)", query, re.IGNORECASE)
        if match:
            res = schedule_reminder(match.group(1), match.group(2))
        else:
            match = re.match(r"^(?:(?:add|save|create)?\s*note:?)\s+(.+)", query, re.IGNORECASE)
            if match:
                import core.notes as notes
                res = notes.save_note(match.group(1))
            else:
                res = "Could not parse reminder or note format."
        self._show_chat_result(text=res, html="")

    def _show_chat_result(self, html: str = "", text: str = "", action_data: dict = None):
        self._results.stop_border_scan()
        if action_data is None:
            action_data = {}
        # Ensure show_followup is true by default unless specified
        if "show_followup" not in action_data:
            action_data["show_followup"] = True
            
        ri = ResultItem(
            kind=ResultKind.CHAT,
            title="",
            raw_text=text,
            html=html,
            action_data=action_data
        )
        self._divider.show()
        self._results.show_results([ri])
        self._relayout()

    def _show_yt_formats(self, formats: list):
        url = getattr(self, "_pending_yt_url", "")
        print(f"[YT] done signal received, showing {len(formats)} formats for {url}")
        items = []
        
        # Group formats by category
        from collections import defaultdict
        grouped = defaultdict(list)
        for f in formats:
            grouped[f.get("category", "Other")].append(f)
            
        # Define display order
        order = ["Video + Audio (HQ Muxed)", "Video + Audio", "Video Only", "Audio Only", "Images", "Other"]
        
        for cat in order:
            if cat not in grouped or not grouped[cat]:
                continue
                
            # Add section header
            items.append(ResultItem(
                kind=ResultKind.YT_FORMAT,
                title=f"━━ {cat.upper()} ━━",
                selectable=False
            ))
            
            # Add items for this section
            for i, f in enumerate(grouped[cat], 1):
                ri = ResultItem(
                    kind=ResultKind.YT_FORMAT,
                    title=f"   {f['note']}",
                    action_data={"url": url, "format_id": f["format_id"]},
                )
                items.append(ri)
                
        badge_text = "INSTAGRAM" if "instagram.com" in url else "YOUTUBE"
        self._set_badge(badge_text)
        self._divider.show()
        self._results.show_results(items)
        self._relayout()

    def _set_badge(self, text: str):
        """Show a monochromatic intent badge (no garish colors)."""
        self._badge.setText(text)
        self._badge.setStyleSheet(
            "background: rgba(255,255,255,0.06); "
            "color: rgba(255,255,255,0.40); "
            "border: 1px solid rgba(255,255,255,0.10); "
            "border-radius: 8px; "
            "font-size: 9px; font-weight: 700; "
            "letter-spacing: 0.5px; padding: 2px 8px;"
        )
        self._badge.show()

    def _relayout(self):
        self._card.adjustSize()
        self.adjustSize()
        self.update()   # trigger paintEvent to redraw card at new size

    # ─────────────────────────────────────────────────────────────────────
    # Background task launchers
    # ─────────────────────────────────────────────────────────────────────



    def _on_agent_finished(self, query: str, state: dict):
        if getattr(self, "_current_agent_query", "") != query:
            log.info("Query mismatch! expected %s got %s", getattr(self, "_current_agent_query", ""), query)
            return

        self._results.stop_border_scan()
        result = state.get("result", "")
        
        # Intercept tool actions
        if state.get("tool_output"):
            ui_data = state["tool_output"]
            if ui_data.get("ui_action") == "image_convert":
                params = ui_data.get("params", {})
                self._run_image_convert_explicit(params.get("src", "png"), params.get("tgt", "jpg"))
                return
            elif ui_data.get("ui_action") == "image_resize":
                params = ui_data.get("params", {})
                self._run_image_resize_explicit(params.get("width", 0), params.get("height", 0))
                return
            elif ui_data.get("ui_action") == "yt_download":
                self._run_yt_list(ui_data.get("params", {}).get("query", ""))
                return

        intent = state.get("intent", "chat")
        msgs   = state.get("messages", [])
        is_first = True
        if msgs:
            from langchain_core.messages import HumanMessage, AIMessage
            display_msgs = [m for m in msgs if isinstance(m, (HumanMessage, AIMessage))]
            is_first = len(display_msgs) <= 2
            
            self._conversation_messages = msgs
            history_html = self._format_chat_history_html(msgs)
            if history_html:
                result = ""
                html_result = history_html
            else:
                html_result = ""
        else:
            html_result = ""

        if intent == "page_analyze":
            ri = ResultItem(kind=ResultKind.PAGE, title="", raw_text=result, html=html_result, action_data={"scroll_to_bottom": not is_first})
            self._divider.show()
            self._results.show_results([ri])
            
            # Hide scanner overlay if it exists
            if hasattr(self, "_scanner_overlay") and self._scanner_overlay:
                self._scanner_overlay.close()
                self._scanner_overlay = None
            
            # Show ourselves again
            self.setWindowOpacity(1.0)
            self.show()
            self.raise_()
            self.activateWindow()
        elif intent in ("app_launch", "calc"):
            self._show_chat_result(html=html_result, text=result, action_data={"scroll_to_bottom": not is_first})
        else:
            self._show_chat_result(html=html_result, text=result, action_data={"scroll_to_bottom": not is_first})

        self._relayout()

    def _format_chat_history_html(self, msgs: list) -> str:
        from langchain_core.messages import HumanMessage, AIMessage
        import markdown
        
        display_msgs = [m for m in msgs if isinstance(m, (HumanMessage, AIMessage))]
        display_msgs = display_msgs[-10:]
        
        formatted = []
        for m in display_msgs:
            if isinstance(m, HumanMessage):
                html_content = markdown.markdown(m.content, extensions=["fenced_code", "tables", "nl2br"])
                bubble = f'''
                <div style="margin: 8px 0; margin-left: 40px; text-align: right;">
                    <div style="color: rgba(255,255,255,0.5); font-size: 11px; margin: 0; padding: 0;">You</div>
                    {html_content}
                </div>
                '''
                formatted.append(bubble)
            elif isinstance(m, AIMessage):
                content = m.content
                if isinstance(content, list):
                    # Extract text from content blocks if it's a list
                    text_parts = []
                    for block in content:
                        if isinstance(block, str):
                            text_parts.append(block)
                        elif isinstance(block, dict) and "text" in block:
                            text_parts.append(block["text"])
                    content = " ".join(text_parts)
                elif not isinstance(content, str):
                    content = str(content or "")
                
                if not content.strip() and getattr(m, "tool_calls", None):
                    continue
                if content.startswith("[Vision Analysis of User's Screen]:\n"):
                    content = content.replace("[Vision Analysis of User's Screen]:\n", "*(Analyzed screen)*\n\n", 1)
                
                html_content = markdown.markdown(content, extensions=["fenced_code", "tables", "nl2br"])
                bubble = f'''
                <div style="margin: 8px 0; margin-right: 40px; text-align: left;">
                    <div style="color: rgba(255,255,255,0.5); font-size: 11px; margin: 0; padding: 0;">Scenoxis</div>
                    {html_content}
                </div>
                '''
                formatted.append(bubble)
                
        return "".join(formatted)

    def _on_agent_error(self, query: str, msg: str):
        if getattr(self, "_current_agent_query", "") != query:
            return

        self._results.stop_border_scan()
        self._show_chat_result(text=f"⚠ Error: {msg}", html="")
        
        # Hide scanner overlay if it exists
        if hasattr(self, "_scanner_overlay") and self._scanner_overlay:
            self._scanner_overlay.close()
            self._scanner_overlay = None
            
        # Show ourselves again
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        self.activateWindow()
        self._relayout()

    def _run_page_analysis(self, query: str):
        # Hide the main window immediately
        self.hide()
        
        # Give Windows a moment to repaint the desktop/windows behind us
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, lambda: self._do_capture_and_scan(query))
        
    def _do_capture_and_scan(self, query: str):
        # Take the screenshot while we are hidden
        from agent.tools.page_analyzer import _capture_screen_pil
        image_bytes = _capture_screen_pil()
        
        # Now show the full screen scanner animation
        from ui.scanner_overlay import ScannerOverlay
        self._scanner_overlay = ScannerOverlay()
        self._scanner_overlay.show()
        
        # Update our own UI (ready for when we come back)
        self._results.show_thinking()
        self._set_badge("VISION")
        self._divider.show()
        self._relayout()
        
        # Run the agent with the captured bytes
        self._run_agent(query, image_bytes=image_bytes)

    def _run_agent(self, query: str, image_bytes: bytes = None):
        # Instead of killing the blocked thread, just keep it alive so it doesn't GC crash
        worker = AgentWorker(query, active_tab_url=self._active_tab_url, messages=self._conversation_messages, image_bytes=image_bytes)
        thread = QThread()
        worker.moveToThread(thread)
        
        # Keep references to prevent garbage collection!
        if not hasattr(self, "_active_workers"):
            self._active_workers = []
        if not hasattr(self, "_active_threads"):
            self._active_threads = []
            
        self._active_workers.append(worker)
        self._active_threads.append(thread)
        
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_agent_finished)
        worker.error.connect(self._on_agent_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        
        # Cleanup references when done
        def cleanup(*args):
            if worker in getattr(self, "_active_workers", []):
                self._active_workers.remove(worker)
            if thread in getattr(self, "_active_threads", []):
                self._active_threads.remove(thread)
                
        worker.finished.connect(cleanup)
        worker.error.connect(cleanup)
        
        thread.start()

    def _run_yt_list(self, query: str):
        print(f"[YT] _run_yt_list called with query: {query!r}")
        try:
            from agent.tools.yt_downloader import extract_yt_url
        except ImportError as exc:
            print(f"[YT] IMPORT ERROR: {exc}")
            self._on_yt_error(str(exc))
            return
            
        url = extract_yt_url(query)
        if not url and self._active_tab_url:
            url = self._active_tab_url
            
        # Optional: just do a very loose check to avoid sending Google searches to yt-dlp
        if not url or ("youtube.com" not in url and "youtu.be" not in url and "instagram.com" not in url):
            self._on_yt_error("Could not find a valid YouTube or Instagram URL in your command or active browser tab.")
            return
            
        print(f"[YT] Extracted URL: {url}")
        self._pending_yt_url = url
        self._results.show_thinking()
        
        badge_text = "INSTAGRAM" if "instagram.com" in url else "YOUTUBE"
        self._set_badge(badge_text)
        self._divider.show()
        self._relayout()

        worker = YTListWorker(url)
        thread = QThread()
        worker.moveToThread(thread)
        
        # PREVENT GARBAGE COLLECTION! PySide6 will destroy local objects when the function returns
        if not hasattr(self, "_active_workers"):
            self._active_workers = []
        self._active_workers.append(worker)
        
        thread.started.connect(worker.run)
        worker.done.connect(self._show_yt_formats)
        worker.error.connect(self._on_yt_error)
        
        def _cleanup():
            if worker in getattr(self, "_active_workers", []):
                self._active_workers.remove(worker)
            thread.quit()
            
        worker.done.connect(_cleanup)
        worker.error.connect(_cleanup)
        
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(worker.deleteLater)
        self._active_threads.append(thread)
        print(f"[YT] Starting worker thread...")
        thread.start()
        print(f"[YT] Worker thread started")

    def _on_yt_error(self, msg: str):
        """Handle YT-specific errors (single-arg signal)."""
        print(f"[YT] error signal received: {msg}")
        self._results.stop_border_scan()
        self._show_chat_result(text=f"⚠ YouTube error: {msg}", html="")
        self._relayout()

    def _on_yt_folder_change(self):
        from PySide6.QtWidgets import QFileDialog
        import time
        
        self._is_dialog_open = True
        try:
            out_dir = QFileDialog.getExistingDirectory(self, "Select Download Folder", self._results._yt_download_dir)
            if out_dir:
                self._results._yt_download_dir = out_dir
        finally:
            self._hiding = False
            self.setWindowOpacity(1.0)
            self.show()
            self.raise_()
            self.activateWindow()
            self._disable_deactivate_until = time.time() + 1.5

    def _start_yt_download(self, url: str, format_id: str, out_dir: str):
        self._results.show_download_progress_mode()
        self._relayout()
            
        worker = YTDownloadWorker(url, format_id, out_dir)
        thread = QThread()
        worker.moveToThread(thread)
        
        # PREVENT GARBAGE COLLECTION!
        if not hasattr(self, "_active_workers"):
            self._active_workers = []
        self._active_workers.append(worker)
        
        thread.started.connect(worker.run)
        worker.progress.connect(self._results.update_download_progress)
        worker.finished.connect(self._on_yt_download_finished)
        worker.error.connect(self._on_yt_error)
        
        def _cleanup():
            if worker in getattr(self, "_active_workers", []):
                self._active_workers.remove(worker)
            thread.quit()
            
        worker.finished.connect(_cleanup)
        worker.error.connect(_cleanup)
        
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_yt_download_finished(self, result: dict):
        if result.get("success"):
            path = result.get("filepath", "")
            self._show_chat_result(text=f"✓ Download complete:\n`{path}`", action_data={"show_followup": False})
        else:
            self._show_chat_result(text=f"✗ Download failed: {result.get('error')}", action_data={"show_followup": False})
        self._relayout()

    def _launch_exe(self, exe_path: str):
        if not exe_path:
            return
        try:
            import os
            # Use os.startfile instead of subprocess so console apps (cmd, powershell) get a visible window
            os.startfile(exe_path)
        except Exception as exc:
            log.error("Launch failed: %s", exc)
        self.hide_overlay()

    def _launch_file(self, file_path: str):
        if not file_path:
            return
        log.info("Launching file: %s", file_path)
        try:
            import os
            os.startfile(file_path)
        except Exception as exc:
            log.error("Launch failed: %s", exc)
        self.hide_overlay()

    # ─────────────────────────────────────────────────────────────────────
    # Lose focus → hide
    # ─────────────────────────────────────────────────────────────────────

    def changeEvent(self, event):
        super().changeEvent(event)
        from PySide6.QtCore import QEvent, QTimer
        if event.type() == QEvent.Type.WindowDeactivate:
            # Small delay so clicks on results don't trigger hide
            QTimer.singleShot(100, self._check_deactivate)
        elif event.type() == QEvent.Type.WindowActivate:
            self._is_dialog_open = False

    def _check_deactivate(self):
        import time
        if getattr(self, "_is_dialog_open", False):
            return
        if time.time() < getattr(self, "_disable_deactivate_until", 0):
            return
        if not self.isActiveWindow() and self.isVisible():
            self.hide_overlay()
