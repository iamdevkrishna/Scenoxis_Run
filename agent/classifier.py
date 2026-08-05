"""
agent/classifier.py
Local intent classifier — pure Python, precompiled regex, in-memory lookups only.
Runs on every keystroke; MUST have zero disk/network I/O.
"""
import re
import logging
from typing import Optional

log = logging.getLogger(__name__)

# ── Arithmetic detection ────────────────────────────────────────────────────
# Imported from core.calculator to keep the regex in one place
from core.calculator import is_arithmetic

# ── Media URL detection (YouTube, Instagram) ────────────────────────────────
_MEDIA_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.|m\.)?(?:youtube\.com/watch\?.*v=|youtu\.be/|instagram\.com/(?:p|reel|reels|tv)/)[\w\-]+",
    re.IGNORECASE,
)

# ── Page analysis trigger phrases ───────────────────────────────────────────
_PAGE_PHRASES = re.compile(
    r"\b(?:analys[ei]s?|describe|explain|summarise?|summarize|what(?:'s| is|s) (?:on|this|going on)|look at|tell me what)[\s\w]*(?:page|screen|window|tab)?\b",
    re.IGNORECASE,
)

# ── Bookmarks ───────────────────────────────────────────────────────────────
_SAVE_BOOKMARK_RE = re.compile(r"^(?:save|watch later|bookmark)\b", re.IGNORECASE)
_VIEW_BOOKMARKS_RE = re.compile(r"^(?:saved|bookmarks)$", re.IGNORECASE)

# ── Converter ───────────────────────────────────────────────────────────────
_CONVERT_RE = re.compile(r"^convert\s+(.+?)\s+(?:to|into)\s+([a-z0-9]+)", re.IGNORECASE)

# ── Resizer ─────────────────────────────────────────────────────────────────
_RESIZE_RE = re.compile(r"^resize\s+(?:image\s+)?(?:to\s+)?(\d+)\s*(?:x|\*|by)\s*(\d+)", re.IGNORECASE)


# ── System & Media Controls ─────────────────────────────────────────────────
_SYS_CONTROL_RE = re.compile(r"^(?:sleep|lock|shutdown|mute)$|^(?:volume)\s+(\d+)$", re.IGNORECASE)
_MEDIA_CONTROL_RE = re.compile(r"^(?:play|pause|play/pause|next|skip|previous|prev|back)$", re.IGNORECASE)

# ── File Search ─────────────────────────────────────────────────────────────
_FILE_SEARCH_RE = re.compile(r"^(?:find|search)\s+(.+)", re.IGNORECASE)

# ── Reminders & Notes ───────────────────────────────────────────────────────
_REMINDER_RE = re.compile(r"^(?:remind me in|remind in)\s+(\d+\s*[a-z]+)\s+(.+)|^(?:note:?)\s+(.+)", re.IGNORECASE)

# ── Natural-language question patterns (should NEVER route to app_launch) ──
_QUESTION_RE = re.compile(
    r"^\s*(?:who|what|how|why|when|where|which|is|are|was|were|do|does|did|"
    r"can|could|will|would|should|tell me|explain|describe|define)\b",
    re.IGNORECASE,
)

_DOWNLOAD_THIS_RE = re.compile(r"^(?:download|dl|save|get)\b.*\b(?:this|video|audio|clip|song)?\b", re.IGNORECASE)

# ── App launch: minimum query length before fuzzy matching is worthwhile ────
_MIN_APP_QUERY_LEN = 2

# ── Fuzzy match threshold ───────────────────────────────────────────────────
_LAUNCH_THRESHOLD = 60   # score (0-100) above which we treat it as an app query


def classify(query: str, app_index=None, active_tab_url: str = None) -> str:
    """
    Classify the user query into one of the intent buckets.
    """
    q = query.strip()

    if not q:
        return "empty"

    # 1. Arithmetic
    if is_arithmetic(q):
        log.debug("classify → calc")
        return "calc"

    # 2. View Bookmarks (Highest priority for these keywords)
    if _VIEW_BOOKMARKS_RE.match(q):
        log.debug("classify → view_bookmarks")
        return "view_bookmarks"
        
    if _SAVE_BOOKMARK_RE.match(q):
        log.debug("classify → save_bookmark")
        return "save_bookmark"

    # 3. New Power Features
    if _SYS_CONTROL_RE.match(q):
        log.debug("classify → sys_control")
        return "sys_control"
        
    if _MEDIA_CONTROL_RE.match(q):
        log.debug("classify → media_control")
        return "media_control"
        
    if _FILE_SEARCH_RE.match(q):
        log.debug("classify → file_search")
        return "file_search"
        
    if _REMINDER_RE.match(q):
        log.debug("classify → reminder")
        return "reminder"
        
    if re.match(r"^(?:view notes|show notes|notes|my notes)$", q, re.IGNORECASE):
        log.debug("classify → view_notes")
        return "view_notes"

    # 4. Convert Image / Units
    if _CONVERT_RE.match(q):
        m = _CONVERT_RE.match(q)
        source_arg = m.group(1).strip()
        # If source argument starts with a number, it's a unit/currency conversion
        if re.match(r"^[\d.,]+", source_arg):
            log.debug("classify → convert")
            return "convert"
        else:
            log.debug("classify → image_convert")
            return "image_convert"
        
    # Also handle quick conversion like "100 usd to eur" (without the word "convert")
    if re.match(r"^([\d.,]+)\s+([a-zA-Z]+)\s+to\s+([a-zA-Z]+)", q, re.IGNORECASE):
        log.debug("classify → convert")
        return "convert"
        
    if _RESIZE_RE.match(q):
        log.debug("classify → image_resize")
        return "image_resize"

    # 5. Media URL (YouTube, Instagram, or implicit "download this" while on a media page)
    if _MEDIA_PATTERN.search(q):
        log.debug("classify → yt_download")
        return "yt_download"
        
    if _DOWNLOAD_THIS_RE.match(q):
        log.debug("classify → yt_download")
        return "yt_download"

    # 6. Page analysis
    if _PAGE_PHRASES.search(q):
        log.debug("classify → page_analyze")
        return "page_analyze"

    # 7. App fuzzy match (only if index available, query is long enough,
    #    AND query does NOT look like a natural language question)
    if app_index and len(q) >= _MIN_APP_QUERY_LEN and not _QUESTION_RE.match(q):
        # Also skip if query has 3+ words (likely a sentence, not an app name)
        word_count = len(q.split())
        if word_count <= 3:
            results = app_index.search(q, limit=1)
            if results:
                log.debug("classify → app_launch (top match: %s)", results[0].name)
                return "app_launch"

    # 8. Chat
    log.debug("classify → chat")
    return "chat"


def classify_for_live_preview(query: str, app_index=None) -> Optional[str]:
    """
    Lightweight classification for live-keystroke preview.
    """
    intent = classify(query, app_index)
    if intent in ("calc", "app_launch", "view_bookmarks", "convert", "sys_control", "media_control", "file_search", "view_notes", "image_convert", "image_resize"):
        return intent
    return None

