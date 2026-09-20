"""pipeline.py - runs one full job: download, then convert. No interface code lives here."""

import gc
import os
import shutil
import threading
import time
import uuid

from .convert import convert, convert_audio
from .engine import Canceled, download
from .presets import resolve_preset


def _stop_ffmpeg_in(token):
    """Stops ffmpeg programs that work on this job's files (yt-dlp starts them for section downloads)."""
    try:
        import psutil
    except ImportError:
        return  # without psutil the cancel still works, it just waits until the clip is finished
    for process in psutil.process_iter(["name", "cmdline"]):
        try:
            if "ffmpeg" in (process.info["name"] or "").lower() and \
                    any(token in part for part in (process.info["cmdline"] or [])):
                process.kill()
        except psutil.Error:
            pass


def _forget_traceback(error):
    """Lets go of the program parts the error passed through.

    On Windows a half-written file stays locked as long as those parts are alive, and then the
    working folder can't be deleted. Dropping the traceback (and collecting) closes those files.
    """
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        error.__traceback__ = None
        error = error.__cause__ or error.__context__
    gc.collect()


def _remove_folder(folder):
    """Deletes a folder, trying again for a few seconds because Windows can hold a file for a moment."""
    for _ in range(15):
        shutil.rmtree(folder, ignore_errors=True)
        if not os.path.exists(folder):
            return
        time.sleep(0.3)


def run_preset(url, preset_id, output_dir, on_progress=None, section=None, cancel=None):
    """Downloads with a preset, converts if the preset asks for it, returns the final file path.

    preset_id: a preset id like "premiere", or a ready preset dictionary (the Custom section).
    section: None for the whole video, or (start_seconds, end_seconds).
    cancel: an Event; when it is set the job stops, raises Canceled and leaves no half-made files.
    """
    preset = resolve_preset(preset_id)
    token = "job-" + uuid.uuid4().hex[:8]          # this job's own private working folder
    work_dir = os.path.join(output_dir, "_working", token)
    stop_watching = threading.Event()

    if cancel is not None:
        def watch():
            while not stop_watching.wait(0.3):
                if cancel.is_set():
                    _stop_ffmpeg_in(token)
        threading.Thread(target=watch, daemon=True).start()

    try:
        return _run_job(url, preset, output_dir, work_dir, on_progress, section, cancel)
    except BaseException as error:
        _forget_traceback(error)
        raise
    finally:
        stop_watching.set()
        _remove_folder(work_dir)                        # raw download, half-made files, everything
        try:
            os.rmdir(os.path.join(output_dir, "_working"))   # only if empty
        except OSError:
            pass


def _run_job(url, preset, output_dir, work_dir, on_progress, section, cancel):
    downloaded = download(url, preset, output_dir, on_progress=on_progress, section=section,
                          cancel=cancel, work_dir=work_dir)
    if cancel is not None and cancel.is_set():
        raise Canceled()

    if preset["content"] == "audio_only":
        result = convert_audio(downloaded, preset["audio_format"], output_dir,
                               on_progress=on_progress, cancel=cancel)
    else:
        result = convert(
            downloaded,
            preset["treatment"],
            output_dir,
            on_progress=on_progress,
            drop_audio=(preset["content"] == "video_only"),
            label=preset.get("label"),
            cancel=cancel,
        )

    if os.path.abspath(result) == os.path.abspath(downloaded):
        # "Original": the raw download IS the result, so move it out of the working folder.
        os.makedirs(output_dir, exist_ok=True)
        final = os.path.join(output_dir, os.path.basename(downloaded))
        os.replace(downloaded, final)      # replaces an older file with the same name
        return final
    return result