"""pipeline.py - runs one full job: download, then convert. No interface code lives here."""

import gc
import os
import shutil
import threading
import time
import uuid
from datetime import datetime

from .convert import convert, convert_audio
from .engine import Canceled, download, format_time
from .naming import plan_output, reserve_path, sidecar_path, variant_from_stem
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


def run_preset(url, preset_id, output_dir, on_progress=None, section=None, cancel=None,
               organize=None, info_out=None):
    """Downloads with a preset, converts if the preset asks for it, returns the final file path.

    preset_id: a preset id like "premiere", or a ready preset dictionary (the Custom section).
    section: None for the whole video, or (start_seconds, end_seconds).
    cancel: an Event; when it is set the job stops, raises Canceled and leaves no half-made files.
    organize: None = the old way (the file lands in output_dir with an id-based name).
              A dictionary = the new way: the file is filed as
              output_dir/<Platform>/<date>/<Clean title> [id]<extras>.<ext> and gets a source-info file.
              The dictionary may hold "summary" (what the editor asked for, in words) and "section"
              (the section plan from plan_section()).
    info_out: an empty dictionary that gets filled with the video's id, title, uploader, platform and link.
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
        return _run_job(url, preset, output_dir, work_dir, on_progress, section, cancel,
                        organize, info_out if info_out is not None else {})
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


def _source_text(info, url, preset, organize, final):
    """The words in the source-info file that sits next to the finished file."""
    platform = {"youtube": "YouTube", "x": "X"}.get(info.get("platform"), "")
    lines = [
        "Downloaded with Video Downloader",
        "",
        f"Title:     {info.get('title') or ''}",
        f"Uploader:  {info.get('uploader') or ''}",
        f"Link:      {info.get('webpage_url') or url}",
        f"Platform:  {platform}",
        f"Video ID:  {info.get('id') or ''}",
        f"Saved on:  {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"You asked: {organize.get('summary') or preset.get('name') or ''}",
        f"File:      {os.path.basename(final)}",
    ]
    plan = organize.get("section")
    if plan:
        extra = plan["start"] - plan["padded_start"]
        line = (f"Section:   {format_time(plan['start'])} to {format_time(plan['end'])} "
                f"(saved {format_time(plan['padded_start'])} to {format_time(plan['padded_end'])}")
        lines.append(line + (f", about {extra:g} s extra at the start)" if extra > 0 else ")"))
    return "\n".join(lines) + "\n"


def _file_result(result, url, preset, output_dir, info, organize):
    """Moves the finished file from the working folder to its place and writes the source-info file.

    Returns the final path. If anything goes wrong, the name that was claimed is given back.
    """
    extension = os.path.splitext(result)[1].lstrip(".")
    stem = os.path.splitext(os.path.basename(result))[0]
    video_id = info.get("id") or ""
    plan = plan_output(output_dir, info.get("platform") or "other", video_id or stem,
                       info.get("title"), info.get("uploader"),
                       variant_from_stem(stem, video_id), extension)
    final = reserve_path(plan["folder"], plan["base"], extension)
    try:
        try:
            os.replace(result, final)          # puts the real file over the empty claimed one
        except OSError:
            shutil.copy2(result, final)        # (a different drive: copy, then delete the working copy)
            os.remove(result)
    except BaseException:
        try:
            os.remove(final)
        except OSError:
            pass
        raise
    try:
        with open(sidecar_path(final), "w", encoding="utf-8-sig") as file:
            file.write(_source_text(info, url, preset, organize, final))
    except OSError:
        pass                                   # the video is safe; a missing note must not fail the job
    return final


def _run_job(url, preset, output_dir, work_dir, on_progress, section, cancel, organize=None, info_out=None):
    info = info_out if info_out is not None else {}
    downloaded = download(url, preset, output_dir, on_progress=on_progress, section=section,
                          cancel=cancel, work_dir=work_dir, info_out=info)
    if cancel is not None and cancel.is_set():
        raise Canceled()

    # New way: everything is made inside the working folder and only the finished file is moved out.
    made_in = work_dir if organize is not None else output_dir

    if preset["content"] == "audio_only":
        result = convert_audio(downloaded, preset["audio_format"], made_in,
                               on_progress=on_progress, cancel=cancel)
    else:
        result = convert(
            downloaded,
            preset["treatment"],
            made_in,
            on_progress=on_progress,
            drop_audio=(preset["content"] == "video_only"),
            label=preset.get("label"),
            cancel=cancel,
        )

    if organize is not None:
        if cancel is not None and cancel.is_set():
            raise Canceled()
        return _file_result(result, url, preset, output_dir, info, organize)

    if os.path.abspath(result) == os.path.abspath(downloaded):
        # "Original": the raw download IS the result, so move it out of the working folder.
        os.makedirs(output_dir, exist_ok=True)
        final = os.path.join(output_dir, os.path.basename(downloaded))
        os.replace(downloaded, final)      # replaces an older file with the same name
        return final
    return result