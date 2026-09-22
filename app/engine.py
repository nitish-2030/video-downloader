"""engine.py - talks to yt-dlp. No interface code lives here."""

import os
import shutil
from urllib.parse import urlparse

import yt_dlp
from yt_dlp.utils import DownloadCancelled, DownloadError, download_range_func

from .presets import resolve_preset
from .settings import get_settings


class EngineError(Exception):
    """An error with a friendly message for the user and raw details for 'Show details'.

    `action`, when set, tells the interface to offer a specific next step (right now the only
    one is "need_cookies": show a button that opens Settings, scrolled to the cookies.txt field,
    with the "how do I get this file" help open).
    """

    def __init__(self, friendly, details="", action=None):
        super().__init__(friendly)
        self.friendly = friendly
        self.details = details
        self.action = action


class Canceled(DownloadCancelled):
    """The user pressed Cancel. Not an error: the job just stops and its half-made files are removed."""


MIN_FREE_BYTES = 500 * 1024 * 1024   # 500 MB - a conservative floor before starting a download


def check_disk_space(path, minimum_bytes=MIN_FREE_BYTES):
    """Raises EngineError if the drive holding `path` doesn't have enough free space."""
    os.makedirs(path, exist_ok=True)
    free = shutil.disk_usage(path).free
    if free < minimum_bytes:
        free_mb = free // (1024 * 1024)
        raise EngineError(
            f"Not enough free disk space to download (only {free_mb} MB free). "
            "Free up some space and try again."
        )


def _cookie_options():
    """Reads the sign-in setting and returns the yt-dlp option(s) to add, if any.

    Sign-in works only through an exported cookies.txt file - it doesn't need to read a live
    browser's cookie database, so it isn't affected by Windows locking that database while the
    browser is open.
    """
    settings = get_settings()
    cookies_file = (settings.get("cookies_file") or "").strip()
    if cookies_file:
        return {"cookiefile": cookies_file}
    return {}


def _has_cookies_file():
    return bool((get_settings().get("cookies_file") or "").strip())


# The only kinds of failure worth retrying with cookies. Anything else (bot-check, network,
# "page needs to be reloaded", etc.) fails straight away - retrying those with cookies just
# wastes a second full attempt without any real chance of fixing the problem.
SIGNIN_ERROR_KEYS = (
    "sign in to confirm your age", "age-restricted", "age restricted",
    "private video",
    "members-only", "members only", "music premium members",
)


def _is_signin_error(message):
    text = message.lower()
    return any(key in text for key in SIGNIN_ERROR_KEYS)


def _extract_with_cookie_fallback(options, url, download):
    """Runs yt-dlp's extract_info without cookies first (the fast path for the common, public
    video case), and only retries with cookies.txt if that first attempt fails with a sign-in
    style error (age-restricted / private / members-only) and a cookies.txt is set.

    This way a cookies.txt left over from one earlier exceptional video doesn't add a second
    attempt to every normal download afterwards - cookies only get used when they're actually
    needed. If the cookies retry also fails, that failure (the real reason) is what gets raised.
    """
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            return ydl.extract_info(url, download=download)
    except DownloadError as error:
        cookie_spec = _cookie_options()
        if cookie_spec and _is_signin_error(str(error)):
            with yt_dlp.YoutubeDL({**options, **cookie_spec}) as ydl:
                return ydl.extract_info(url, download=download)
        raise


def _signin_message(what):
    """Builds the friendly message for a video that needs sign-in (age-restricted, private,
    members-only), depending on whether a cookies.txt file is already set up.

    Returns (friendly, action) - action is "need_cookies" so the interface can offer a button
    that opens Settings with the cookies.txt help open, rather than just naming the setting.
    """
    if _has_cookies_file():
        return (
            f"{what} Your cookies.txt sign-in didn't work for it — it may have expired, or be "
            "for a different account. Export a fresh cookies.txt from Settings and try again.",
            "need_cookies",
        )
    return (
        f"{what} Add a cookies.txt file in Settings to download it.",
        "need_cookies",
    )


def _classify_download_error(message):
    """Turns yt-dlp's raw error text into one of our known, friendly messages.

    Returns (friendly, action) if something matches, action may be None. Returns None if
    nothing matches, so the caller can fall back to a generic message.
    """
    text = message.lower()

    signin_checks = [
        (("sign in to confirm your age", "age-restricted", "age restricted"),
         "This video is age-restricted."),
        (("private video",),
         "This video is private."),
        (("members-only", "members only", "music premium members"),
         "This video is for members only."),
    ]
    for keys, what in signin_checks:
        if any(key in text for key in keys):
            return _signin_message(what)
    # (SIGNIN_ERROR_KEYS above is the flat version of the same keys, used to decide whether a
    # cookies retry is worth trying at all - keep both lists in sync if these ever change.)

    checks = [
        (("sign in to confirm you're not a bot", "confirm you're not a bot"),
         "YouTube is asking to confirm you're not a bot right now. This is usually temporary — "
         "try again in a few minutes, or try a different video."),
        (("this video is unavailable", "video unavailable", "video has been removed"),
         "This video isn't available anymore — it may have been removed, made private, or "
         "blocked in your region."),
        (("unsupported url",),
         "This link isn't a video page I can read. Double-check the link and try again."),
        (("requested format is not available", "no video formats found"),
         "Couldn't find a downloadable version of this video at that quality."),
        (("copyright",),
         "This video was blocked due to a copyright claim."),
        (("429", "too many requests"),
         "Too many requests right now. Wait a bit and try again."),
        (("timed out", "timeout"),
         "The connection timed out. Check your internet and try again."),
        (("failed to establish a new connection", "name or service not known", "getaddrinfo failed",
          "connection refused", "network is unreachable"),
         "Couldn't connect to the internet. Check your connection and try again."),
        (("live event will begin", "this live event", "premieres in"),
         "This video hasn't started yet — it's scheduled or a premiere."),
        (("live stream recording is not available",),
         "This live stream's recording isn't ready yet. Try again later."),
        (("could not open cookie", "no such file or directory", "cookie file"),
         "Couldn't read your cookies.txt file. Check that the path in Settings still points to "
         "it, then try again."),
        (("the page needs to be reloaded", "please reload"),
         "YouTube had a temporary hiccup loading this video. Try again in a moment — if it "
         "keeps happening, export a fresh cookies.txt in Settings and try again."),
    ]
    for keys, friendly in checks:
        if any(key in text for key in keys):
            return (friendly, None)
    return None


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
        info = _extract_with_cookie_fallback(options, url, download=False)
    except DownloadError as error:
        friendly, action = _classify_download_error(str(error)) or ("Couldn't read this video.", None)
        raise EngineError(friendly, str(error), action=action) from error

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

def _make_progress_hook(on_progress, cancel=None):
    """Wraps yt-dlp's progress into a simple dict a queue can use later.

    If the cancel flag is set, the next progress message stops the download (by raising Canceled).
    """

    def hook(d):
        if cancel is not None and cancel.is_set():
            raise Canceled()
        if not on_progress:
            return
        title = (d.get("info_dict") or {}).get("title")
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
                "title": title,
            })
        elif status == "finished":
            on_progress({"status": "finished", "percent": 100.0, "speed": None, "eta": None,
                         "title": title})

    return hook


def _time_tag(seconds):
    """Turns seconds into text that is safe in a file name: 78.0 -> '78', 78.5 -> '78p5'."""
    if abs(seconds - round(seconds)) < 0.05:
        return str(int(round(seconds)))
    return f"{seconds:.1f}".replace(".", "p")


def download(url, preset_id, output_dir, on_progress=None, section=None, cancel=None, work_dir=None,
             info_out=None):
    """Downloads a video (no conversion yet). Returns the path of the saved file.

    The raw download goes into work_dir (default: a "_working" folder inside output_dir), never straight
    into the output folder, so half-made files can always be thrown away. run_preset() moves and cleans up.

    preset_id: a preset id like "premiere", or a ready preset dictionary (the Custom section).
    section: None for the whole video, or (start_seconds, end_seconds).
    cancel: an Event; when it is set the download stops and Canceled is raised.
    info_out: an empty dictionary that gets filled with what is known about the video (id, title, uploader,
    platform, webpage_url, duration), so the caller can name and describe the file. Optional.
    """
    url = url.strip()
    if detect_platform(url) is None:
        raise EngineError("This link isn't supported. Please use a YouTube or X link.")

    preset = resolve_preset(preset_id)
    quality = preset.get("quality")   # short side in pixels (Custom section), None = best available

    work_dir = work_dir or os.path.join(output_dir, "_working")
    os.makedirs(work_dir, exist_ok=True)
    check_disk_space(work_dir)

    # The quality goes into the file name so two qualities of one video never overwrite each other.
    name = "%(id)s"
    if quality:
        name += "_" + quality_label(quality)
    if section:
        # The times go into the name too, so two sections of one video never overwrite each other.
        name += f"_section_{_time_tag(section[0])}-{_time_tag(section[1])}"
    options = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "overwrites": True,
        "outtmpl": os.path.join(work_dir, name + ".%(ext)s"),
        "merge_output_format": "mkv",
    }
    if on_progress or cancel is not None:
        options["progress_hooks"] = [_make_progress_hook(on_progress, cancel)]
    if section:
        options["download_ranges"] = download_range_func([], [section])
        options["force_keyframes_at_cuts"] = True
    cookie_spec = _cookie_options()

    content = preset["content"]
    if content == "video_audio":
        options["format"] = "bv*+ba/b"
    elif content == "video_only":
        options["format"] = "bv*/b"
    elif content == "audio_only":
        # Only the sound is downloaded. Our own ffmpeg step (convert_audio) turns it into WAV/MP3.
        options["format"] = "ba/b"

    if quality and content != "audio_only":
        # "res" is the short side of the picture. res:720 means: the best picture up to 720, not bigger.
        options["format_sort"] = [f"res:{quality}"]

    # Built once here (not merged into `options`) so the first attempt below never carries cookies -
    # cookies only get added if that first attempt fails with a sign-in style error.
    cookie_options = {**options, **cookie_spec} if cookie_spec else None

    def _run(opts):
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if cancel is not None and cancel.is_set():
                raise Canceled()
            if info_out is not None:
                info_out.update({
                    "id": info.get("id"),
                    "title": info.get("title"),
                    "uploader": info.get("uploader") or info.get("channel") or "",
                    "platform": detect_platform(url),
                    "webpage_url": info.get("webpage_url") or url,
                    "duration": info.get("duration"),
                })
            downloads = info.get("requested_downloads") or []
            if downloads and downloads[0].get("filepath"):
                return downloads[0]["filepath"]
            return ydl.prepare_filename(info)

    try:
        return _run(options)
    except DownloadError as error:
        if cancel is not None and cancel.is_set():
            raise Canceled() from error   # the cancel stopped a helper program, so yt-dlp complained
        # Only worth a second attempt with cookies if this looks like a sign-in problem
        # (age-restricted / private / members-only) and a cookies.txt is actually set. A bot-check,
        # network error, or anything else won't be fixed by cookies, so fail straight away instead
        # of wasting a full second download attempt on it.
        if not (cookie_options and _is_signin_error(str(error))):
            friendly, action = _classify_download_error(str(error)) or ("The download failed.", None)
            raise EngineError(friendly, str(error), action=action) from error
        try:
            return _run(cookie_options)
        except DownloadError as retry_error:
            if cancel is not None and cancel.is_set():
                raise Canceled() from retry_error
            friendly, action = _classify_download_error(str(retry_error)) or (
                "The download failed.", None)
            raise EngineError(friendly, str(retry_error), action=action) from retry_error