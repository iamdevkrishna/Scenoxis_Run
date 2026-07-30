"""
main.py
Scenoxis Run — entry point.

Startup sequence:
  1. Load .env / configure logging
  2. Build QApplication, load stylesheet
  3. Create OverlayWindow (hidden)
  4. Kick off app index scan on a background thread
  5. Register Alt+Space global hotkey → calls window.hotkey_callback()
  6. Enter Qt event loop
"""
import logging
import os
import sys
import threading

from dotenv import load_dotenv

# ── Environment first ────────────────────────────────────────────────────────
load_dotenv()

# Workaround for corporate/proxy SSL certificate issues
import ssl
ssl._create_default_https_context = ssl._create_unverified_context
os.environ.setdefault("PYTHONHTTPSVERIFY", "0")

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("scenoxis")

# ── Qt ───────────────────────────────────────────────────────────────────────
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontDatabase, QFont

# Enable High-DPI scaling before creating QApplication
QApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
)

# ── Project imports ──────────────────────────────────────────────────────────
from ui.overlay_window import OverlayWindow
import core.hotkey as hotkey
import core.app_index as app_index


def _build_app_index():
    """Run on a daemon thread so startup is non-blocking."""
    log.info("Building app index…")
    app_index.init()
    log.info("App index ready — %d entries", app_index.get_index().count())

def _warm_memory_model():
    """Warm up the HuggingFace embeddings in the background so the first query is fast."""
    try:
        # Setting this env var stops HuggingFace from making dozens of HTTP HEAD requests
        os.environ["HF_HUB_OFFLINE"] = "1"
        from agent.memory import get_store
        # This will trigger _get_embeddings() and load the model into memory
        get_store()
    except Exception as exc:
        log.warning("Memory warmup failed (might be first run without cache): %s", exc)
        os.environ.pop("HF_HUB_OFFLINE", None)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Scenoxis Run")
    app.setApplicationVersion("0.1.0")
    app.setQuitOnLastWindowClosed(False)   # Stay resident when overlay is hidden

    # ── App icon (optional, graceful if missing) ──────────────────────────
    try:
        from PySide6.QtGui import QIcon
        icon = QIcon("assets/icon.png")
        if not icon.isNull():
            app.setWindowIcon(icon)
    except Exception:
        pass

    # ── Create overlay (hidden) ───────────────────────────────────────────
    window = OverlayWindow()
    window.hide()
    log.info("Overlay window created")

    # ── App index scan (background thread) ───────────────────────────────
    idx_thread = threading.Thread(target=_build_app_index, daemon=True, name="AppIndex")
    idx_thread.start()

    # ── Warm up memory models (background thread) ─────────────────────────
    mem_thread = threading.Thread(target=_warm_memory_model, daemon=True, name="MemoryWarmup")
    mem_thread.start()

    # ── Global hotkey ─────────────────────────────────────────────────────
    # The hotkey callback is called on the Win32 pump thread; it emits
    # window.toggle_visibility (a Qt signal) which is delivered safely
    # on the main thread via the event loop.
    registered = hotkey.register(window.hotkey_callback)
    if not registered:
        log.error("Failed to register Alt+Space hotkey")
    else:
        log.info("Alt+Space hotkey registered — press to open Scenoxis Run")

    # ── Optional: show window once on first launch ────────────────────────
    QTimer.singleShot(200, window.show_overlay)

    # ── Event loop ────────────────────────────────────────────────────────
    exit_code = app.exec()

    # Cleanup
    hotkey.unregister()
    app_index.get_index().stop()
    log.info("Scenoxis Run exited (code=%d)", exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
