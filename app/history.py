"""history.py - a record of finished downloads, kept in data/history.json.

This is separate from jobs.py's queue: the queue forgets everything when the server stops,
history does not. Only "done" jobs are recorded - canceled and failed ones are not, since
there's no finished file to look back at.
"""

import json
import os
import platform
import subprocess
import tempfile
import threading
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
HISTORY_FILE = DATA_DIR / "history.json"

MAX_ENTRIES = 200

_lock = threading.RLock()


def _write_file(entries):
    """Same safe-write pattern as settings.py: a temp file first, then swapped in."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=DATA_DIR, prefix="history-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            json.dump(entries, file, indent=2, ensure_ascii=False)
        os.replace(temp_name, HISTORY_FILE)
    except BaseException:
        try:
            os.remove(temp_name)
        except OSError:
            pass
        raise


def _read_file():
    try:
        entries = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return entries if isinstance(entries, list) else []


def add_entry(*, title, url, platform_name, preset_summary, path, preset_id=None, content=None,
             section=None, job_id=None, finished_at=None):
    """Records one finished download. Newest entries are kept first; only the last MAX_ENTRIES stay.

    path may point at a file that no longer exists (moved or deleted by the editor) - that's fine,
    the entry is still useful for "what did I download and from where". list_entries() flags this.

    preset_id: the raw preset id used (e.g. "premiere", "broll", "audio", "original"), or "custom"
    for a one-off Custom-options download - not the display label. See app/presets.py for the ids.
    content: the raw content type ("video_audio", "video_only", "audio_only"), so the page can
    filter on it directly (this matters for "audio_only", which several presets can produce).
    section: None for the whole video, or the plan_section()-shaped dict (start/end/padded_start/
    padded_end) for a section download - the same shape the frontend already knows how to format.
    job_id: the queue job id that produced this entry, if known at write time. Lets the page match
    a job that is still visible in the (session-only) queue to its permanent history entry, so it
    is shown once instead of twice. None for entries where this isn't available (the page falls
    back to matching by link instead).
    """
    entry = {
        "title": title or "",
        "url": url,
        "platform": platform_name,
        "preset": preset_summary or "",
        "preset_id": preset_id,
        "content": content,
        "section": section,
        "job_id": job_id,
        "path": path,
        "finished_at": finished_at or datetime.now().isoformat(timespec="seconds"),
    }
    with _lock:
        entries = _read_file()
        entries.insert(0, entry)
        del entries[MAX_ENTRIES:]
        _write_file(entries)
    return entry


def list_entries(limit=None, offset=0):
    """Entries, newest first, each with a 'file_exists' flag for whether the file is still there.

    limit/offset page through the stored list; both default to "everything" (limit=None, offset=0),
    so existing callers that just want the full list (like open_folder's known-paths check) are
    unaffected. Use count_entries() alongside this for the total, e.g. for a "Load older" control.
    """
    with _lock:
        entries = _read_file()
    if offset:
        entries = entries[offset:]
    if limit is not None:
        entries = entries[:limit]
    for entry in entries:
        entry["file_exists"] = bool(entry.get("path")) and os.path.exists(entry["path"])
    return entries


def count_entries():
    """How many history entries exist in total (ignoring any limit/offset)."""
    with _lock:
        return len(_read_file())


def clear_history():
    """Empties the history list. Never touches the actual downloaded files."""
    with _lock:
        _write_file([])


def open_folder(path):
    """Opens the folder containing 'path' in the system file browser, with that file selected.

    Only ever called with a path this program already recorded (a history entry or a finished
    job) - never with anything typed by hand on the page, so there's nothing for the page to
    tamper with.
    """
    folder = os.path.dirname(path)
    system = platform.system()
    if system == "Windows":
        if os.path.exists(path):
            subprocess.run(["explorer", "/select,", os.path.normpath(path)])
        elif os.path.isdir(folder):
            subprocess.run(["explorer", os.path.normpath(folder)])
        else:
            return False
    elif system == "Darwin":
        if os.path.exists(path):
            subprocess.run(["open", "-R", path])
        elif os.path.isdir(folder):
            subprocess.run(["open", folder])
        else:
            return False
    else:
        if not os.path.isdir(folder):
            return False
        subprocess.run(["xdg-open", folder])
    return True