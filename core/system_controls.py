import ctypes
import os

# Virtual Key Codes for Media Controls
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF

def send_media_key(key_code: int):
    """Send a virtual key press and release event."""
    # 0 = key press, 2 = key release
    ctypes.windll.user32.keybd_event(key_code, 0, 0, 0)
    ctypes.windll.user32.keybd_event(key_code, 0, 2, 0)

def execute_sys_control(action: str):
    """Execute a system control action."""
    action = action.lower().strip()
    
    if action in ["play", "pause", "play/pause"]:
        send_media_key(VK_MEDIA_PLAY_PAUSE)
        return "Media toggled."
    elif action in ["next", "skip"]:
        send_media_key(VK_MEDIA_NEXT_TRACK)
        return "Skipped to next track."
    elif action in ["previous", "prev", "back"]:
        send_media_key(VK_MEDIA_PREV_TRACK)
        return "Skipped to previous track."
    elif action == "mute":
        send_media_key(VK_VOLUME_MUTE)
        return "System volume muted/unmuted."
    elif action == "lock":
        ctypes.windll.user32.LockWorkStation()
        return "Workstation locked."
    elif action == "sleep":
        # Requires powrprof.dll to put the system to sleep
        os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
        return "System sleep initiated."
    elif action == "shutdown":
        # /s = shutdown, /t 0 = zero wait
        os.system("shutdown /s /t 0")
        return "System shutting down."
    elif action == "volume up":
        send_media_key(VK_VOLUME_UP)
        return "Volume increased."
    elif action == "volume down":
        send_media_key(VK_VOLUME_DOWN)
        return "Volume decreased."
    elif action.startswith("volume"):
        import re
        match = re.search(r"volume\s+(\d+)", action)
        if match:
            target_vol = int(match.group(1))
            target_vol = max(0, min(100, target_vol))
            # Windows changes volume by 2% per keypress
            # Hack: mute to 0, then go up
            for _ in range(50):
                send_media_key(VK_VOLUME_DOWN)
            for _ in range(target_vol // 2):
                send_media_key(VK_VOLUME_UP)
            return f"Volume set to ~{target_vol}%."
            
    return f"Unknown system control: {action}"
