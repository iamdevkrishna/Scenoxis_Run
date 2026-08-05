import urllib.request
import json
import os
import time
import threading
import logging

log = logging.getLogger(__name__)

CACHE_FILE = "data/currency_cache.json"
CACHE_EXPIRY = 86400  # 24 hours

_rates = {}

def init_converter():
    """Initializes the converter by loading cached rates and starting a background update if needed."""
    if not os.path.exists("data"):
        os.makedirs("data")
    
    _load_cache()
    if _is_cache_stale():
        threading.Thread(target=_update_rates, daemon=True).start()

def _load_cache():
    global _rates
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                data = json.load(f)
                _rates = data.get("rates", {})
        except Exception as e:
            log.error(f"Failed to load currency cache: {e}")

def _is_cache_stale() -> bool:
    if not os.path.exists(CACHE_FILE):
        return True
    return (time.time() - os.path.getmtime(CACHE_FILE)) > CACHE_EXPIRY

def _update_rates():
    global _rates
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            if "rates" in data:
                _rates = data["rates"]
                with open(CACHE_FILE, "w") as f:
                    json.dump(data, f)
                log.info("Currency rates updated successfully.")
    except Exception as e:
        log.error(f"Failed to update currency rates: {e}")

# Simple unit conversions (base to standard, standard to target)
# Length: base is meters
# Weight: base is grams
# Temperature: specially handled
_UNITS = {
    "length": {
        "m": 1.0, "meter": 1.0, "meters": 1.0,
        "km": 1000.0, "kilometer": 1000.0, "kilometers": 1000.0,
        "cm": 0.01, "centimeter": 0.01, "centimeters": 0.01,
        "mm": 0.001, "millimeter": 0.001, "millimeters": 0.001,
        "in": 0.0254, "inch": 0.0254, "inches": 0.0254,
        "ft": 0.3048, "foot": 0.3048, "feet": 0.3048,
        "yd": 0.9144, "yard": 0.9144, "yards": 0.9144,
        "mi": 1609.34, "mile": 1609.34, "miles": 1609.34,
    },
    "weight": {
        "g": 1.0, "gram": 1.0, "grams": 1.0,
        "kg": 1000.0, "kilogram": 1000.0, "kilograms": 1000.0,
        "mg": 0.001, "milligram": 0.001, "milligrams": 0.001,
        "lb": 453.592, "lbs": 453.592, "pound": 453.592, "pounds": 453.592,
        "oz": 28.3495, "ounce": 28.3495, "ounces": 28.3495,
    }
}

def convert(amount: float, source: str, target: str) -> str:
    source = source.lower().strip()
    target = target.lower().strip()
    
    # Check currency first
    source_cur = source.upper()
    target_cur = target.upper()
    
    if source_cur in _rates and target_cur in _rates:
        # Convert to USD first, then to target
        usd_amount = amount / _rates[source_cur]
        target_amount = usd_amount * _rates[target_cur]
        return f"{target_amount:,.2f} {target_cur}"
        
    # Check Temperature
    if source in ["c", "celsius", "f", "fahrenheit", "k", "kelvin"] and target in ["c", "celsius", "f", "fahrenheit", "k", "kelvin"]:
        # Convert to celsius first
        c = amount
        if source in ["f", "fahrenheit"]:
            c = (amount - 32) * 5/9
        elif source in ["k", "kelvin"]:
            c = amount - 273.15
            
        # Convert celsius to target
        if target in ["f", "fahrenheit"]:
            res = (c * 9/5) + 32
            return f"{res:,.2f} °F"
        elif target in ["k", "kelvin"]:
            res = c + 273.15
            return f"{res:,.2f} K"
        else:
            return f"{c:,.2f} °C"
            
    # Check simple units
    for category, units in _UNITS.items():
        if source in units and target in units:
            base_amount = amount * units[source]
            target_amount = base_amount / units[target]
            return f"{target_amount:,.4g} {target}"
            
    return ""

def convert_image(src_path: str, tgt_path: str, target_format: str) -> tuple[bool, str]:
    try:
        from PIL import Image
        img = Image.open(src_path)
        if img.mode in ("RGBA", "P") and target_format.lower() in ("jpeg", "jpg"):
            img = img.convert("RGB")
        img.save(tgt_path, format=target_format.upper())
        return True, tgt_path
    except Exception as e:
        log.error(f"Image conversion failed: {e}")
        return False, ""

def resize_image(src_path: str, tgt_path: str, width: int, height: int) -> tuple[bool, str]:
    try:
        from PIL import Image
        img = Image.open(src_path)
        img = img.resize((width, height), Image.Resampling.LANCZOS)
        img.save(tgt_path)
        return True, tgt_path
    except Exception as e:
        log.error(f"Image resize failed: {e}")
        return False, ""
