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

# Audio-only choices. "quality" is passed to yt-dlp (None = not needed).
# Audio-only choices. Our own ffmpeg step makes these files (so the page can show real progress).
AUDIO_FORMATS = {
    "wav": {"label": "WAV (best for editing)", "extension": "wav",
            "audio_args": ["-c:a", "pcm_s16le"]},
    "mp3": {"label": "MP3 (smaller file)", "extension": "mp3",
            "audio_args": ["-c:a", "libmp3lame", "-b:a", "320k"]},
}


def get_preset(preset_id):
    """Returns one preset, or raises a clear error if the id is unknown."""
    if preset_id not in PRESETS:
        raise KeyError(f"Unknown preset: {preset_id}")
    return PRESETS[preset_id]