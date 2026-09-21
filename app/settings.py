"""settings.py - the editor's settings, kept in data/settings.json.

Only four things live here for now: where files are saved, which preset is picked at start,
how many extra seconds a section gets, and how many downloads run at the same time.
Nothing here talks to the interface or to yt-dlp.
"""

import json
import os
import tempfile
import threading
import uuid
from pathlib import Path

from .presets import PRESETS

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"

# Limits (the page shows them too, so they are in one place).
MIN_PARALLEL, MAX_PARALLEL_ALLOWED = 1, 4
MAX_EXTRA_SECONDS = 60
MAX_FOLDER_LENGTH = 120    # leaves room for Platform\date\title\variant inside Windows' 260-character path limit


class SettingsError(Exception):
    """A setting that can't be used. 'friendly' is for the page, 'details' for Show details."""

    def __init__(self, friendly, details=""):
        super().__init__(friendly)
        self.friendly = friendly
        self.details = details


def default_settings():
    return {
        "output_folder": str(Path.home() / "Videos" / "Video Downloader"),
        "default_preset": "premiere",
        "extra_seconds": 2,
        "parallel_downloads": 1,
    }


_lock = threading.RLock()
_cache = None   # the settings in memory, so the file is read only once


# ---------- checking one value at a time ----------

def _check_output_folder(value):
    text = str(value or "").strip().strip('"')
    if not text:
        raise SettingsError("Please choose a folder to save your videos in.")
    try:
        folder = Path(os.path.expandvars(os.path.expanduser(text)))
    except (ValueError, OSError) as error:
        raise SettingsError("That folder name can't be used.", str(error)) from error
    if not folder.is_absolute():
        raise SettingsError("Please give the full folder path, like C:\\Users\\you\\Videos\\Downloads.",
                            text)
    if len(str(folder)) > MAX_FOLDER_LENGTH:
        raise SettingsError("That folder path is too long. Please choose a shorter one.", str(folder))
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / f".write-test-{uuid.uuid4().hex[:8]}"
        probe.write_text("ok")
        probe.unlink()
    except (OSError, ValueError) as error:
        raise SettingsError("I can't save files in that folder. Please choose another one.",
                            str(error)) from error
    return str(folder)


def _check_default_preset(value):
    if value not in PRESETS:
        raise SettingsError("That preset isn't available.", f"Unknown preset: {value}")
    return value


def _check_extra_seconds(value):
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise SettingsError("Extra seconds must be a number.", str(value)) from error
    if not 0 <= number <= MAX_EXTRA_SECONDS:
        raise SettingsError(f"Extra seconds must be between 0 and {MAX_EXTRA_SECONDS}.", str(value))
    return int(number) if number == int(number) else round(number, 2)


def _check_parallel(value):
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise SettingsError("The number of downloads at once must be a whole number.",
                            str(value)) from error
    if not MIN_PARALLEL <= number <= MAX_PARALLEL_ALLOWED:
        raise SettingsError(
            f"Downloads at once must be between {MIN_PARALLEL} and {MAX_PARALLEL_ALLOWED}.", str(value))
    return number


_CHECKS = {
    "output_folder": _check_output_folder,
    "default_preset": _check_default_preset,
    "extra_seconds": _check_extra_seconds,
    "parallel_downloads": _check_parallel,
}


# ---------- the file ----------

def _write_file(settings):
    """Writes the whole file to a temporary name first, then swaps it in (a crash never leaves half a file)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=DATA_DIR, prefix="settings-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            json.dump(settings, file, indent=2, ensure_ascii=False)
        os.replace(temp_name, SETTINGS_FILE)
    except BaseException:
        try:
            os.remove(temp_name)
        except OSError:
            pass
        raise


def _load_from_disk():
    """Reads the file and fills in anything missing or unusable with the default."""
    settings = default_settings()
    try:
        saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return settings          # no file yet, or a broken one: start from the defaults
    if not isinstance(saved, dict):
        return settings
    for key, check in _CHECKS.items():
        if key not in saved:
            continue
        try:
            # The folder is only looked at here, not created: a missing drive must not stop the tool starting.
            settings[key] = str(saved[key]) if key == "output_folder" else check(saved[key])
        except SettingsError:
            pass                 # a bad saved value falls back to the default
    return settings


# ---------- what the rest of the tool uses ----------

def get_settings():
    """A copy of the current settings."""
    global _cache
    with _lock:
        if _cache is None:
            _cache = _load_from_disk()
        return dict(_cache)


def update_settings(changes):
    """Changes some settings (a dictionary with only the keys to change). Returns all settings.

    Everything is checked first; if anything is wrong nothing is saved and SettingsError is raised.
    """
    global _cache
    unknown = [key for key in changes if key not in _CHECKS]
    if unknown:
        raise SettingsError("That setting doesn't exist.", ", ".join(unknown))
    with _lock:
        new = get_settings()
        for key, value in changes.items():
            new[key] = _CHECKS[key](value)
        _write_file(new)
        _cache = new
        return dict(new)


def reload_settings():
    """Forgets the copy in memory, so the file is read again (used by tests)."""
    global _cache
    with _lock:
        _cache = None