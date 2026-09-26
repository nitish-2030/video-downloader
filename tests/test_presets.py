"""test_presets.py - throwaway test. Runs every preset on real links and checks each result with ffprobe.

Run from the downloader folder (venv active):   python test_presets.py
It writes into the folder test_presets_out (you can delete that folder afterwards).
"""

import json
import os
import shutil
import subprocess
import time

from app.engine import EngineError, get_info
from app.pipeline import run_preset

OUT = "test_presets_out"
YOUTUBE = "https://www.youtube.com/watch?v=xuP4g7IDgDM"
X_LINK = "https://x.com/PrettyCitiesX/status/2100991213621092475?s=20"

# (label, link, preset)
CASES = [
    ("yt_premiere", YOUTUBE, "premiere"),
    ("yt_after_effects", YOUTUBE, "after_effects"),
    ("yt_broll", YOUTUBE, "broll"),
    ("yt_audio", YOUTUBE, "audio"),
    ("yt_original", YOUTUBE, "original"),
    ("x_premiere", X_LINK, "premiere"),
    ("x_broll", X_LINK, "broll"),
    ("x_audio", X_LINK, "audio"),
]


def fps(text):
    """'30/1' -> 30.0. Returns None if the text is missing or '0/0'."""
    try:
        top, bottom = text.split("/")
        return float(top) / float(bottom)
    except (ValueError, ZeroDivisionError, AttributeError):
        return None


def probe(path):
    command = [
        "ffprobe", "-v", "error",
        "-show_entries",
        "stream=codec_type,codec_name,profile,pix_fmt,width,height,r_frame_rate,avg_frame_rate,"
        "sample_rate,channels,duration:format=duration,format_name,size",
        "-of", "json", path,
    ]
    data = json.loads(subprocess.run(command, capture_output=True, text=True, check=True).stdout)
    streams = data.get("streams", [])
    return {
        "video": next((s for s in streams if s.get("codec_type") == "video"), None),
        "audio": next((s for s in streams if s.get("codec_type") == "audio"), None),
        "duration": float(data["format"].get("duration") or 0),
        "container": data["format"].get("format_name", ""),
        "size": int(data["format"].get("size") or 0),
    }


def describe(media):
    lines = []
    v, a = media["video"], media["audio"]
    if v:
        rate = fps(v.get("r_frame_rate"))
        lines.append(f"video : {v.get('codec_name')} {v.get('profile', '')} {v.get('width')}x{v.get('height')} "
                     f"{v.get('pix_fmt')} {rate:.3f} fps" if rate else f"video : {v.get('codec_name')}")
    else:
        lines.append("video : none")
    if a:
        lines.append(f"audio : {a.get('codec_name')} {a.get('sample_rate')} Hz, {a.get('channels')} ch")
    else:
        lines.append("audio : none")
    lines.append(f"length: {media['duration']:.2f} s   size: {media['size'] / 1_000_000:.1f} MB   "
                 f"container: {media['container']}")
    return lines


def check(preset, link, path, media, source_duration):
    """Returns a list of (passed, text) checks for one finished file."""
    results = []
    v, a = media["video"], media["audio"]
    ext = os.path.splitext(path)[1].lower()

    def add(passed, text):
        results.append((bool(passed), text))

    add(media["size"] > 0, "file is not empty")
    if source_duration:
        add(abs(media["duration"] - source_duration) <= 1.0,
            f"length matches the source ({media['duration']:.2f} s vs {source_duration:.2f} s)")

    if preset in ("premiere", "broll"):
        add(ext == ".mp4", "container is .mp4")
        add(v and v.get("codec_name") == "h264", "video is H.264")
        add(v and v.get("pix_fmt") == "yuv420p", "pixel format is yuv420p")
        r, avg = (fps(v.get("r_frame_rate")), fps(v.get("avg_frame_rate"))) if v else (None, None)
        add(r and avg and abs(r - avg) < 0.05, "constant frame rate (r_frame_rate matches avg_frame_rate)")
    if preset == "premiere":
        add(a and a.get("codec_name") == "aac", "audio is AAC")
        va, aa = (v or {}).get("duration"), (a or {}).get("duration")
        if va and aa:
            add(abs(float(va) - float(aa)) < 0.1, f"picture and sound stay in sync ({va} vs {aa})")
    if preset == "broll":
        add(a is None, "no sound track")
    if preset == "after_effects":
        add(ext == ".mov", "container is .mov")
        add(v and v.get("codec_name") == "prores", "video is ProRes")
        add(v and v.get("profile") == "Standard", "ProRes profile is 422 (Standard)")
        add(v and v.get("pix_fmt") == "yuv422p10le", "pixel format is yuv422p10le")
        add(a and a.get("codec_name") == "pcm_s16le", "audio is PCM")
    if preset == "audio":
        add(ext == ".wav", "file is .wav")
        add(v is None, "no picture in the file")
        add(a and a.get("codec_name") == "pcm_s16le", "audio is pcm_s16le")
        if "youtube" in link or "youtu" in link:
            add(a and a.get("sample_rate") == "48000" and a.get("channels") == 2, "48000 Hz, stereo")
    if preset == "original":
        add(v is not None and a is not None, "has both picture and sound")
        name = os.path.basename(path)
        add("_premiere" not in name and "_after_effects" not in name, "was not converted (no _premiere / _after_effects in the name)")
    return results


def main():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    durations = {}
    failures = []
    for label, link, preset in CASES:
        print("=" * 78)
        print(f"{label}   (preset: {preset})")
        folder = os.path.join(OUT, label)
        stages = []
        started = time.time()
        try:
            if link not in durations:
                durations[link] = get_info(link).get("duration")
            path = run_preset(link, preset, folder, on_progress=lambda e: stages.append(e["status"]))
        except EngineError as error:
            print(f"  FAIL  the job stopped: {error.friendly}")
            print(f"        details: {error.details[:300]}")
            failures.append(f"{label}: {error.friendly}")
            continue
        except Exception as error:
            print(f"  FAIL  unexpected error: {error}")
            failures.append(f"{label}: {error}")
            continue

        took = time.time() - started
        media = probe(path)
        print(f"  file  : {os.path.basename(path)}   (took {took:.0f} s, stages: {sorted(set(stages))})")
        for line in describe(media):
            print("  " + line)

        results = check(preset, link, path, media, durations.get(link))
        files_left = sorted(os.listdir(folder))
        results.append((len(files_left) == 1, f"only the finished file is left in the folder {files_left}"))
        for passed, text in results:
            print(f"  {'PASS' if passed else 'FAIL'}  {text}")
            if not passed:
                failures.append(f"{label}: {text}")

    print("=" * 78)
    if failures:
        print(f"{len(failures)} check(s) FAILED:")
        for item in failures:
            print("  - " + item)
    else:
        print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()