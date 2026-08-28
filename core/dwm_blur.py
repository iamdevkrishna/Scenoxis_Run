"""
core/dwm_blur.py
Apply Windows Acrylic/blur-behind effect to a Qt window via ctypes DWM APIs.
Falls back gracefully on older Windows versions.

KEY INSIGHT: Do NOT call DwmExtendFrameIntoClientArea — it fills the entire
rectangular HWND with an opaque glass frame, creating visible black corners
when the paintEvent clips to a rounded rect. Instead, rely purely on
WA_TranslucentBackground + WCA Acrylic for proper transparency.
"""
import ctypes
import ctypes.wintypes
import logging
import sys

log = logging.getLogger(__name__)

WCA_ACCENT_POLICY = 19
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
ACCENT_ENABLE_BLURBEHIND = 3
ACCENT_DISABLED = 0


class _ACCENT_POLICY(ctypes.Structure):
    _fields_ = [
        ("AccentState",   ctypes.c_uint),
        ("AccentFlags",   ctypes.c_uint),
        ("GradientColor", ctypes.c_uint),   # AABBGGRR
        ("AnimationId",   ctypes.c_uint),
    ]


class _WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
    _fields_ = [
        ("Attribute",  ctypes.c_int),
        ("Data",       ctypes.POINTER(_ACCENT_POLICY)),
        ("SizeOfData", ctypes.c_size_t),
    ]


def _setup_set_wca():
    try:
        user32 = ctypes.windll.user32
        fn = getattr(user32, "SetWindowCompositionAttribute", None)
        if fn is None:
            return None
        fn.argtypes = [
            ctypes.wintypes.HWND,
            ctypes.POINTER(_WINDOWCOMPOSITIONATTRIBDATA),
        ]
        fn.restype = ctypes.wintypes.BOOL
        return fn
    except Exception as exc:
        log.debug("SetWindowCompositionAttribute not available: %s", exc)
        return None


_set_wca = None
_set_wca_checked = False


def _get_set_wca():
    global _set_wca, _set_wca_checked
    if not _set_wca_checked:
        _set_wca = _setup_set_wca()
        _set_wca_checked = True
    return _set_wca


def apply_blur(hwnd: int, dark_mode: bool = True, tint_color: int = 0x01000000) -> bool:
    """
    Apply Windows 10/11 Acrylic blur to the given HWND.

    Uses SetWindowCompositionAttribute (WCA) with ACCENT_ENABLE_ACRYLICBLURBEHIND.
    On Windows 11+, also sets DWMWA_WINDOW_CORNER_PREFERENCE to natively round
    the window corners at the compositor level, eliminating black corner artifacts.
    """
    if sys.platform != "win32":
        return False

    dwmapi = ctypes.windll.dwmapi

    # ── Enable dark mode ──────────────────────────────────────────────────
    try:
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        dark = ctypes.c_int(1 if dark_mode else 0)
        dwmapi.DwmSetWindowAttribute(
            ctypes.wintypes.HWND(hwnd),
            ctypes.wintypes.DWORD(DWMWA_USE_IMMERSIVE_DARK_MODE),
            ctypes.byref(dark),
            ctypes.wintypes.DWORD(ctypes.sizeof(dark)),
        )
    except Exception:
        pass

    # ── Windows 11: native DWM rounded corners ────────────────────────────
    try:
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_ROUND = 2  # native rounded corners
        corner_pref = ctypes.c_int(DWMWCP_ROUND)
        dwmapi.DwmSetWindowAttribute(
            ctypes.wintypes.HWND(hwnd),
            ctypes.wintypes.DWORD(DWMWA_WINDOW_CORNER_PREFERENCE),
            ctypes.byref(corner_pref),
            ctypes.wintypes.DWORD(ctypes.sizeof(corner_pref)),
        )
        log.debug("DWM native rounded corners applied to HWND=%s", hwnd)
    except Exception as exc:
        log.debug("DWM corner rounding not available (Win10?): %s", exc)

    # ── Apply Windows 11 System Backdrop (Mica/Acrylic) ───────────────────
    try:
        DWMWA_SYSTEMBACKDROP_TYPE = 38
        DWMSBT_TRANSIENTWINDOW = 3  # Acrylic
        
        # 1. Extend frame into client area so backdrop covers everything
        class MARGINS(ctypes.Structure):
            _fields_ = [("cxLeftWidth", ctypes.c_int),
                        ("cxRightWidth", ctypes.c_int),
                        ("cyTopHeight", ctypes.c_int),
                        ("cyBottomHeight", ctypes.c_int)]
        margins = MARGINS(-1, -1, -1, -1)
        dwmapi.DwmExtendFrameIntoClientArea(ctypes.wintypes.HWND(hwnd), ctypes.byref(margins))

        # 2. Set Backdrop type to Acrylic
        backdrop_type = ctypes.c_int(DWMSBT_TRANSIENTWINDOW)
        res = dwmapi.DwmSetWindowAttribute(
            ctypes.wintypes.HWND(hwnd),
            ctypes.wintypes.DWORD(DWMWA_SYSTEMBACKDROP_TYPE),
            ctypes.byref(backdrop_type),
            ctypes.wintypes.DWORD(ctypes.sizeof(backdrop_type)),
        )
        
        # 3. Remove the standard Windows 11 outline border
        try:
            DWMWA_BORDER_COLOR = 34
            DWMWA_COLOR_NONE = 0xFFFFFFFE
            border_color = ctypes.c_uint(DWMWA_COLOR_NONE)
            dwmapi.DwmSetWindowAttribute(
                ctypes.wintypes.HWND(hwnd),
                ctypes.wintypes.DWORD(DWMWA_BORDER_COLOR),
                ctypes.byref(border_color),
                ctypes.wintypes.DWORD(ctypes.sizeof(border_color)),
            )
        except Exception as e:
            log.debug("DWM attribute setting failed: %s", e)

        if res == 0:
            log.debug("DWM System Backdrop applied to HWND=%s", hwnd)
            return True
    except Exception as exc:
        log.debug("DWM System Backdrop failed: %s", exc)

    # ── Fallback to WCA Acrylic ───────────────────────────────────────────
    try:
        fn = _get_set_wca()
        if fn is not None:
            accent = _ACCENT_POLICY()
            accent.AccentState   = ACCENT_ENABLE_BLURBEHIND
            accent.AccentFlags   = 2
            accent.GradientColor = tint_color  # AABBGGRR
            accent.AnimationId   = 0

            data = _WINDOWCOMPOSITIONATTRIBDATA()
            data.Attribute  = WCA_ACCENT_POLICY
            data.Data       = ctypes.cast(
                ctypes.pointer(accent), ctypes.POINTER(_ACCENT_POLICY)
            )
            data.SizeOfData = ctypes.sizeof(accent)

            res = fn(ctypes.wintypes.HWND(hwnd), ctypes.byref(data))
            if res:
                log.debug("WCA Acrylic applied to HWND=%s", hwnd)
                return True
    except Exception as exc:
        log.debug("WCA Acrylic failed: %s", exc)

    return False


def remove_blur(hwnd: int) -> None:
    try:
        fn = _get_set_wca()
        if fn is not None:
            accent = _ACCENT_POLICY()
            accent.AccentState = ACCENT_DISABLED
            data = _WINDOWCOMPOSITIONATTRIBDATA()
            data.Attribute  = WCA_ACCENT_POLICY
            data.Data       = ctypes.pointer(accent)
            data.SizeOfData = ctypes.sizeof(accent)
            fn(ctypes.wintypes.HWND(hwnd), ctypes.byref(data))
    except Exception as exc:
        log.debug("remove_blur failed: %s", exc)
