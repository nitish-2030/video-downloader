"""convert.py - ffmpeg conversion steps. No interface code lives here."""

import json
import os
import subprocess
import threading

from .engine import Canceled, EngineError
from .presets import AUDIO_FORMATS, CONVERSIONS

_PROGRESS_KEYS = {
    "frame", "fps", "bitrate", "total_size", "out_time_us", "out_time_ms",
    "out_time", "dup_frames", "drop_frames", "speed", "progress",
}


def probe_media(path):
    """Reads the first video stream, first audio stream and duration of a file."""
    command = [
        "ffprobe", "-v", "error",
        "-show_entries",
        "stream=codec_type,codec_name,pix_fmt,r_frame_rate,avg_frame_rate:format=duration",
        "-of", "json", path,
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
    except FileNotFoundError as error:
        raise EngineError("A required tool (ffmpeg) was not found on this computer.",
                          str(error)) from error
    except subprocess.CalledProcessError as error:
        raise EngineError("I couldn't read this file.", error.stderr) from error

    data = json.loads(result.stdout or "{}")
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = float((data.get("format") or {}).get("duration") or 0)
    return {"video": video, "audio": audio, "duration": duration}


def is_already_suitable(media, treatment, drop_audio=False):
    """True if the file already matches the target, so it can be copied without re-encoding."""
    if treatment != "premiere":
        return False
    video, audio = media["video"], media["audio"]
    if not video:
        return False
    if video.get("codec_name") != "h264" or video.get("pix_fmt") != "yuv420p":
        return False
    if video.get("r_frame_rate") != video.get("avg_frame_rate"):
        return False
    if audio and not drop_audio and audio.get("codec_name") != "aac":
        return False
    return True


def _seconds_from_stamp(stamp):
    """'00:00:07.290000' -> 7.29. Returns None for 'N/A' and other junk."""
    try:
        hours, minutes, seconds = stamp.strip().split(":")
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except ValueError:
        return None


def _build_command(input_path, output_path, conv, copy_only, drop_audio):
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-nostdin",
        "-progress", "pipe:1", "-nostats",
        "-i", input_path,
        "-map", "0:v:0",
    ]
    if not drop_audio:
        command += ["-map", "0:a:0?"]  # the ? means: fine if there is no audio
    if copy_only:
        command += ["-c:v", "copy"]
        command += ["-an"] if drop_audio else ["-c:a", "copy"]
    else:
        command += conv["video_args"]
        command += ["-an"] if drop_audio else conv["audio_args"]
    command += conv["extra_args"]
    command.append(output_path)
    return command


def _run_ffmpeg(command, duration, on_progress, output_path, failure_message, cancel=None):
    """Runs ffmpeg, reports progress while it works, removes the half-made file if it fails or is canceled."""
    try:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
    except FileNotFoundError as error:
        raise EngineError("A required tool (ffmpeg) was not found on this computer.",
                          str(error)) from error

    finished = threading.Event()
    if cancel is not None:
        def watch():
            # Checks the cancel flag a few times per second and stops ffmpeg, even if it is silent.
            while not finished.wait(0.2):
                if cancel.is_set():
                    process.terminate()
                    return
        threading.Thread(target=watch, daemon=True).start()

    log_tail = []
    try:
        for line in process.stdout:
            line = line.strip()
            key, _, value = line.partition("=")
            if key in _PROGRESS_KEYS:
                if key == "out_time" and on_progress and duration:
                    seconds = _seconds_from_stamp(value)
                    if seconds is not None:
                        percent = max(0.0, min(99.0, seconds / duration * 100))
                        on_progress({"status": "converting", "percent": percent,
                                     "speed": None, "eta": None})
            elif line:
                log_tail.append(line)
                log_tail = log_tail[-15:]
        process.wait()
    finally:
        finished.set()

    if cancel is not None and cancel.is_set():
        if os.path.exists(output_path):
            os.remove(output_path)
        raise Canceled()

    if process.returncode != 0:
        if os.path.exists(output_path):
            os.remove(output_path)
        raise EngineError(failure_message, "\n".join(log_tail))

    if on_progress:
        on_progress({"status": "converting", "percent": 100.0, "speed": None, "eta": None})


def _strip_audio(input_path, output_dir, on_progress, cancel=None):
    """'Original' without sound: copies the picture into a new file, no sound, no re-encoding."""
    media = probe_media(input_path)
    if not media["video"]:
        raise EngineError("This file has no picture.")

    folder = output_dir or os.path.dirname(os.path.abspath(input_path))
    os.makedirs(folder, exist_ok=True)
    stem, extension = os.path.splitext(os.path.basename(input_path))
    output_path = os.path.join(folder, f"{stem}_nosound{extension}")
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-nostdin",
        "-progress", "pipe:1", "-nostats",
        "-i", input_path,
        "-map", "0:v:0", "-c:v", "copy", "-an",
        output_path,
    ]
    _run_ffmpeg(command, media["duration"], on_progress, output_path, "Removing the sound failed.", cancel)
    return output_path


def convert(input_path, treatment, output_dir=None, on_progress=None, drop_audio=False, label=None, cancel=None):
    """Converts a downloaded file. Returns the path of the result.

    treatment: 'premiere', 'after_effects', 'original' or None.
    'original' and None keep the file as it is (only the sound is removed if drop_audio is True).
    label: the word added to the file name (default: the treatment). B-roll passes 'broll' so it
    never overwrites the Premiere file.
    """
    if treatment in (None, "original"):
        if not drop_audio:
            return input_path
        return _strip_audio(input_path, output_dir, on_progress, cancel)
    if treatment not in CONVERSIONS:
        raise EngineError("This conversion isn't available.", f"Unknown treatment: {treatment}")

    conv = CONVERSIONS[treatment]
    media = probe_media(input_path)
    if not media["video"]:
        raise EngineError("This file has no picture to convert.")
    copy_only = is_already_suitable(media, treatment, drop_audio)

    folder = output_dir or os.path.dirname(os.path.abspath(input_path))
    os.makedirs(folder, exist_ok=True)
    stem = os.path.splitext(os.path.basename(input_path))[0]
    output_path = os.path.join(folder, f"{stem}_{label or treatment}.{conv['extension']}")
    if os.path.abspath(output_path) == os.path.abspath(input_path):
        raise EngineError("The converted file would overwrite the original.")

    command = _build_command(input_path, output_path, conv, copy_only, drop_audio)
    _run_ffmpeg(command, media["duration"], on_progress, output_path, "Converting the video failed.", cancel)
    return output_path


def convert_audio(input_path, audio_format, output_dir=None, on_progress=None, cancel=None):
    """Turns a downloaded file into a WAV or MP3 (only the sound). Returns the new file's path."""
    if audio_format not in AUDIO_FORMATS:
        raise EngineError("This audio type isn't available.", f"Unknown audio format: {audio_format}")
    fmt = AUDIO_FORMATS[audio_format]

    media = probe_media(input_path)
    if not media["audio"]:
        raise EngineError("This video has no sound to save.")

    folder = output_dir or os.path.dirname(os.path.abspath(input_path))
    os.makedirs(folder, exist_ok=True)
    stem = os.path.splitext(os.path.basename(input_path))[0]
    output_path = os.path.join(folder, f"{stem}.{fmt['extension']}")
    if os.path.abspath(output_path) == os.path.abspath(input_path):
        output_path = os.path.join(folder, f"{stem}_audio.{fmt['extension']}")

    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-nostdin",
        "-progress", "pipe:1", "-nostats",
        "-i", input_path,
        "-vn", "-map", "0:a:0",
    ] + fmt["audio_args"] + [output_path]
    _run_ffmpeg(command, media["duration"], on_progress, output_path, "Converting the audio failed.", cancel)
    return output_path