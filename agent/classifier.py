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

# ── YouTube URL detection ───────────────────────────────────────────────────
_YT_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w\-]+",
    re.IGNORECASE,
)

# ── Page analysis trigger phrases ───────────────────────────────────────────
_PAGE_PHRASES = re.compile(
    r"\b(?:analys[ei]s?|describe|explain|summarise?|summarize|what(?:'s| is|s) (?:on|this|going on)|look at|tell me what)[\s\w]*(?:page|screen|window|tab)?\b",
    re.IGNORECASE,
)

# ── Natural-language question patterns (should NEVER route to app_launch) ──
_QUESTION_RE = re.compile(
    r"^\s*(?:who|what|how|why|when|where|which|is|are|was|were|do|does|did|"
    r"can|could|will|would|should|tell me|explain|describe|define)\b",
    re.IGNORECASE,
)

# ── App launch: minimum query length before fuzzy matching is worthwhile ────
_MIN_APP_QUERY_LEN = 2

# ── Fuzzy match threshold ───────────────────────────────────────────────────
_LAUNCH_THRESHOLD = 60   # score (0-100) above which we treat it as an app query


def classify(query: str, app_index=None) -> str:
    """
    Classify the user query into one of the intent buckets.
    
    Priority order (per spec):
      1. Arithmetic → "calc"
      2. YouTube URL → "yt_download"
      3. Page analysis phrase → "page_analyze"
      4. Fuzzy app match above threshold → "app_launch"
         (but ONLY if query does NOT look like a natural language question)
      5. Fallback → "chat"

    Args:
        query: Raw text from the search bar.
        app_index: Optional AppIndex instance. If None, skips app matching.

    Returns:
        Intent string: one of the five buckets.
    """
    q = query.strip()

    if not q:
        return "empty"

    # 1. Arithmetic
    if is_arithmetic(q):
        log.debug("classify → calc")
        return "calc"

    # 2. YouTube URL
    if _YT_PATTERN.search(q):
        log.debug("classify → yt_download")
        return "yt_download"

    # 3. Page analysis
    if _PAGE_PHRASES.search(q):
        log.debug("classify → page_analyze")
        return "page_analyze"

    # 4. App fuzzy match (only if index available, query is long enough,
    #    AND query does NOT look like a natural language question)
    if app_index and len(q) >= _MIN_APP_QUERY_LEN and not _QUESTION_RE.match(q):
        # Also skip if query has 3+ words (likely a sentence, not an app name)
        word_count = len(q.split())
        if word_count <= 3:
            results = app_index.search(q, limit=1)
            if results:
                log.debug("classify → app_launch (top match: %s)", results[0].name)
                return "app_launch"

    # 5. Chat
    log.debug("classify → chat")
    return "chat"


def classify_for_live_preview(query: str, app_index=None) -> Optional[str]:
    """
    Lightweight classification for live-keystroke preview.
    Only returns "calc" or "app_launch" — the two intents that show
    instant local results. Returns None for everything else (no preview yet).
    """
    intent = classify(query, app_index)
    if intent in ("calc", "app_launch"):
        return intent
    return None

