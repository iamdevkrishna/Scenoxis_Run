import subprocess
import os
import logging

log = logging.getLogger(__name__)

def search_files(query: str, limit: int = 15) -> list[str]:
    """
    Search for files using the Everything command line interface (es.exe).
    es.exe must be installed and in the system PATH, or located in the app directory.
    """
    # Check if es.exe exists in the current directory or PATH
    es_path = "es.exe"
    if os.path.exists("bin/es.exe"):
        es_path = "bin/es.exe"
        
    try:
        # Run es.exe with the query
        # -max-results limits the output
        result = subprocess.run(
            [es_path, query, "-max-results", str(limit)],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        
        if result.returncode == 0:
            lines = [line.strip() for line in result.stdout.split('\n') if line.strip()]
            return lines
        else:
            log.warning(f"es.exe returned non-zero exit code: {result.returncode}")
            return []
            
    except FileNotFoundError:
        log.error("es.exe not found. Please install Everything and its command-line interface (es.exe).")
        raise RuntimeError("File search requires 'es.exe' (Everything CLI) to be in your PATH or in a 'bin' folder.")
    except Exception as e:
        log.error(f"Error executing file search: {e}")
        return []
