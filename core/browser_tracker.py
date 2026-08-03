import uiautomation as auto
import logging

log = logging.getLogger("scenoxis.browser_tracker")

def get_active_browser_url() -> str | None:
    """
    Attempts to fetch the URL from the currently active browser window using UIAutomation.
    Returns the URL string if found, otherwise None.
    """
    try:
        window = auto.GetForegroundControl()
        if not window:
            return None
            
        # 1. Try known exact names first (this is instant)
        # Chrome, Edge, Brave
        edit = window.EditControl(Name="Address and search bar")
        if edit.Exists(0, 0):
            try:
                val = edit.GetValuePattern().Value
                if val:
                    if not val.startswith("http"): val = "https://" + val
                    return val
            except Exception:
                pass
                
        # Firefox
        edit = window.EditControl(Name="Search with Google or enter address")
        if edit.Exists(0, 0):
            try:
                val = edit.GetValuePattern().Value
                if val:
                    if not val.startswith("http"): val = "https://" + val
                    return val
            except Exception:
                pass

        # 2. Fallback: Search the top levels for any EditControl that contains a URL-like string.
        for control, depth in auto.WalkTree(window, maxDepth=10):
            if control.ControlType == auto.ControlType.EditControl:
                try:
                    val = control.GetValuePattern().Value
                    if val and ("http://" in val or "https://" in val or "www." in val or ("." in val and " " not in val)):
                        if not val.startswith("http"):
                            val = "https://" + val
                        return val
                except Exception:
                    continue
                    
    except Exception as exc:
        log.debug("Failed to get browser url: %s", exc)
        
    return None
