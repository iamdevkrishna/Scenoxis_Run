import os
import json
import logging
import uuid
import time
from typing import List, Dict

log = logging.getLogger(__name__)

NOTES_FILE = "data/notes.json"

def _ensure_dir():
    if not os.path.exists("data"):
        os.makedirs("data")

def get_notes() -> List[Dict]:
    if os.path.exists(NOTES_FILE):
        try:
            with open(NOTES_FILE, "r") as f:
                data = json.load(f)
                if data and isinstance(data[0], str):
                    return [{"id": str(uuid.uuid4()), "text": txt, "timestamp": time.time()} for txt in data]
                return data
        except Exception as e:
            log.error(f"Failed to load notes: {e}")
    return []

def save_note(text: str) -> str:
    _ensure_dir()
    notes = get_notes()
    
    notes.append({
        "id": str(uuid.uuid4()),
        "text": text,
        "timestamp": time.time()
    })
    
    try:
        with open(NOTES_FILE, "w") as f:
            json.dump(notes, f, indent=4)
        return f"Note saved: {text}"
    except Exception as e:
        log.error(f"Failed to save note: {e}")
        return "Failed to save note."

def delete_note(note_id: str) -> bool:
    notes = get_notes()
    initial_len = len(notes)
    notes = [n for n in notes if n.get("id") != note_id]
    if len(notes) < initial_len:
        try:
            with open(NOTES_FILE, "w") as f:
                json.dump(notes, f, indent=4)
            return True
        except Exception as e:
            log.error(f"Failed to save after deleting note: {e}")
    return False
