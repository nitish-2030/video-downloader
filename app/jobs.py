"""jobs.py - a tiny in-memory job runner. Phase 6 replaces this with the real queue."""

import os
import threading
import uuid
from pathlib import Path

from .engine import EngineError
from .pipeline import run_preset
from .presets import resolve_preset

# Temporary fixed folder. Phase 7 adds the output-folder setting.
DOWNLOAD_DIR = Path(__file__).resolve().parent.parent / "downloads"

_jobs = {}
_jobs_lock = threading.Lock()  # protects the _jobs dictionary
_run_lock = threading.Lock()   # only one job runs at a time; the others wait as "queued"


def _update(job_id, **changes):
    with _jobs_lock:
        _jobs[job_id].update(changes)


def _run(job_id, url, preset, section):
    with _run_lock:
        _update(job_id, status="downloading")

        def on_progress(event):
            stage = "converting" if event.get("status") == "converting" else "downloading"
            _update(
                job_id,
                status=stage,
                percent=event.get("percent"),
                speed=event.get("speed"),
                eta=event.get("eta"),
            )

        try:
            times = (section["padded_start"], section["padded_end"]) if section else None
            result = run_preset(url, preset, str(DOWNLOAD_DIR), on_progress=on_progress, section=times)
            _update(
                job_id,
                status="done",
                percent=100.0,
                speed=None,
                eta=None,
                file=os.path.basename(result),
                folder=str(DOWNLOAD_DIR),
            )
        except EngineError as error:
            _update(job_id, status="error",
                    error={"friendly": error.friendly, "details": error.details})
        except Exception as error:
            _update(job_id, status="error",
                    error={"friendly": "Something went wrong. Please try again.",
                           "details": str(error)})


def start_job(url, preset, section=None):
    """Starts a download in the background and returns its job id right away.

    preset: a preset id like "premiere", or a ready preset dictionary (the Custom section).
    section: None for the whole video, or the plan from plan_section()
             (start, end, padded_start, padded_end in seconds).
    """
    choice = resolve_preset(preset)  # raises KeyError for an unknown preset id
    job_id = uuid.uuid4().hex[:8]
    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id,
            "url": url,
            "preset": preset if isinstance(preset, str) else "custom",
            "section": section,   # None = whole video
            "content": choice["content"],   # video_audio | video_only | audio_only (the page uses it for wording)
            "status": "queued",   # queued | downloading | converting | done | error
            "percent": 0.0,
            "speed": None,
            "eta": None,
            "file": None,
            "folder": None,
            "error": None,
        }
    threading.Thread(target=_run, args=(job_id, url, preset, section), daemon=True).start()
    return job_id


def get_job(job_id):
    """Returns a copy of the job's current state, or None if the id is unknown."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None