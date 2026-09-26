"""main.py - the local server. It only listens on this computer (127.0.0.1)."""

import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .engine import QUALITY_STEPS, EngineError, detect_platform, get_info, plan_section, quality_label
from . import history
from . import updater
from .jobs import (apply_settings, cancel_job, clean_leftovers, clear_finished, get_job, list_jobs,
                   remove_job, retry_job, start_job)
from .presets import (AUDIO_FORMATS, CONTENT_CHOICES, DEFAULT_PRESET, PRESETS, VIDEO_FORMATS,
                      build_custom_preset)
from .settings import (MAX_EXTRA_SECONDS, MAX_PARALLEL_ALLOWED, MIN_PARALLEL, SettingsError,
                       get_settings, update_settings)

@asynccontextmanager
async def lifespan(app):
    clean_leftovers()   # half-made files from a crash or Ctrl+C are thrown away at start
    apply_settings()    # the number of downloads at once comes from the settings
    yield


app = FastAPI(title="Video Downloader for Editors", lifespan=lifespan)
_browse_lock = threading.Lock()   # only one folder-picker dialog at a time

# Limits for GET /api/history's paging (mirrors the pattern used for settings' own limits).
HISTORY_DEFAULT_LIMIT = 50
HISTORY_MAX_LIMIT = 200


class InfoRequest(BaseModel):
    url: str


class CustomOptions(BaseModel):
    """The choices from the Custom section of the page."""
    content: str                    # video_audio | video_only | audio_only
    quality: int | None = None      # short side in pixels, None = best available
    format: str = "premiere"        # premiere | after_effects | original
    audio_format: str = "wav"       # wav | mp3


class SectionOptions(BaseModel):
    """'Only a section' from the page. Times are text (mm:ss, hh:mm:ss or seconds)."""
    start: str
    end: str
    extra: float = 2                # extra seconds on each side, so the editor has room to trim


class SettingsUpdate(BaseModel):
    """Only the settings that changed are sent; the rest stay as they are."""
    output_folder: str | None = None
    default_preset: str | None = None
    extra_seconds: float | None = None
    parallel_downloads: int | None = None
    cookies_file: str | None = None


class DownloadRequest(BaseModel):
    url: str
    preset: str = DEFAULT_PRESET
    custom: CustomOptions | None = None   # if given, it is used instead of "preset"
    section: SectionOptions | None = None  # None = the whole video


# The video info that /api/info fetched is remembered for a few minutes, so checking the section
# times (which need the video length) doesn't fetch it a second time.
_INFO_KEEP_SECONDS = 600
_info_cache = {}   # link -> (time it was stored, info)


def _known_info(url):
    entry = _info_cache.get(url.strip())
    if entry and time.time() - entry[0] < _INFO_KEEP_SECONDS:
        return entry[1]
    return None


def _plan_for(url, section):
    """Checks the section times against the video length. Returns the plan, or raises a friendly 400."""
    try:
        info = _known_info(url)
        if info is None:
            info = get_info(url)
            _info_cache[url.strip()] = (time.time(), info)
        return plan_section(section.start, section.end, section.extra, info.get("duration"))
    except EngineError as error:
        raise HTTPException(
            status_code=400,
            detail={"friendly": error.friendly, "details": error.details, "action": error.action},
        )
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail={"friendly": "Something went wrong. Please try again.", "details": str(error)},
        )


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/update-check")
def update_check():
    """Checks PyPI for a newer yt-dlp. Never updates anything by itself."""
    return updater.check_for_update()


@app.post("/api/update")
def update_run():
    """Upgrades yt-dlp via pip. The owner presses a button for this - it never runs on its own.

    Python has already loaded the old yt-dlp into memory, so the new version only takes effect
    after the tool is restarted - the page tells the owner that.
    """
    ok, message = updater.run_update()
    if not ok:
        raise HTTPException(
            status_code=500,
            detail={"friendly": "The update didn't complete. Try again, or update it yourself with "
                                 "'pip install --upgrade yt-dlp'.", "details": message},
        )
    return {"updated": True, "details": message}


@app.get("/api/settings")
def settings_get():
    """The editor's settings, plus the limits the page should respect."""
    return {
        "settings": get_settings(),
        "limits": {"min_parallel": MIN_PARALLEL, "max_parallel": MAX_PARALLEL_ALLOWED,
                   "max_extra_seconds": MAX_EXTRA_SECONDS},
    }


@app.put("/api/settings")
def settings_put(request: SettingsUpdate):
    """Saves the settings that were sent. A bad value saves nothing and gives a friendly message."""
    try:
        saved = update_settings(request.model_dump(exclude_none=True))
    except SettingsError as error:
        raise HTTPException(status_code=400,
                            detail={"friendly": error.friendly, "details": error.details})
    apply_settings()    # a new number of downloads at once takes effect straight away
    return {"settings": saved}


@app.get("/api/history")
def history_list(limit: int = HISTORY_DEFAULT_LIMIT, offset: int = 0):
    """Past finished downloads, newest first, paged. Each entry says whether its file is still
    there. 'total' is the full history count, so the page can offer a "Load older" control."""
    limit = max(1, min(HISTORY_MAX_LIMIT, limit))
    offset = max(0, offset)
    return {"history": history.list_entries(limit=limit, offset=offset), "total": history.count_entries()}


@app.delete("/api/history")
def history_clear():
    """Empties the history list. The downloaded files themselves are never touched."""
    history.clear_history()
    return {"history": [], "total": 0}


class FolderRequest(BaseModel):
    path: str


@app.post("/api/history/open-folder")
def history_open_folder(request: FolderRequest):
    """Opens the given file's folder in Explorer (or Finder/file manager). 'path' must be one this
    program already knows about (a history entry's path, or a finished job's path) - the page
    never lets someone type an arbitrary path in."""
    known_paths = {entry["path"] for entry in history.list_entries() if entry.get("path")}
    known_paths |= {job["path"] for job in list_jobs() if job.get("path")}
    if request.path not in known_paths:
        raise HTTPException(status_code=400, detail={"friendly": "That file isn't in the history or queue."})
    if not history.open_folder(request.path):
        raise HTTPException(status_code=404,
                            detail={"friendly": "That file and its folder can't be found anymore."})
    return {"opened": True}


@app.post("/api/settings/browse-folder")
def settings_browse_folder():
    """Opens the computer's own folder picker and waits for a choice. Returns {"folder": null} if
    the editor canceled it. This blocks the request until the picker is closed, same as a native
    Save dialog would - fine for a local, single-editor tool."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as error:
        raise HTTPException(status_code=501, detail={
            "friendly": "The folder picker isn't available on this computer. Please type the path instead.",
            "details": str(error)})
    current = get_settings()["output_folder"]
    with _browse_lock:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        chosen = filedialog.askdirectory(
            title="Choose where to save your videos",
            initialdir=current if os.path.isdir(current) else str(Path.home()))
        root.destroy()
    return {"folder": chosen or None}


@app.post("/api/settings/browse-cookies-file")
def settings_browse_cookies_file():
    """Opens a native 'choose a file' dialog for picking an exported cookies.txt.

    Returns {"file": null} if the editor canceled it. Blocks until the dialog closes - fine for
    a local, single-editor tool (same pattern as the folder picker above).
    """
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as error:
        raise HTTPException(status_code=501, detail={
            "friendly": "The file picker isn't available on this computer. Please type the path instead.",
            "details": str(error)})
    with _browse_lock:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        chosen = filedialog.askopenfilename(
            title="Choose your exported cookies.txt",
            filetypes=[("Cookies file", "*.txt"), ("All files", "*.*")])
        root.destroy()
    return {"file": chosen or None}


@app.get("/api/presets")
def presets():
    """The quick presets in plain words, for the page to show."""
    default_id = get_settings().get("default_preset", DEFAULT_PRESET)
    return {
        "default": default_id if default_id in PRESETS else DEFAULT_PRESET,
        "presets": [
            {
                "id": preset_id,
                "name": preset["name"],
                "description": preset["description"],
                "warning": preset["warning"],
                "content": preset["content"],
            }
            for preset_id, preset in PRESETS.items()
        ],
        "audio_formats": [
            {"id": key, "label": value["label"]} for key, value in AUDIO_FORMATS.items()
        ],
        "quality_steps": [{"value": step, "label": quality_label(step)} for step in QUALITY_STEPS],
        "content_choices": [{"id": key, "label": label} for key, label in CONTENT_CHOICES.items()],
        "video_formats": [
            {"id": key, "label": value["label"], "warning": value["warning"]}
            for key, value in VIDEO_FORMATS.items()
        ],
    }


@app.post("/api/info")
def info(request: InfoRequest):
    """Fetches video info for a link (plain 'def' so it runs in a background thread)."""
    try:
        info = get_info(request.url)
        _info_cache[request.url.strip()] = (time.time(), info)
        return info
    except EngineError as error:
        raise HTTPException(
            status_code=400,
            detail={"friendly": error.friendly, "details": error.details, "action": error.action},
        )
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail={"friendly": "Something went wrong. Please try again.", "details": str(error)},
        )


@app.post("/api/download")
def download(request: DownloadRequest):
    """Starts a download in the background (a quick preset or Custom choices; whole video or a section). Returns a job id."""
    url = request.url.strip()
    if not url:
        raise HTTPException(
            status_code=400,
            detail={"friendly": "Please paste a link first.", "details": ""},
        )
    if detect_platform(url) is None:
        raise HTTPException(
            status_code=400,
            detail={"friendly": "This link isn't supported. Please use a YouTube or X link.",
                    "details": ""},
        )
    if request.custom is not None:
        custom = request.custom
        try:
            if custom.quality is not None and custom.quality not in QUALITY_STEPS:
                raise ValueError(f"Unknown quality: {custom.quality}")
            choice = build_custom_preset(custom.content, custom.quality, custom.format, custom.audio_format)
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail={"friendly": "That option isn't available.", "details": str(error)},
            )
    else:
        if request.preset not in PRESETS:
            raise HTTPException(
                status_code=400,
                detail={"friendly": "That option isn't available.",
                        "details": f"Unknown preset: {request.preset}"},
            )
        choice = request.preset

    plan = _plan_for(url, request.section) if request.section is not None else None
    title = (_known_info(url) or {}).get("title")
    return {"job_id": start_job(url, choice, plan, title)}


@app.get("/api/jobs")
def jobs_list():
    """The whole queue, oldest first."""
    return {"jobs": list_jobs()}


@app.post("/api/jobs/clear-finished")
def jobs_clear_finished():
    """Removes finished and canceled jobs from the list (failed ones stay so they can be retried)."""
    return {"removed": clear_finished()}


def _job_action(action, job_id):
    """Runs cancel / retry / remove and turns the outcomes into friendly errors."""
    try:
        result = action(job_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail={"friendly": str(error), "details": job_id})
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"friendly": "I can't find that download.", "details": job_id},
        )
    return result


@app.post("/api/jobs/{job_id}/cancel")
def jobs_cancel(job_id: str):
    return _job_action(cancel_job, job_id)


@app.post("/api/jobs/{job_id}/retry")
def jobs_retry(job_id: str):
    return _job_action(retry_job, job_id)


@app.delete("/api/jobs/{job_id}")
def jobs_remove(job_id: str):
    _job_action(remove_job, job_id)
    return {"removed": 1}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    """Current state of a download job (the page will ask for this every second or so)."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"friendly": "I can't find that download.", "details": job_id},
        )
    return job


# The page itself. This must stay LAST so it never hides the /api routes above.
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
# --- Runner: lets "python -m app.main" start the server and open the browser. ---

def _find_free_port(preferred=8756):
    """Tries the preferred port first, falls back to any free port if it's taken."""
    import socket
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return sock.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("Could not find a free port")


def main():
    import webbrowser
    import uvicorn

    port = _find_free_port()
    url = f"http://127.0.0.1:{port}"

    def _open_browser():
        time.sleep(1.0)  # give uvicorn a moment to start listening
        webbrowser.open(url)

    threading.Thread(target=_open_browser, daemon=True).start()

    print(f"Video Downloader for Editors is running at {url}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()