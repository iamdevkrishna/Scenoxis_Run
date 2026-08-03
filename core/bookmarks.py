import os
import json
import logging
from pathlib import Path

log = logging.getLogger("scenoxis.bookmarks")

def _get_bookmarks_file() -> Path:
    app_data = Path(os.getenv("APPDATA", os.path.expanduser("~"))) / ".scenoxis"
    app_data.mkdir(parents=True, exist_ok=True)
    return app_data / "bookmarks.json"

def get_bookmarks() -> list:
    """Return a list of bookmarks, each a dict with 'url', 'title', etc."""
    path = _get_bookmarks_file()
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Failed to load bookmarks: %s", exc)
        return []

def save_bookmark(url: str, title: str = ""):
    """Save a new bookmark or update the title of an existing one."""
    if not url:
        return

    bookmarks = get_bookmarks()
    
    # Check if it already exists
    for bm in bookmarks:
        if bm.get("url") == url:
            if title:
                bm["title"] = title
            _write_bookmarks(bookmarks)
            return

    # Add new
    bookmarks.insert(0, {"url": url, "title": title or url})
    _write_bookmarks(bookmarks)
    log.info("Saved bookmark: %s", url)

def remove_bookmark(url: str):
    """Remove a bookmark by exact URL."""
    bookmarks = get_bookmarks()
    original_len = len(bookmarks)
    bookmarks = [bm for bm in bookmarks if bm.get("url") != url]
    if len(bookmarks) != original_len:
        _write_bookmarks(bookmarks)
        log.info("Removed bookmark: %s", url)

def _write_bookmarks(bookmarks: list):
    path = _get_bookmarks_file()
    try:
        path.write_text(json.dumps(bookmarks, indent=2), encoding="utf-8")
    except Exception as exc:
        log.error("Failed to write bookmarks: %s", exc)
