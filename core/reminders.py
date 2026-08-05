import threading
import time
import re
import subprocess
import logging

log = logging.getLogger(__name__)

def parse_time(time_str: str) -> int:
    """Parse relative time string like '10m', '1h', '30s' to seconds."""
    time_str = time_str.lower().strip()
    match = re.match(r'^(\d+)\s*(s|sec|m|min|h|hr|d|day)', time_str)
    if not match:
        return 0
        
    val = int(match.group(1))
    unit = match.group(2)
    
    if unit.startswith('s'):
        return val
    elif unit.startswith('m'):
        return val * 60
    elif unit.startswith('h'):
        return val * 3600
    elif unit.startswith('d'):
        return val * 86400
        
    return 0

def show_toast(title: str, message: str):
    """Trigger a native Windows 10/11 toast notification using PowerShell."""
    ps_script = f"""
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
    
    $APP_ID = 'Scenoxis Run'
    $template = @"
    <toast>
        <visual>
            <binding template="ToastText02">
                <text id="1">{title}</text>
                <text id="2">{message}</text>
            </binding>
        </visual>
    </toast>
"@
    
    $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
    $xml.LoadXml($template)
    $toast = New-Object Windows.UI.Notifications.ToastNotification $xml
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($APP_ID).Show($toast)
    """
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], 
                       creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception as e:
        log.error(f"Failed to show toast notification: {e}")

def _reminder_worker(delay_sec: int, text: str):
    time.sleep(delay_sec)
    show_toast("Reminder", text)

def schedule_reminder(time_str: str, text: str) -> str:
    """Schedule a reminder and return a confirmation message."""
    seconds = parse_time(time_str)
    if seconds <= 0:
        return "Invalid time format. Use something like '10m', '1h', '30s'."
        
    t = threading.Thread(target=_reminder_worker, args=(seconds, text), daemon=True)
    t.start()
    
    return f"Reminder set for {time_str} from now."
