"""
core/hotkey.py
Global hotkey registration via Win32 RegisterHotKey.
Runs a hidden message pump on a daemon thread; fires a callback on the main
thread via a Qt signal so it's safe to call Qt methods from the callback.
"""
import ctypes
import ctypes.wintypes
import threading
import logging

log = logging.getLogger(__name__)

# Virtual-key codes
VK_SPACE = 0x20
VK_Z = 0x5A

# Modifier flags for RegisterHotKey
MOD_ALT        = 0x0001
MOD_NOREPEAT   = 0x4000

WM_HOTKEY = 0x0312
HOTKEY_ID = 1

_callback = None
_pump_thread: threading.Thread | None = None
_stop_event = threading.Event()
_hwnd: int | None = None


def _message_pump() -> None:
    """Hidden HWND message pump — runs on its own daemon thread."""
    global _hwnd

    user32 = ctypes.windll.user32
    user32.CreateWindowExW.restype = ctypes.wintypes.HWND
    user32.DispatchMessageW.argtypes = [ctypes.c_void_p]

    # Create a message-only window so we have an HWND to bind the hotkey to
    hwnd = user32.CreateWindowExW(
        0, "STATIC", "ScenoxisHotkey",
        0, 0, 0, 0, 0,
        ctypes.wintypes.HWND(-3),  # HWND_MESSAGE
        None, None, None,
    )
    _hwnd = hwnd

    ok = user32.RegisterHotKey(hwnd, HOTKEY_ID, MOD_ALT | MOD_NOREPEAT, VK_SPACE)
    if not ok:
        err = ctypes.GetLastError()
        log.warning("RegisterHotKey Alt+Space failed (error %d). Falling back to Alt+Z.", err)
        ok = user32.RegisterHotKey(hwnd, HOTKEY_ID, MOD_ALT | MOD_NOREPEAT, VK_Z)
        if not ok:
            log.error("RegisterHotKey Alt+Z failed as well (error %d).", ctypes.GetLastError())
            return
        log.info("Global hotkey Alt+Z registered (HWND=%s)", hwnd)
    else:
        log.info("Global hotkey Alt+Space registered (HWND=%s)", hwnd)

    msg = ctypes.wintypes.MSG()
    while not _stop_event.is_set():
        # PeekMessage with a short timeout so we can check _stop_event
        result = user32.PeekMessageW(
            ctypes.byref(msg), hwnd, 0, 0,
            0x0001,  # PM_REMOVE
        )
        if result:
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                if _callback:
                    try:
                        _callback()
                    except Exception:
                        log.exception("Hotkey callback raised an exception")
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        else:
            _stop_event.wait(timeout=0.01)

    user32.UnregisterHotKey(hwnd, HOTKEY_ID)
    user32.DestroyWindow(hwnd)
    log.info("Global hotkey unregistered")


def register(callback) -> bool:
    """
    Start the Win32 hotkey listener.

    Args:
        callback: Callable invoked (on the pump thread) when Alt+Space fires.
                  Must be thread-safe — use Qt signals, not direct Qt calls.

    Returns:
        True if the pump thread started successfully.
    """
    global _callback, _pump_thread
    _callback = callback
    _stop_event.clear()
    _pump_thread = threading.Thread(target=_message_pump, daemon=True, name="HotkeyPump")
    _pump_thread.start()
    return True


def unregister() -> None:
    """Stop the hotkey pump thread."""
    _stop_event.set()
    if _pump_thread:
        _pump_thread.join(timeout=1.0)
