"""jobs.py - the download queue. Jobs wait in order, run one (or two) at a time, and can be canceled or retried.

The list of jobs is kept in memory: closing the tool forgets it (the history is kept separately).
Where files are saved and how many jobs run at once come from the settings.
"""

import os
import shutil
import threading
import time
import uuid
from pathlib import Path

from .engine import Canceled, EngineError, detect_platform
from .pipeline import run_preset
from .presets import PRESETS, resolve_preset
from .settings import get_settings

# Normally None: files go to the output folder from the settings. The test scripts can set this to a
# folder of their own, and then that folder is used instead.
DOWNLOAD_DIR = None

# How many downloads run at the same time. Filled from the settings by apply_settings().
MAX_PARALLEL = 1

FINISHED = ("done", "error", "canceled")   # jobs that are over (they can be removed)

_lock = threading.RLock()
_jobs = {}           # job id -> what the page sees. The order of this dictionary IS the queue order.
_requests = {}       # job id -> (preset, section): what is needed to run the job again
_cancel_flags = {}   # job id -> Event that stops the job when set
_running = set()     # ids of jobs that have been started and are not finished yet


def output_dir():
    """The folder that files are saved in right now."""
    return str(DOWNLOAD_DIR) if DOWNLOAD_DIR else get_settings()["output_folder"]


def apply_settings():
    """Takes the number of simultaneous downloads from the settings (at start-up and after a change)."""
    set_max_parallel(get_settings()["parallel_downloads"])


def _summary(preset):
    """One plain line about what the job will make, like 'Premiere ready'."""
    if isinstance(preset, str):
        return PRESETS[preset]["name"]
    return preset.get("summary") or "Custom"


def _update(job_id, **changes):
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(changes)


def _schedule():
    """Starts waiting jobs, oldest first, while there is a free place."""
    with _lock:
        for job_id, job in _jobs.items():
            if len(_running) >= MAX_PARALLEL:
                break
            if job["status"] == "queued" and job_id not in _running:
                _running.add(job_id)
                job["status"] = "downloading"
                job["started"] = time.time()
                threading.Thread(target=_run, args=(job_id,), daemon=True).start()


def _run(job_id):
    with _lock:
        url = _jobs[job_id]["url"]
        preset, section = _requests[job_id]
        cancel = _cancel_flags[job_id]

    def on_progress(event):
        stage = "converting" if event.get("status") == "converting" else "downloading"
        changes = {"status": stage, "percent": event.get("percent"),
                   "speed": event.get("speed"), "eta": event.get("eta")}
        with _lock:
            if event.get("title") and not _jobs[job_id].get("title"):
                changes["title"] = event["title"]
        _update(job_id, **changes)

    try:
        times = (section["padded_start"], section["padded_end"]) if section else None
        info = {}
        result = run_preset(url, preset, output_dir(), on_progress=on_progress, section=times,
                            cancel=cancel, info_out=info,
                            organize={"summary": _summary(preset), "section": section})
        changes = {}
        with _lock:
            if info.get("title") and not _jobs[job_id].get("title"):
                changes["title"] = info["title"]
        _update(job_id, status="done", percent=100.0, speed=None, eta=None,
                file=os.path.basename(result), folder=os.path.dirname(result), path=result,
                video_id=info.get("id"), **changes)
    except Canceled:
        _update(job_id, status="canceled", speed=None, eta=None)
    except EngineError as error:
        _update(job_id, status="error", speed=None, eta=None,
                error={"friendly": error.friendly, "details": error.details})
    except Exception as error:
        _update(job_id, status="error", speed=None, eta=None,
                error={"friendly": "Something went wrong. Please try again.",
                       "details": str(error)})
    finally:
        with _lock:
            _running.discard(job_id)
        _schedule()


def start_job(url, preset, section=None, title=None):
    """Puts a download at the end of the queue and returns its job id right away.

    preset: a preset id like "premiere", or a ready preset dictionary (the Custom section).
    section: None for the whole video, or the plan from plan_section()
             (start, end, padded_start, padded_end in seconds).
    title: the video title if it is already known (otherwise it is filled in once the download starts).
    """
    resolve_preset(preset)  # raises KeyError for an unknown preset id
    job_id = uuid.uuid4().hex[:8]
    with _lock:
        _jobs[job_id] = {
            "id": job_id,
            "url": url,
            "title": title,
            "summary": _summary(preset),          # e.g. "Premiere ready"
            "preset": preset if isinstance(preset, str) else "custom",
            "content": resolve_preset(preset)["content"],   # video_audio | video_only | audio_only
            "section": section,                   # None = whole video
            "status": "queued",   # queued | downloading | converting | done | error | canceled
            "cancel_requested": False,
            "percent": 0.0,
            "speed": None,
            "eta": None,
            "platform": detect_platform(url),      # youtube | x
            "video_id": None,
            "file": None,
            "folder": None,
            "path": None,          # the full path of the finished file
            "error": None,
            "created": time.time(),
            "started": None,      # when the job left the waiting line (None = has not started yet)
        }
        _requests[job_id] = (preset, section)
        _cancel_flags[job_id] = threading.Event()
    _schedule()
    return job_id


def get_job(job_id):
    """Returns a copy of the job's current state, or None if the id is unknown."""
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def list_jobs():
    """All jobs in queue order (oldest first)."""
    with _lock:
        return [dict(job) for job in _jobs.values()]


def cancel_job(job_id):
    """Stops a job. A waiting job is canceled at once; a running one stops within a moment.

    Returns the job's state, or None if the id is unknown. A finished job is left as it is.
    """
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        if job["status"] == "queued":
            job["status"] = "canceled"
        elif job["status"] in ("downloading", "converting"):
            job["cancel_requested"] = True
            _cancel_flags[job_id].set()
        return dict(job)


def retry_job(job_id):
    """Puts a failed or canceled job at the end of the queue again (same id).

    Returns the job's state, or None if the id is unknown. Raises ValueError if it can't be retried.
    """
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        if job["status"] not in ("error", "canceled"):
            raise ValueError("Only a failed or canceled download can be tried again.")
        del _jobs[job_id]                       # re-adding puts it at the end of the queue
        job.update(status="queued", cancel_requested=False, percent=0.0, speed=None, eta=None,
                   file=None, folder=None, path=None, video_id=None, error=None, started=None)
        _jobs[job_id] = job
        _cancel_flags[job_id] = threading.Event()
    _schedule()
    return get_job(job_id)


def remove_job(job_id):
    """Takes one finished, failed or canceled job out of the list.

    Returns True, or None if the id is unknown. Raises ValueError if the job is still waiting or running.
    """
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        if job["status"] not in FINISHED:
            raise ValueError("Cancel this download first, then it can be removed.")
        del _jobs[job_id]
        _requests.pop(job_id, None)
        _cancel_flags.pop(job_id, None)
        return True


def clear_finished():
    """Removes finished and canceled jobs from the list. Failed jobs stay, so they can be retried.

    Returns how many were removed.
    """
    with _lock:
        cleared = [job_id for job_id, job in _jobs.items() if job["status"] in ("done", "canceled")]
        for job_id in cleared:
            del _jobs[job_id]
            _requests.pop(job_id, None)
            _cancel_flags.pop(job_id, None)
        return len(cleared)


def get_max_parallel():
    return MAX_PARALLEL


def set_max_parallel(count):
    """How many downloads may run at once (1 to 4)."""
    global MAX_PARALLEL
    MAX_PARALLEL = max(1, min(4, int(count)))
    _schedule()


def clean_leftovers():
    """At start-up: removes half-made files that a crash or a forced close left behind."""
    shutil.rmtree(Path(output_dir()) / "_working", ignore_errors=True)