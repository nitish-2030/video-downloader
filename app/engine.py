"""engine.py - talks to yt-dlp. No interface code lives here."""

import os
from urllib.parse import urlparse

import yt_dlp
from yt_dlp.utils import DownloadError, download_range_func

from .presets import get_preset


class EngineError(Exception):
    """An error with a friendly message for the user and raw details for 'Show details'."""

    def __init__(self, friendly, details=""):
        super().__init__(friendly)
        self.friendly = friendly
        self.details = details


def detect_platform(url):
    """Returns 'youtube', 'x', or None if the link is not supported."""
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host in ("youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"):
        return "youtube"
    if host in ("x.com", "twitter.com", "mobile.twitter.com", "mobile.x.com"):
        return "x"
    return None


def quality_label(side):
    """Turns the short side of a video (in pixels) into a friendly label."""
    if not side:
        return "Unknown"
    if side >= 4320:
        return "8K"
    if side >= 2160:
        return "4K"
    return f"{side}p"


def short_side(fmt):
    """Short side of a format. Portrait 720x1280 -> 720, landscape 1920x1080 -> 1080."""
    height = fmt.get("height")
    width = fmt.get("width")
    if not height:
        return None
    return min(width, height) if width else height


# The standard sizes shown in the quality dropdown (the "short side" of the picture, biggest first).
QUALITY_STEPS = [4320, 2160, 1440, 1080, 720, 480, 360, 240, 144]


def build_quality_options(sizes):
    """Turns the real picture sizes of a video into a clean list for the quality dropdown.

    sizes: list of (width, height); width may be None if the site doesn't say.
    Each option is a ceiling: choosing it gets the best size that is not bigger than it.
    Odd sizes (like 1080x608) don't get their own entry, they sit under the standard step above them.
    Returns [{"value": 1080, "label": "1080p", "result": "1920x1080"}, ...], biggest first.
    """
    entries = []
    for width, height in set(sizes):
        if height:
            entries.append((min(width, height) if width else height, width or 0, height))
    if not entries:
        return []

    best_side = max(entry[0] for entry in entries)
    top = min((step for step in QUALITY_STEPS if step >= best_side), default=QUALITY_STEPS[0])

    options, seen = [], set()
    for step in reversed(QUALITY_STEPS):          # smallest step first, so a size keeps its closest label
        if step > top:
            continue
        fits = [entry for entry in entries if entry[0] <= step]
        if not fits:
            continue
        side, width, height = max(fits)            # the biggest size that still fits under this step
        if (width, height) in seen:
            continue
        seen.add((width, height))
        options.append({
            "value": step,
            "label": quality_label(step),
            "result": f"{width}x{height}" if width else f"{height}p",
        })
    return list(reversed(options))


def get_info(url):
    """Fetches video info without downloading anything."""
    url = url.strip()
    platform = detect_platform(url)
    if platform is None:
        raise EngineError("This link isn't supported. Please use a YouTube or X link.")

    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as error:
        raise EngineError("Couldn't read this video.", str(error)) from error

    sizes = []
    for fmt in info.get("formats", []):
        if fmt.get("vcodec") == "none" or fmt.get("ext") == "mhtml":
            continue
        if fmt.get("height"):
            sizes.append((fmt.get("width"), fmt["height"]))
    quality_options = build_quality_options(sizes)

    return {
        "platform": platform,
        "url": info.get("webpage_url") or url,
        "video_id": info.get("id"),
        "title": info.get("title") or "Untitled",
        "uploader": info.get("uploader") or info.get("channel") or "",
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "is_live": bool(info.get("is_live")),
        "quality_options": quality_options,
        "best_quality": ("Up to " + quality_options[0]["label"]) if quality_options else "Unknown",
    }


# ---------- Timeline (section) helpers ----------

def parse_time(text):
    """Accepts mm:ss, hh:mm:ss or plain seconds (decimals allowed). Returns seconds."""
    raw = str(text).strip()
    try:
        parts = [float(p) for p in raw.split(":")]
    except ValueError:
        parts = []
    if not parts or len(parts) > 3 or any(p < 0 for p in parts):
        raise EngineError(
            f"I couldn't understand the time '{raw}'. Use mm:ss, hh:mm:ss or seconds."
        )
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds


def format_time(seconds):
    """Turns seconds into m:ss or h:mm:ss for messages."""
    total = int(round(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def plan_section(start_text, end_text, extra_seconds, duration):
    """Validates a section and adds the extra seconds on each side.

    Returns start/end (what the user asked for) and padded_start/padded_end
    (what will actually be downloaded). Extra seconds never go below 0 or past the end.
    """
    start = parse_time(start_text)
    end = parse_time(end_text)
    extra = max(0.0, float(extra_seconds or 0))

    if start >= end:
        raise EngineError("The start time must be before the end time.")
    if duration:
        length = format_time(duration)
        if start >= duration:
            raise EngineError(
                f"The start time is past the end of the video (it is {length} long)."
            )
        if end > duration:
            raise EngineError(
                f"The end time is past the end of the video (it is {length} long)."
            )

    padded_start = max(0.0, start - extra)
    padded_end = end + extra
    if duration:
        padded_end = min(padded_end, float(duration))
    return {
        "start": start,
        "end": end,
        "padded_start": padded_start,
        "padded_end": padded_end,
    }


# ---------- Downloading ----------

def _make_progress_hook(on_progress):
    """Wraps yt-dlp's progress into a simple dict a queue can use later."""

    def hook(d):
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes") or 0
            percent = (done / total * 100) if total else None
            on_progress({
                "status": "downloading",
                "percent": percent,
                "speed": d.get("speed"),
                "eta": d.get("eta"),
            })
        elif status == "finished":
            on_progress({"status": "finished", "percent": 100.0, "speed": None, "eta": None})

    return hook


def download(url, preset_id, output_dir, on_progress=None, section=None):
    """Downloads a video (no conversion yet). Returns the path of the saved file.

    section: None for the whole video, or (start_seconds, end_seconds).
    """
    url = url.strip()
    if detect_platform(url) is None:
        raise EngineError("This link isn't supported. Please use a YouTube or X link.")

    preset = get_preset(preset_id)
    os.makedirs(output_dir, exist_ok=True)

    name = "%(id)s_section" if section else "%(id)s"
    options = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "overwrites": True,
        "outtmpl": os.path.join(output_dir, name + ".%(ext)s"),
        "merge_output_format": "mkv",
    }
    if on_progress:
        options["progress_hooks"] = [_make_progress_hook(on_progress)]
    if section:
        options["download_ranges"] = download_range_func([], [section])
        options["force_keyframes_at_cuts"] = True

    content = preset["content"]
    if content == "video_audio":
        options["format"] = "bv*+ba/b"
    elif content == "video_only":
        options["format"] = "bv*/b"
    elif content == "audio_only":
        # Only the sound is downloaded. Our own ffmpeg step (convert_audio) turns it into WAV/MP3.
        options["format"] = "ba/b"

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            downloads = info.get("requested_downloads") or []
            if downloads and downloads[0].get("filepath"):
                return downloads[0]["filepath"]
            return ydl.prepare_filename(info)
    except DownloadError as error:
        raise EngineError("The download failed.", str(error)) from error