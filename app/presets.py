"""presets.py - every preset lives here. To add or tune a preset, only edit this file."""

# Friendly text shown to the editor. No technical words on purpose.
# "content":   video_audio | video_only | audio_only
# "treatment": a key of CONVERSIONS below, or "original" (no conversion)
PRESETS = {
    "premiere": {
        "name": "Premiere ready",
        "description": "Best quality, plays smoothly on your timeline, with sound.",
        "content": "video_audio",
        "treatment": "premiere",
        "audio_format": None,
        "warning": None,
    },
    "after_effects": {
        "name": "After Effects ready",
        "description": "Highest quality, very smooth to work with, with sound. Files are large.",
        "content": "video_audio",
        "treatment": "after_effects",
        "audio_format": None,
        "warning": "These files are very large (roughly 1 GB per minute at 1080p, more at 4K).",
    },
    "broll": {
        "name": "B-roll (no sound)",
        "description": "Best quality picture only, no sound, smooth for editing.",
        "content": "video_only",
        "treatment": "premiere",
        "audio_format": None,
        "warning": None,
        "label": "broll",
    },
    "audio": {
        "name": "Audio only",
        "description": "Sound only, as a WAV file (the best choice for editing).",
        "content": "audio_only",
        "treatment": None,
        "audio_format": "wav",
        "warning": None,
    },
    "original": {
        "name": "Original (untouched)",
        "description": "Exactly what the website provides, nothing changed.",
        "content": "video_audio",
        "treatment": "original",
        "audio_format": None,
        "warning": None,
    },
}

DEFAULT_PRESET = "premiere"

# The ffmpeg settings behind "Smooth for editing". Values tested by hand in Phase 1.
CONVERSIONS = {
    "premiere": {
        "extension": "mp4",
        "video_args": ["-c:v", "libx264", "-crf", "17", "-preset", "medium",
                       "-pix_fmt", "yuv420p", "-fps_mode", "cfr"],
        "audio_args": ["-c:a", "aac", "-b:a", "320k"],
        "extra_args": ["-movflags", "+faststart"],
    },
    "after_effects": {
        "extension": "mov",
        "video_args": ["-c:v", "prores_ks", "-profile:v", "2",
                       "-pix_fmt", "yuv422p10le", "-fps_mode", "cfr"],
        "audio_args": ["-c:a", "pcm_s16le"],
        "extra_args": [],
    },
}

# Audio-only choices. Our own ffmpeg step makes these files (so the page can show real progress).
AUDIO_FORMATS = {
    "wav": {"label": "WAV (best for editing)", "extension": "wav",
            "audio_args": ["-c:a", "pcm_s16le"]},
    "mp3": {"label": "MP3 (smaller file)", "extension": "mp3",
            "audio_args": ["-c:a", "libmp3lame", "-b:a", "320k"]},
}



# Choices for the Custom section of the page (labels are plain words for the editor).
CONTENT_CHOICES = {
    "video_audio": "Video with sound",
    "video_only": "Video only (no sound)",
    "audio_only": "Sound only",
}

# "id" is a key of CONVERSIONS, or "original" (no conversion).
VIDEO_FORMATS = {
    "premiere": {"label": "Premiere ready (MP4)", "warning": None},
    "after_effects": {"label": "After Effects ready (MOV, large files)",
                      "warning": PRESETS["after_effects"]["warning"]},
    "original": {"label": "Original (untouched)", "warning": None},
}

def get_preset(preset_id):
    """Returns one preset, or raises a clear error if the id is unknown."""
    if preset_id not in PRESETS:
        raise KeyError(f"Unknown preset: {preset_id}")
    return PRESETS[preset_id]


def resolve_preset(preset):
    """Accepts a preset id (text) or a ready-made preset dictionary (custom choices)."""
    if isinstance(preset, dict):
        return preset
    return get_preset(preset)


def _quality_text(quality):
    """2160 -> '4K', 720 -> '720p', None -> 'Best quality'."""
    if not quality:
        return "Best quality"
    if quality >= 4320:
        return "8K"
    if quality >= 2160:
        return "4K"
    return f"{quality}p"


def build_custom_preset(content, quality=None, video_format="premiere", audio_format="wav"):
    """Turns the choices from the Custom section into a preset-shaped dictionary.

    Raises ValueError for a choice that doesn't exist. Extra keys used by the download:
    "quality" (short side in pixels, None = best available) and "label" (extra word in the file name).
    """
    if content not in CONTENT_CHOICES:
        raise ValueError(f"Unknown content choice: {content}")

    if content == "audio_only":
        if audio_format not in AUDIO_FORMATS:
            raise ValueError(f"Unknown audio type: {audio_format}")
        return {"name": "Custom", "content": content, "treatment": None,
                "audio_format": audio_format, "warning": None, "quality": None, "label": None,
                "summary": f"Custom: {CONTENT_CHOICES[content]} · {audio_format.upper()}"}

    if video_format not in VIDEO_FORMATS:
        raise ValueError(f"Unknown format: {video_format}")
    label = None
    if content == "video_only":
        # Keeps a no-sound file from overwriting the with-sound file of the same kind.
        label = "broll" if video_format == "premiere" else f"{video_format}_nosound"
    return {"name": "Custom", "content": content, "treatment": video_format,
            "audio_format": None, "warning": VIDEO_FORMATS[video_format]["warning"],
            "quality": quality, "label": label,
            "summary": f"Custom: {CONTENT_CHOICES[content]} · {_quality_text(quality)} · "
                       f"{PRESETS[video_format]['name']}"}