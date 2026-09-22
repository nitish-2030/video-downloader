"""updater.py - checks whether yt-dlp has a newer version on PyPI, and can upgrade it.

Only talks to the internet when explicitly asked (a check or an update), never automatically.
yt-dlp is what actually knows how to talk to YouTube/X, so keeping it current is how most
"this used to work" breakages get fixed.
"""

import json
import subprocess
import sys
import urllib.request

import yt_dlp

PYPI_URL = "https://pypi.org/pypi/yt-dlp/json"


def current_version():
    """The yt-dlp version currently installed."""
    return yt_dlp.version.__version__


def latest_version(timeout=5):
    """The latest yt-dlp version on PyPI, or None if it can't be reached right now."""
    try:
        with urllib.request.urlopen(PYPI_URL, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data["info"]["version"]
    except Exception:
        return None


def _normalize(version_string):
    """Turns '2026.08.19' and '2026.8.19' into the same comparable tuple.

    PyPI normalizes version numbers (drops leading zeros in each segment, per PEP 440), but
    yt-dlp's own __version__ string keeps them - so a plain string compare sees a false
    "update available" even when both are the same release.
    """
    try:
        return tuple(int(part) for part in str(version_string).split("."))
    except (ValueError, AttributeError):
        return None


def check_for_update():
    """Returns {'current', 'latest', 'update_available'}. 'latest' is None if PyPI can't be reached."""
    current = current_version()
    latest = latest_version()
    same_release = latest and _normalize(current) == _normalize(latest) and _normalize(current) is not None
    return {
        "current": current,
        "latest": latest,
        "update_available": bool(latest) and not same_release,
    }


def run_update():
    """Upgrades yt-dlp via pip. Returns (success, message) - message is pip's own output either way."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return False, (result.stderr or "").strip()[-2000:] or "pip failed with no error message."
        return True, (result.stdout or "").strip()[-2000:]
    except Exception as error:
        return False, str(error)