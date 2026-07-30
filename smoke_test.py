"""
smoke_test.py
Quick offline verification that all modules import correctly and
the core fast-path logic works - no network, no Qt, no GPU required.
Run with: python smoke_test.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

print("== Smoke test for Scenoxis Run ==================================")

# 1. Calculator
print("\n[1] Calculator")
from core.calculator import is_arithmetic, calculate
assert is_arithmetic("2+2"),              "should detect arithmetic"
assert not is_arithmetic("open notepad"), "should not detect text as arithmetic"
assert not is_arithmetic("https://youtu.be/abc123"), "URL should not be arithmetic"
r = calculate("3 * (4 + 2)")
assert r["result"] == "18", f"expected 18, got {r['result']}"
r2 = calculate("100 / 4")
assert r2["result"] == "25", f"expected 25, got {r2['result']}"
print(f"   OK  3*(4+2) = {r['result']}")
print(f"   OK  100/4   = {r2['result']}")

# 2. Classifier (no app index needed for non-app intents)
print("\n[2] Classifier")
from agent.classifier import classify, classify_for_live_preview
assert classify("2+2*3")                         == "calc",         f"got {classify('2+2*3')}"
assert classify("https://youtu.be/dQw4w9WgXcQ") == "yt_download",  f"got {classify('https://youtu.be/dQw4w9WgXcQ')}"
assert classify("analyse the page")              == "page_analyze", f"got {classify('analyse the page')}"
assert classify("what is the meaning of life")   == "chat",         f"got {classify('what is the meaning of life')}"
print("   OK  calc / yt_download / page_analyze / chat all route correctly")

# 3. AgentState shape
print("\n[3] AgentState")
from agent.state import AgentState
s: AgentState = {"query": "hello", "intent": "chat", "result": "hi"}
assert s["query"] == "hello"
print("   OK  AgentState TypedDict is valid")

# 4. App index (scan, no COM required for basic import)
print("\n[4] App index import")
from core.app_index import AppIndex, AppEntry
e = AppEntry(name="Notepad", exe_path=r"C:\Windows\notepad.exe")
assert e._norm == "notepad"
print("   OK  AppEntry normalisation works")

# 5. DWM blur module loads
print("\n[5] DWM blur module")
from core.dwm_blur import apply_blur, remove_blur
print("   OK  dwm_blur imported (actual blur only applies to a live HWND)")

# 6. Hotkey module loads
print("\n[6] Hotkey module")
from core.hotkey import register, unregister
print("   OK  hotkey imported (registration deferred to runtime)")

# 7. Tool imports (no API calls)
print("\n[7] Tool imports")
from agent.tools.launch_app      import launch_app, launch_app_direct
from agent.tools.calculator_tool import calculate as calc_tool
from agent.tools.web_search      import web_search
from agent.tools.page_analyzer   import analyze_current_page, capture_for_ui
from agent.tools.yt_downloader   import download_youtube_video, extract_yt_url, list_formats
print("   OK  All @tool functions imported")

# 8. YT URL extraction
print("\n[8] YouTube URL extraction")
url = extract_yt_url("Check this out: https://youtu.be/dQw4w9WgXcQ")
assert url == "https://youtu.be/dQw4w9WgXcQ", f"Got: {url}"
print(f"   OK  Extracted: {url}")

print("\n== All smoke tests passed =======================================")


