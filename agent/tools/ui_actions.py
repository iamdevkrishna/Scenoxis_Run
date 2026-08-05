from langchain_core.tools import tool
import json

@tool
def trigger_image_convert(source_format: str, target_format: str) -> str:
    """
    Triggers the native Image Converter UI dialog.
    Use this when the user asks to convert an image (e.g., from png to jpg).
    """
    return json.dumps({
        "ui_action": "image_convert",
        "params": {"src": source_format, "tgt": target_format}
    })

@tool
def trigger_image_resize(width: int, height: int) -> str:
    """
    Triggers the native Image Resizer UI dialog.
    Use this when the user asks to resize an image (e.g., to 1920x1080).
    """
    return json.dumps({
        "ui_action": "image_resize",
        "params": {"width": width, "height": height}
    })

@tool
def trigger_yt_download(query: str = "") -> str:
    """
    Triggers the native YouTube downloader UI.
    Use this when the user asks to download a YouTube video or song (e.g., 'download this', 'download this video', 'get the audio').
    The UI will automatically extract the URL from the active browser tab.
    """
    return json.dumps({
        "ui_action": "yt_download",
        "params": {"query": query}
    })
