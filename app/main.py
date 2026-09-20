"""main.py - the local server. It only listens on this computer (127.0.0.1)."""

import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .engine import QUALITY_STEPS, EngineError, detect_platform, get_info, plan_section
from .jobs import get_job, start_job
from .presets import (AUDIO_FORMATS, CONTENT_CHOICES, DEFAULT_PRESET, PRESETS, VIDEO_FORMATS,
                      build_custom_preset)

app = FastAPI(title="Video Downloader for Editors")


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
            detail={"friendly": error.friendly, "details": error.details},
        )
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail={"friendly": "Something went wrong. Please try again.", "details": str(error)},
        )


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/presets")
def presets():
    """The quick presets in plain words, for the page to show."""
    return {
        "default": DEFAULT_PRESET,
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
            detail={"friendly": error.friendly, "details": error.details},
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
    return {"job_id": start_job(url, choice, plan)}


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