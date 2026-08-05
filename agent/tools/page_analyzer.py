"""
agent/tools/page_analyzer.py
Captures the active window / full screen and sends it to Groq's vision model
for analysis. Uses Windows Graphics Capture API via ctypes where available,
falls back to PIL/mss screen capture.
"""
import logging
import base64
import io
import os
from langchain_core.tools import tool

log = logging.getLogger(__name__)


def _capture_screen_pil() -> bytes | None:
    """Fallback: capture full primary screen using PIL ImageGrab."""
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as exc:
        log.error("PIL screen capture failed: %s", exc)
        return None


def _capture_active_window() -> bytes | None:
    """
    Attempt to capture just the foreground window using PrintWindow,
    falling back to full-screen grab.
    """
    try:
        import ctypes
        import ctypes.wintypes
        from PIL import Image

        user32  = ctypes.windll.user32
        gdi32   = ctypes.windll.gdi32

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return _capture_screen_pil()

        # Get window rect
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        width  = rect.right  - rect.left
        height = rect.bottom - rect.top

        if width <= 0 or height <= 0:
            return _capture_screen_pil()

        # Use PrintWindow to capture the window even if partially off-screen
        hwnd_dc   = user32.GetWindowDC(hwnd)
        mem_dc    = gdi32.CreateCompatibleDC(hwnd_dc)
        bitmap    = gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
        gdi32.SelectObject(mem_dc, bitmap)

        # PW_RENDERFULLCONTENT = 0x2 (captures layered/DX windows on Win10+)
        user32.PrintWindow(hwnd, mem_dc, 0x2)

        # Extract pixels via GetDIBits
        import ctypes
        class BITMAPINFOHEADER(ctypes.Structure):
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

        bmi = BITMAPINFOHEADER()
        bmi.biSize      = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth     = width
        bmi.biHeight    = -height  # top-down
        bmi.biPlanes    = 1
        bmi.biBitCount  = 32
        bmi.biCompression = 0  # BI_RGB

        buf_size = width * height * 4
        pixel_buf = (ctypes.c_byte * buf_size)()
        gdi32.GetDIBits(mem_dc, bitmap, 0, height, pixel_buf, ctypes.byref(bmi), 0)

        img = Image.frombuffer("RGBA", (width, height), bytes(pixel_buf), "raw", "BGRA", 0, 1)
        img = img.convert("RGB")

        # Resize for Groq vision: keep under 1024px on longest side
        max_dim = 1024
        if max(img.width, img.height) > max_dim:
            ratio = max_dim / max(img.width, img.height)
            img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="PNG")

        # Cleanup GDI objects
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(hwnd, hwnd_dc)

        return buf.getvalue()

    except Exception as exc:
        log.warning("PrintWindow capture failed (%s), falling back to PIL", exc)
        return _capture_screen_pil()


def _call_groq_vision(image_bytes: bytes, prompt: str) -> str:
    """Send image to Groq vision model and return the text response."""
    try:
        from groq import Groq
        from core.config import get_api_key
        api_key = get_api_key("GROQ")
        if not api_key:
            return "GROQ_API_KEY not set."

        import yaml, pathlib
        prompt_file = pathlib.Path("prompts/vision_analysis.yaml")
        system_prompt = "Describe what is shown on the screen in detail."
        if prompt_file.exists():
            data = yaml.safe_load(prompt_file.read_text(encoding="utf-8"))
            system_prompt = data.get("system_prompt", system_prompt)
            
        import datetime
        current_time_str = datetime.datetime.now().strftime("%A, %B %d, %Y %I:%M %p")
        system_prompt += f"\n\nCurrent system time: {current_time_str}"

        client = Groq(api_key=api_key, timeout=15.0, max_retries=0)
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        response = client.chat.completions.create(
            model="qwen/qwen3.6-27b",
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                        {"type": "text", "text": prompt or "Describe this screen."},
                    ],
                },
            ],
            max_tokens=4096,
        )
        return response.choices[0].message.content or "No description returned."

    except Exception as exc:
        log.error("Groq vision call failed: %s", exc)
        return f"Vision analysis failed: {exc}"


@tool
def analyze_current_page(instruction: str = "") -> str:
    """
    Capture the currently active window or screen and analyse it using
    Groq's vision model. Optionally accepts a specific instruction
    (e.g. 'What errors are shown?', 'Summarise this article').
    Returns a detailed text description of what is on screen.
    """
    log.info("Capturing screen for analysis…")
    image_bytes = _capture_active_window()
    if not image_bytes:
        return "Screen capture failed — could not obtain image data."

    prompt = instruction.strip() or "Describe what is shown on this screen in detail."
    return _call_groq_vision(image_bytes, prompt)


def capture_for_ui() -> bytes | None:
    """
    Public function for the UI to call directly (outside of LangGraph)
    to get the raw screenshot bytes — used to drive the border-scan animation.
    """
    return _capture_active_window()
