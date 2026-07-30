"""
agent/tools/yt_downloader.py
YouTube download tool using yt-dlp.
Step 1: detect URL → list available formats.
Step 2: user selects a format → download with progress updates.
"""
import logging
import os
import re
from pathlib import Path
from typing import Callable, Optional
from langchain_core.tools import tool

log = logging.getLogger(__name__)

# Default download directory — ~/Downloads
DEFAULT_DOWNLOAD_DIR = str(Path.home() / "Downloads")

_YT_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w\-]+(?:&\S*)?",
    re.IGNORECASE,
)


def extract_yt_url(text: str) -> Optional[str]:
    """Extract the first YouTube URL from a string, or None."""
    m = _YT_URL_RE.search(text)
    return m.group(0) if m else None


def list_formats(url: str) -> list[dict]:
    """
    Use yt-dlp to list available formats for a YouTube URL.
    Returns a list of dicts: {format_id, ext, resolution, filesize_approx, note}
    Raises on failure so the UI can display the error.
    """
    import yt_dlp
    ydl_opts = {
        "quiet": False,
        "no_warnings": False,
        "listformats": False,
        "skip_download": True,
        "socket_timeout": 20,
        "extract_flat": False,
        "nocheckcertificate": True,
        "no_check_certificates": True,
    }
    print(f"[YT] list_formats() called for: {url}")
    print(f"[YT] Calling yt_dlp.extract_info (this may take a moment)...")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        print(f"[YT] extract_info returned successfully")
    except Exception as exc:
        print(f"[YT] extract_info FAILED: {type(exc).__name__}: {exc}")
        import traceback
        traceback.print_exc()
        raise RuntimeError(f"yt-dlp failed: {exc}") from exc

    if not info:
        print("[YT] extract_info returned None/empty!")
        raise RuntimeError("yt-dlp returned no info for this URL")

    formats = info.get("formats", [])
    log.info("yt-dlp: got %d raw formats", len(formats))

    result = []
    for f in formats:
        ext  = f.get("ext", "?")
        vcodec = f.get("vcodec", "none")
        acodec = f.get("acodec", "none")
        height = f.get("height")
        fps    = f.get("fps")
        tbr    = f.get("tbr")
        fsize  = f.get("filesize") or f.get("filesize_approx")

        # Categorize
        if vcodec != "none" and acodec != "none":
            cat = "Video + Audio"
            note = f"{height}p{int(fps) if fps else ''} [{ext}]"
        elif vcodec != "none":
            cat = "Video Only"
            note = f"{height}p{int(fps) if fps else ''} [{ext}]"
        elif acodec != "none":
            cat = "Audio Only"
            note = f"[{ext}] {int(tbr or 0)}kbps"
        else:
            cat = "Other"
            note = f"[{ext}] unknown"

        size_str = ""
        if fsize:
            size_str = f" ~{fsize / 1_048_576:.1f} MB"

        result.append({
            "category":     cat,
            "format_id":    f.get("format_id", "?"),
            "ext":          ext,
            "height":       height,
            "note":         note + size_str,
            "filesize":     fsize,
        })

    # Filter to meaningful formats (video+audio preferred, then best video, then audio)
    va = [r for r in result if r["category"] == "Video + Audio"]
    vo = [r for r in result if r["category"] == "Video Only"]
    ao = [r for r in result if r["category"] == "Audio Only"]

    # Sort each group by height descending (for audio, bitrate is sorted inherently if height is None)
    va.sort(key=lambda x: x.get("height") or 0, reverse=True)
    vo.sort(key=lambda x: x.get("height") or 0, reverse=True)
    
    # Sort audio by bitrate or filesize if possible, since height is 0
    ao.sort(key=lambda x: x.get("filesize") or 0, reverse=True)

    # Return a curated list: top 8 V+A, top 6 V-only, top 4 A-only
    curated = va[:8] + vo[:6] + ao[:4]
    return curated if curated else result[:15]


def download(
    url: str,
    format_id: str = "bestvideo+bestaudio/best",
    output_dir: str = DEFAULT_DOWNLOAD_DIR,
    progress_callback: Optional[Callable[[dict], None]] = None,
) -> dict:
    """
    Download a YouTube video.

    Args:
        url: YouTube URL
        format_id: yt-dlp format string or format_id from list_formats()
        output_dir: Directory to save the file
        progress_callback: Optional callable(progress_dict) for UI updates.
                           progress_dict keys: status, downloaded_bytes,
                           total_bytes, speed, eta, filename

    Returns:
        dict with 'success', 'filepath', 'error'
    """
    try:
        import yt_dlp

        filepath_holder = {"path": ""}

        def _hook(d):
            if progress_callback:
                progress_callback(d)
            if d.get("status") == "finished":
                filepath_holder["path"] = d.get("filename", "")

        ydl_opts = {
            "format": format_id,
            "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [_hook],
            "merge_output_format": "mp4",
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        return {"success": True, "filepath": filepath_holder["path"], "error": None}

    except Exception as exc:
        log.error("yt-dlp download failed: %s", exc)
        return {"success": False, "filepath": "", "error": str(exc)}


@tool
def download_youtube_video(url: str) -> str:
    """
    List available yt-dlp formats for a YouTube URL so the user can
    choose a quality to download. Returns a formatted list of format options.
    The actual download is triggered separately once the user picks a format.
    """
    formats = list_formats(url)
    if not formats:
        return f"Could not retrieve formats for: {url}"

    lines = [f"Available formats for {url}:\n"]
    for i, f in enumerate(formats, 1):
        lines.append(f"  {i}. [{f['format_id']}] {f['note']}")
    lines.append("\nReply with the number to download.")
    return "\n".join(lines)
