import os
import json
import logging
from typing import Any, Dict

log = logging.getLogger(__name__)

APP_NAME = "ScenoxisRun"

def get_config_dir() -> str:
    appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
    config_dir = os.path.join(appdata, APP_NAME)
    if not os.path.exists(config_dir):
        try:
            os.makedirs(config_dir, exist_ok=True)
        except Exception as e:
            log.error(f"Failed to create config directory: {e}")
    return config_dir

def get_config_file() -> str:
    return os.path.join(get_config_dir(), "config.json")

def load_config() -> Dict[str, Any]:
    config_file = get_config_file()
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.error(f"Failed to load config: {e}")
            return {}
    return {}

def save_config(config: Dict[str, Any]):
    config_file = get_config_file()
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        log.error(f"Failed to save config: {e}")

def get(key: str, default: Any = None) -> Any:
    return load_config().get(key, default)

def set(key: str, value: Any):
    config = load_config()
    config[key] = value
    save_config(config)

def get_api_key(service: str) -> str:
    """Gets API key from config, fallback to environment variable."""
    key = get(f"{service.upper()}_API_KEY", "")
    if not key:
        key = os.environ.get(f"{service.upper()}_API_KEY", "")
    return key

def is_dark_mode() -> bool:
    """Determine if we should use dark mode."""
    theme = get("theme", "system").lower()
    if theme == "dark":
        return True
    if theme == "light":
        return False
    
    # System default detection on Windows
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return value == 0
    except Exception:
        return True # Default to dark on error
