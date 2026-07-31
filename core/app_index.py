"""
core/app_index.py
Scans Windows Start Menu and Desktop for application shortcuts (.lnk files),
resolves their targets via pywin32, and builds an in-memory index.
Provides fuzzy name matching via rapidfuzz.
"""
import os
import re
import time
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import win32com.client
from rapidfuzz import fuzz

log = logging.getLogger(__name__)

# Directories to scan
SCAN_ROOTS = [
    os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
    os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs"),
    os.path.expandvars(r"%USERPROFILE%\Desktop"),
    os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Desktop"),
]

FUZZY_THRESHOLD = 50      # minimum rapidfuzz score (0-100) — lowered for better recall
MAX_RESULTS     = 7       # max items shown in the results panel
REFRESH_INTERVAL = 300    # seconds between background re-scans

# Always-available Windows built-in apps (no Start Menu shortcut on modern Windows)
_SYSTEM32 = os.path.expandvars(r"%SystemRoot%\System32")
_WIN      = os.path.expandvars(r"%SystemRoot%")
_PFILES   = os.path.expandvars(r"%ProgramFiles%")
_PFILES86 = os.path.expandvars(r"%ProgramFiles(x86)%")

SYSTEM_APPS: list[tuple[str, str]] = [
    ("Notepad",          rf"{_SYSTEM32}\notepad.exe"),
    ("Calculator",       rf"{_SYSTEM32}\calc.exe"),
    ("Paint",            rf"{_SYSTEM32}\mspaint.exe"),
    ("Task Manager",     rf"{_SYSTEM32}\Taskmgr.exe"),
    ("File Explorer",    rf"{_WIN}\explorer.exe"),
    ("Command Prompt",   rf"{_SYSTEM32}\cmd.exe"),
    ("PowerShell",       rf"{_SYSTEM32}\WindowsPowerShell\v1.0\powershell.exe"),
    ("Registry Editor",  rf"{_WIN}\regedit.exe"),
    ("Snipping Tool",    rf"{_SYSTEM32}\SnippingTool.exe"),
    ("Character Map",    rf"{_SYSTEM32}\charmap.exe"),
    ("Magnifier",        rf"{_SYSTEM32}\Magnify.exe"),
    ("WordPad",          rf"{_PFILES}\Windows NT\Accessories\wordpad.exe"),
    ("Task Scheduler",   rf"{_SYSTEM32}\taskschd.msc"),
    ("On-Screen Keyboard", rf"{_SYSTEM32}\osk.exe"),
    ("Sticky Notes",     rf"{_SYSTEM32}\StikyNot.exe"),
    ("Remote Desktop",   rf"{_SYSTEM32}\mstsc.exe"),
    ("Disk Cleanup",     rf"{_SYSTEM32}\cleanmgr.exe"),
    ("Control Panel",    rf"{_SYSTEM32}\control.exe"),
    ("Device Manager",   rf"{_SYSTEM32}\devmgmt.msc"),
    ("Disk Management",  rf"{_SYSTEM32}\diskmgmt.msc"),
]


@dataclass
class AppEntry:
    name: str
    exe_path: str
    icon_path: Optional[str] = None
    lnk_path: Optional[str] = None
    score: float = field(default=0.0, repr=False)

    # Normalised name used for matching (lowercase, no punctuation)
    _norm: str = field(default="", init=False, repr=False)

    def __post_init__(self):
        self._norm = re.sub(r"[^a-z0-9 ]", "", self.name.lower()).strip()


class AppIndex:
    """Thread-safe in-memory index of installed applications."""

    def __init__(self):
        self._entries: list[AppEntry] = []
        self._lock = threading.RLock()
        self._shell = None   # COM shell object — created on scan thread
        self._timer: threading.Timer | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self) -> None:
        """Perform an initial synchronous scan on the calling thread."""
        self._scan()
        self._schedule_refresh()

    def search(self, query: str, limit: int = MAX_RESULTS) -> list[AppEntry]:
        """
        Search the app index with prefix-aware scoring.
        Names that start with the query are heavily boosted so that
        e.g. "notepad" always beats "OneNote" when typing "notepad".
        """
        if not query.strip():
            return []

        with self._lock:
            entries = list(self._entries)

        if not entries:
            return []

        norm_query = re.sub(r"[^a-z0-9 ]", "", query.lower()).strip()

        scored: list[tuple[int, int, AppEntry]] = []
        for i, e in enumerate(entries):
            name = e._norm
            
            # If the query is much longer than the app name, or if it contains spaces 
            # (e.g. a natural language chat query), WRatio is too lenient.
            if " " in norm_query or len(norm_query) > len(name) + 4:
                base = fuzz.QRatio(norm_query, name)
            else:
                base = fuzz.WRatio(norm_query, name)

            # Strong boost: name starts exactly with the query
            if name.startswith(norm_query):
                base = min(100, base + 40)
            # Moderate boost: query appears as a complete word inside name
            elif (f" {norm_query} " in f" {name} "):
                base = min(100, base + 20)

            if base >= FUZZY_THRESHOLD:
                scored.append((base, i, e))

        scored.sort(key=lambda x: (-x[0], x[1]))   # desc score, stable by original order
        results = []
        for base_score, _, e in scored[:limit]:
            e.score = base_score
            results.append(e)
        return results

    def get_entry(self, name: str) -> Optional[AppEntry]:
        """Return the single best-matching entry for an exact/near-exact name."""
        results = self.search(name, limit=1)
        return results[0] if results else None

    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    def stop(self) -> None:
        if self._timer:
            self._timer.cancel()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _scan(self) -> None:
        """Walk SCAN_ROOTS, resolve .lnk files, populate self._entries."""
        t0 = time.perf_counter()
        entries: list[AppEntry] = []

        # COM must be initialised on the thread that uses it
        try:
            import pythoncom
            pythoncom.CoInitialize()
            shell = win32com.client.Dispatch("WScript.Shell")
        except Exception as exc:
            log.warning("COM init failed: %s — falling back to name-only index", exc)
            shell = None

        for root in SCAN_ROOTS:
            if not os.path.isdir(root):
                continue
            for dirpath, _, filenames in os.walk(root):
                for fname in filenames:
                    lnk = os.path.join(dirpath, fname)
                    if fname.lower().endswith(".lnk"):
                        entry = self._parse_lnk(lnk, shell)
                        if entry:
                            entries.append(entry)

        # Scan UWP apps
        self._scan_uwp_apps(entries)

        # Seed with always-available system apps
        seen_sys: set[str] = set()
        for app_name, app_path in SYSTEM_APPS:
            norm_path = app_path.lower()
            if os.path.exists(app_path) and norm_path not in seen_sys:
                seen_sys.add(norm_path)
                entries.append(AppEntry(
                    name=app_name,
                    exe_path=app_path,
                    icon_path=app_path,
                ))

        if shell:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass

        # Deduplicate by exe_path, keep first occurrence
        seen: set[str] = set()
        unique: list[AppEntry] = []
        for e in entries:
            key = e.exe_path.lower()
            if key not in seen:
                seen.add(key)
                unique.append(e)

        with self._lock:
            self._entries = unique

        elapsed = time.perf_counter() - t0
        log.info("App index: %d entries in %.2fs", len(unique), elapsed)

    def _parse_lnk(self, lnk_path: str, shell) -> Optional[AppEntry]:
        """Resolve a .lnk shortcut to an AppEntry."""
        name = Path(lnk_path).stem
        exe_path = ""
        icon_path = None

        if shell:
            try:
                shortcut = shell.CreateShortCut(lnk_path)
                target = shortcut.TargetPath
                if target and target.lower().endswith(".exe"):
                    exe_path = target
                    icon_loc = shortcut.IconLocation
                    if icon_loc and "," in icon_loc:
                        icon_path = icon_loc.split(",")[0]
            except Exception:
                pass

        if not exe_path:
            return None  # skip non-executable shortcuts (folders, URLs, etc.)

        return AppEntry(
            name=name,
            exe_path=exe_path,
            icon_path=icon_path or exe_path,
            lnk_path=lnk_path,
        )

    def _scan_uwp_apps(self, entries: list[AppEntry]) -> None:
        """Fetch UWP (Windows Store) apps via PowerShell."""
        try:
            import subprocess
            import json
            # Fast PowerShell command to get installed apps and return JSON
            cmd = ['powershell', '-NoProfile', '-Command', 'Get-StartApps | Select-Object -Property Name, AppID | ConvertTo-Json -Compress']
            
            # Use CREATE_NO_WINDOW so a cmd box doesn't briefly flash on screen!
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            result = subprocess.run(cmd, capture_output=True, text=True, startupinfo=startupinfo, timeout=10.0)
            if result.returncode != 0 or not result.stdout.strip():
                return
                
            data = json.loads(result.stdout)
            if not isinstance(data, list):
                data = [data]
                
            for item in data:
                name = item.get("Name")
                appid = item.get("AppID")
                if name and appid:
                    exe_path = f"shell:AppsFolder\\{appid}"
                    entries.append(AppEntry(
                        name=name,
                        exe_path=exe_path,
                        icon_path=None
                    ))
        except Exception as exc:
            log.warning("UWP app scan failed: %s", exc)

    def _schedule_refresh(self) -> None:
        self._timer = threading.Timer(REFRESH_INTERVAL, self._background_refresh)
        self._timer.daemon = True
        self._timer.start()

    def _background_refresh(self) -> None:
        log.debug("App index background refresh")
        self._scan()
        self._schedule_refresh()


# Module-level singleton
_index: AppIndex | None = None


def get_index() -> AppIndex:
    global _index
    if _index is None:
        _index = AppIndex()
    return _index


def init() -> None:
    """Call once at startup (on a background thread is fine)."""
    get_index().build()
