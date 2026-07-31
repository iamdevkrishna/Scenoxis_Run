"""
agent/tools/launch_app.py
LangChain @tool wrapper for launching Windows applications.
The fast path (fuzzy match → subprocess) is handled by the local classifier
before any LLM call. This @tool exists so the LangGraph agent can also
launch apps when needed within a chat turn.
"""
import os
import subprocess
import logging
from langchain_core.tools import tool
from core.app_index import get_index

log = logging.getLogger(__name__)


def _launch_exe(path: str) -> None:
    """Launch an executable or file using the best method for its type."""
    lower = path.lower()
    if lower.startswith("shell:appsfolder"):
        # UWP App launch
        os.startfile(path)
    elif lower.endswith(".exe"):
        subprocess.Popen(
            [path],
            shell=False,
            close_fds=True,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    else:
        # os.startfile handles .msc, .lnk, .url, .bat, etc. correctly
        os.startfile(path)


@tool
def launch_app(name: str) -> str:
    """
    Launch a Windows application by fuzzy-matching its name against the
    installed app index. Returns a confirmation or error message.
    """
    index = get_index()
    entry = index.get_entry(name)
    if not entry:
        return f"No application matching '{name}' was found in the index."

    try:
        _launch_exe(entry.exe_path)
        log.info("Launched: %s → %s", entry.name, entry.exe_path)
        return f"Launched {entry.name}."
    except Exception as exc:
        log.error("Failed to launch %s: %s", entry.exe_path, exc)
        return f"Failed to launch {entry.name}: {exc}"


def launch_app_direct(name: str) -> dict:
    """
    Direct (non-LLM) launch used by the fast path in the UI.
    Returns a dict with 'launched', 'name', 'exe_path', 'error'.
    """
    index = get_index()
    results = index.search(name, limit=6)
    if not results:
        return {"launched": False, "name": name, "exe_path": "", "error": "Not found"}

    top = results[0]
    try:
        _launch_exe(top.exe_path)
        log.info("Fast-path launch: %s → %s", top.name, top.exe_path)
        return {"launched": True, "name": top.name, "exe_path": top.exe_path, "error": None}
    except Exception as exc:
        log.error("Fast-path launch error: %s", exc)
        return {"launched": False, "name": top.name, "exe_path": top.exe_path, "error": str(exc)}
