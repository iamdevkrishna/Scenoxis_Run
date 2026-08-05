"""
ui/result_item.py
Data class for a single row in the results panel.
"""
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class ResultKind(Enum):
    APP        = auto()   # Application launch result
    CALC       = auto()   # Calculator result
    CHAT       = auto()   # LLM chat answer (markdown)
    YT_FORMAT  = auto()   # YouTube format selection list
    YT_PROGRESS= auto()   # Active download with progress
    PAGE       = auto()   # Page analysis answer
    THINKING   = auto()   # Placeholder while LLM is processing
    ERROR      = auto()   # Error message
    BOOKMARK   = auto()   # Saved bookmark/watch later link
    IMAGE_CONVERT = auto() # Image conversion action
    IMAGE_RESIZE = auto()  # Image resize action
    ACTION     = auto()   # Generic execute action (system, media)
    FILE       = auto()   # File search result
    CONVERT    = auto()   # Unit/Currency conversion result
    NOTE       = auto()   # Saved note


@dataclass
class ResultItem:
    kind:        ResultKind
    title:       str                    # Primary display text
    subtitle:    str         = ""       # Secondary line (app exe path, calc expression, etc.)
    icon_path:   Optional[str] = None   # Absolute path to icon (apps only)
    raw_text:    str         = ""       # Full unformatted text (for copy or markdown source)
    html:        str         = ""       # Pre-rendered HTML (chat / page results)
    score:       float       = 0.0     # Fuzzy match score (apps)
    action_data: dict        = field(default_factory=dict)  # Extra data (exe path, yt url, etc.)
    selectable:  bool        = True
    progress:    float       = -1.0    # 0.0–1.0 for downloads, -1 means N/A
