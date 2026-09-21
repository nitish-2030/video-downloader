"""naming.py - where a finished file goes and what it is called. No downloading and no interface here.

Layout:  <output folder> / <Platform> / <YYYY-MM-DD> / <Clean title> [<video id>]<variant>.<ext>
Example: Videos\\Video Downloader\\YouTube\\2026-09-21\\My Trip to Goa [xuP4g7IDgDM]_720p_premiere.mp4
The date is the day of the download (the computer's local date).
"""

import os
import re
import threading
import unicodedata
from datetime import date

PLATFORM_FOLDERS = {"youtube": "YouTube", "x": "X"}

MAX_TITLE_LENGTH = 80        # characters of the title inside the file name
FULL_PATH_LIMIT = 255        # Windows stops at 260; we keep a few characters spare
SIDECAR_SUFFIX = ".source.txt"
DUPLICATE_ROOM = len(" (99)")   # room for " (2)", " (3)" ... on duplicates
MIN_TITLE_LENGTH = 10

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')       # Windows can't use these in a name
_LINK = re.compile(r"https?://\S+", re.IGNORECASE)         # X posts often end with a t.co link
_VARIATION_SELECTORS = re.compile("[\ufe00-\ufe0f\U000e0100-\U000e01ef]")   # invisible emoji helpers

_reserve_lock = threading.Lock()


# ---------- the title ----------

def _is_unwanted(char):
    """Emoji, symbols and invisible characters go. Letters (any language), numbers, marks and normal punctuation stay."""
    category = unicodedata.category(char)
    # So = emoji and pictures, Sk = skin-tone modifiers, Me = keycap ring, Cf = invisible joiners,
    # Co/Cs/Cn = private, broken or unassigned characters.
    return category in ("So", "Sk", "Me", "Cf", "Co", "Cs", "Cn")


def clean_title(text, max_length=MAX_TITLE_LENGTH):
    """Makes a title safe for a file name on Windows and Mac. Returns "" if nothing usable is left.

    - characters Windows can't use become spaces (so "what/why?" stays readable)
    - emoji and other pictures are removed, Hindi and other languages are kept
    - links are removed, spaces are tidied, trailing dots and spaces are removed
    - too-long titles are cut (at a space when possible, never in the middle of a letter with its marks)
    """
    text = unicodedata.normalize("NFC", str(text or ""))
    text = _LINK.sub(" ", text)
    text = _VARIATION_SELECTORS.sub("", text)
    text = "".join(" " if char.isspace() else char for char in text)
    text = _ILLEGAL.sub(" ", text)
    text = "".join(char for char in text if not _is_unwanted(char))
    text = re.sub(r"\s+", " ", text).strip(" .")

    if len(text) > max_length:
        cut = max_length
        while cut > 0 and unicodedata.category(text[cut]).startswith("M"):
            cut -= 1                       # don't leave a letter's marks behind
        shortened = text[:cut]
        space = shortened.rfind(" ")
        if space >= max_length * 0.6:      # a word boundary that isn't too far back
            shortened = shortened[:space]
        text = shortened
        while text and unicodedata.combining(text[-1]) == 9:
            text = text[:-1]               # a half-written Hindi letter (ends in a virama)
        text = text.strip(" .")
    return text


def display_title(platform, title, uploader):
    """The title we actually name the file with.

    X posts have no real title (it is the post's text), so the poster's name goes in front:
    'PrettyCitiesX - beautiful city'. YouTube titles are used as they are.
    """
    title = str(title or "").strip()
    uploader = str(uploader or "").strip()
    if platform != "x" or not uploader:
        return title
    plain = _LINK.sub("", title).strip()
    if plain.lower().startswith(uploader.lower()):
        return plain
    return f"{uploader} - {plain}" if plain else uploader


# ---------- the file name ----------

def variant_from_stem(stem, video_id):
    """'xuP4g7IDgDM_720p_premiere' -> '_720p_premiere'. The download steps put the id first, then the extras."""
    if video_id and stem.startswith(video_id):
        return stem[len(video_id):]
    return ""


def day_folder(today=None):
    """'2026-09-21' - the local date as a folder name."""
    return (today or date.today()).strftime("%Y-%m-%d")


def platform_folder(platform):
    return PLATFORM_FOLDERS.get(platform, "Other")


def plan_output(output_folder, platform, video_id, title, uploader, variant, extension, today=None):
    """Decides the folder and the file name (without the extension) for one finished file.

    Returns {"folder": ..., "base": ...}. The title is shortened if the whole path would get too long
    for Windows. Nothing is created on disk yet.
    """
    folder = os.path.join(output_folder, platform_folder(platform), day_folder(today))
    fixed = f" [{video_id}]{variant}"
    # the longest neighbour of the file is its source-info file: <name>.<ext>.source.txt
    reserved = len(fixed) + 1 + len(extension) + len(SIDECAR_SUFFIX) + DUPLICATE_ROOM
    room = FULL_PATH_LIMIT - len(folder) - 1 - reserved
    limit = max(MIN_TITLE_LENGTH, min(MAX_TITLE_LENGTH, room))

    name = clean_title(display_title(platform, title, uploader), limit)
    if not name:
        name = clean_title(uploader, limit) or "Video"
    return {"folder": folder, "base": f"{name}{fixed}"}


def sidecar_path(media_path):
    """The source-info file that sits next to a media file: 'Clip [id].mp4' -> 'Clip [id].mp4.source.txt'."""
    return media_path + SIDECAR_SUFFIX


def reserve_path(folder, base, extension):
    """Picks a free file name in the folder and claims it, so two jobs can never pick the same one.

    If 'Clip [id]_premiere.mp4' (or its source-info file) already exists, 'Clip [id]_premiere (2).mp4' is
    tried, then (3) and so on. The file is claimed by creating an empty file with that name; the caller
    then puts the real file over it (os.replace) or deletes the empty one if the job fails.
    Returns the full path.
    """
    os.makedirs(folder, exist_ok=True)
    with _reserve_lock:
        number = 1
        while True:
            name = base if number == 1 else f"{base} ({number})"
            path = os.path.join(folder, f"{name}.{extension}")
            if not os.path.exists(path) and not os.path.exists(sidecar_path(path)):
                try:
                    with open(path, "x"):
                        pass
                    return path
                except FileExistsError:
                    pass
            number += 1