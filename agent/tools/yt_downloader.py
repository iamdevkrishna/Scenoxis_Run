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

_MEDIA_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.|m\.)?(?:youtube\.com/watch\?.*v=|youtu\.be/|instagram\.com/(?:p|reel|reels|tv)/)[\w\-]+(?:&\S*)?",
    re.IGNORECASE,
)


def extract_yt_url(text: str) -> Optional[str]:
    """Extract the first media URL from a string, or None."""
    m = _MEDIA_URL_RE.search(text)
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
        "noplaylist": True,
    }
    print(f"[YT] list_formats() called for: {url}")
    print(f"[YT] Calling yt_dlp.extract_info (this may take a moment)...")
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        print(f"[YT] extract_info returned successfully")
    except Exception as exc:
        print(f"[YT] extract_info FAILED: {type(exc).__name__}: {exc}")
        import re
        err_msg = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', str(exc))
        if "No video formats found" in err_msg and "instagram.com" in url:
            # This is likely an Instagram image post!
            return [{
                "category": "Images",
                "format_id": "ig_images",
                "ext": "jpg/png",
                "height": None,
                "note": "Instagram Post Images (Full Quality)",
                "filesize": None
            }]
        raise RuntimeError(f"Download failed: {err_msg}") from exc

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
        fmt_id = f.get("format_id", "?")
        if vcodec != "none" and acodec != "none":
            cat = "Video + Audio"
            note = f"{height}p{int(fps) if fps else ''} [{ext}]"
        elif vcodec != "none":
            cat = "Video + Audio (HQ Muxed)"
            note = f"{height}p{int(fps) if fps else ''} [{ext}]"
            fmt_id = f"{fmt_id}+bestaudio/best"
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
            "format_id":    fmt_id,
            "ext":          ext,
            "height":       height,
            "note":         note + size_str,
            "filesize":     fsize,
        })

    # Filter to meaningful formats
    va = [r for r in result if r["category"] == "Video + Audio"]
    va_hq = [r for r in result if r["category"] == "Video + Audio (HQ Muxed)"]
    ao = [r for r in result if r["category"] == "Audio Only"]

    # Sort each group by height descending
    va.sort(key=lambda x: x.get("height") or 0, reverse=True)
    va_hq.sort(key=lambda x: x.get("height") or 0, reverse=True)
    
    # Sort audio by bitrate or filesize if possible
    ao.sort(key=lambda x: x.get("filesize") or 0, reverse=True)
    
    # Inject MP3 320kbps option
    mp3_option = {
        "category": "Audio Only",
        "format_id": "bestaudio_mp3_320",
        "ext": "mp3",
        "height": None,
        "note": "[mp3] 320kbps (Converted Best Audio)",
        "filesize": None
    }
    ao.insert(0, mp3_option)

    # Return a curated list: top 6 HQ, top 2 basic, top 5 audio
    curated = va_hq[:6] + va[:2] + ao[:5]
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

        if format_id == "ig_images" and "instagram.com" in url:
            # Run instaloader for image posts
            try:
                import instaloader
            except ImportError:
                return {"success": False, "filepath": "", "error": "instaloader is not installed. Please run: pip install instaloader"}
                
            m = re.search(r'instagram\.com/(?:p|reel|reels|tv)/([^/?]+)', url)
            if not m:
                return {"success": False, "filepath": "", "error": "Could not extract Instagram shortcode"}
            
            shortcode = m.group(1)
            post_dir = os.path.join(output_dir, f"Instagram_{shortcode}")
            
            if progress_callback:
                progress_callback({"status": "downloading", "filename": f"Instagram Images ({shortcode})"})
                
            L = instaloader.Instaloader(
                download_videos=False,
                download_video_thumbnails=False,
                download_geotags=False,
                download_comments=False,
                save_metadata=False,
                compress_json=False,
                dirname_pattern=f"Instagram_{shortcode}"
            )
            
            # Temporarily change working directory so instaloader doesn't sanitize absolute paths
            old_cwd = os.getcwd()
            os.makedirs(output_dir, exist_ok=True)
            os.chdir(output_dir)
            try:
                post = instaloader.Post.from_shortcode(L.context, shortcode)
                L.download_post(post, target="")
            finally:
                os.chdir(old_cwd)
            
            if progress_callback:
                progress_callback({"status": "finished", "filename": post_dir})
                
            return {"success": True, "filepath": post_dir, "error": None}

        ydl_opts = {
            "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [_hook],
            "merge_output_format": "mp4",
            "noplaylist": True,
        }
        
        if format_id == "bestaudio_mp3_320":
            ydl_opts["format"] = "bestaudio/best"
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            }]
        else:
            ydl_opts["format"] = format_id

        try:
            import imageio_ffmpeg
            ydl_opts["ffmpeg_location"] = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            pass

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        final_path = filepath_holder["path"]
        if format_id == "bestaudio_mp3_320" and final_path:
            base, _ = os.path.splitext(final_path)
            final_path = f"{base}.mp3"

        return {"success": True, "filepath": final_path, "error": None}

    except Exception as exc:
        err_msg = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', str(exc))
        log.error("download failed: %s", err_msg)
        return {"success": False, "filepath": "", "error": err_msg}


@tool
def download_youtube_video(url: str) -> str:
    """
    List available yt-dlp formats for a media URL so the user can
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
