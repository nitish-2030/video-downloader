"""pipeline.py - runs one full job: download, then convert. No interface code lives here."""

import os

from .convert import convert, convert_audio
from .engine import download
from .presets import get_preset


def run_preset(url, preset_id, output_dir, on_progress=None, section=None):
    """Downloads with a preset, converts if the preset asks for it, returns the final file path.

    section: None for the whole video, or (start_seconds, end_seconds).
    """
    preset = get_preset(preset_id)
    downloaded = download(url, preset_id, output_dir, on_progress=on_progress, section=section)

    if preset["content"] == "audio_only":
        result = convert_audio(downloaded, preset["audio_format"], output_dir, on_progress=on_progress)
    else:
        result = convert(
            downloaded,
            preset["treatment"],
            output_dir,
            on_progress=on_progress,
            drop_audio=(preset["content"] == "video_only"),
        )
    if os.path.abspath(result) != os.path.abspath(downloaded) and os.path.exists(downloaded):
        os.remove(downloaded)  # remove the raw download, keep only the finished file
    return result