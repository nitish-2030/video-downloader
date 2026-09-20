"""main.py - the local server. It only listens on this computer (127.0.0.1)."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .engine import EngineError, detect_platform, get_info
from .jobs import get_job, start_job
from .presets import AUDIO_FORMATS, CONTENT_CHOICES, DEFAULT_PRESET, PRESETS, VIDEO_FORMATS

app = FastAPI(title="Video Downloader for Editors")


class InfoRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    preset: str = DEFAULT_PRESET


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
        return get_info(request.url)
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
    """Starts a download in the background. Returns a job id to check progress with."""
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
    if request.preset not in PRESETS:
        raise HTTPException(
            status_code=400,
            detail={"friendly": "That option isn't available.",
                    "details": f"Unknown preset: {request.preset}"},
        )
    return {"job_id": start_job(url, request.preset)}


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