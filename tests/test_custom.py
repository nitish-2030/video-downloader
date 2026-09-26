"""test_custom.py - throwaway test. Runs custom choices on real links, checks every file with ffprobe.

Run from the downloader folder (venv active):   python test_custom.py
It writes into the folder test_custom_out (you can delete that folder afterwards).
All cases go into ONE folder on purpose, to prove that files of the same video don't overwrite each other.
"""

import json
import os
import shutil
import subprocess
import time

from app.engine import EngineError
from app.pipeline import run_preset
from app.presets import build_custom_preset

OUT = "test_custom_out"
YOUTUBE = "https://www.youtube.com/watch?v=xuP4g7IDgDM"
X_LINK = "https://x.com/PrettyCitiesX/status/2100991213621092475?s=20"

# (label, link, preset id or custom choices, what we expect)
CASES = [
    ("yt preset Premiere", YOUTUBE, "premiere",
     {"ext": ".mp4", "vcodec": "h264", "acodec": "aac", "name_end": "_premiere.mp4"}),
    ("yt preset B-roll", YOUTUBE, "broll",
     {"ext": ".mp4", "vcodec": "h264", "acodec": None, "name_end": "_broll.mp4"}),
    ("yt preset Original", YOUTUBE, "original",
     {"ext": ".mkv", "has_video": True, "has_audio": True}),
    ("yt custom: sound + 720p + Premiere", YOUTUBE, build_custom_preset("video_audio", 720, "premiere"),
     {"ext": ".mp4", "vcodec": "h264", "acodec": "aac", "side": 720, "name_end": "_720p_premiere.mp4"}),
    ("yt custom: sound + 480p + Original", YOUTUBE, build_custom_preset("video_audio", 480, "original"),
     {"ext": ".mkv", "has_video": True, "has_audio": True, "side": 480, "name_end": "_480p.mkv"}),
    ("yt custom: video only + 360p + Premiere", YOUTUBE, build_custom_preset("video_only", 360, "premiere"),
     {"ext": ".mp4", "vcodec": "h264", "acodec": None, "side": 360, "name_end": "_360p_broll.mp4"}),
    ("yt custom: video only + 360p + Original", YOUTUBE, build_custom_preset("video_only", 360, "original"),
     {"has_video": True, "acodec": None, "side": 360, "name_has": "_360p_nosound"}),
    ("yt custom: sound only + MP3", YOUTUBE, build_custom_preset("audio_only", None, "premiere", "mp3"),
     {"ext": ".mp3", "no_video": True, "acodec": "mp3", "mp3_320": True}),
    ("x custom: sound + 480p + Premiere", X_LINK, build_custom_preset("video_audio", 480, "premiere"),
     {"ext": ".mp4", "vcodec": "h264", "acodec": "aac", "side": 480, "name_end": "_480p_premiere.mp4"}),
]


def probe(path):
    command = ["ffprobe", "-v", "error", "-show_entries",
               "stream=codec_type,codec_name,width,height,bit_rate:format=duration,size",
               "-of", "json", path]
    data = json.loads(subprocess.run(command, capture_output=True, text=True, check=True).stdout)
    streams = data.get("streams", [])
    return {
        "video": next((s for s in streams if s.get("codec_type") == "video"), None),
        "audio": next((s for s in streams if s.get("codec_type") == "audio"), None),
        "duration": float(data["format"].get("duration") or 0),
        "size": int(data["format"].get("size") or 0),
    }


def describe(media):
    v, a = media["video"], media["audio"]
    picture = f"{v.get('codec_name')} {v.get('width')}x{v.get('height')}" if v else "none"
    sound = a.get("codec_name") if a else "none"
    return f"picture: {picture}   sound: {sound}   length: {media['duration']:.2f} s   size: {media['size'] / 1_000_000:.1f} MB"


def check(path, media, expect):
    v, a = media["video"], media["audio"]
    name = os.path.basename(path)
    results = []

    def add(passed, text):
        results.append((bool(passed), text))

    add(media["size"] > 0, "file is not empty")
    if "ext" in expect:
        add(os.path.splitext(name)[1].lower() == expect["ext"], f"file type is {expect['ext']}")
    if "name_end" in expect:
        add(name.endswith(expect["name_end"]), f"name ends with {expect['name_end']}")
    if "name_has" in expect:
        add(expect["name_has"] in name, f"name contains {expect['name_has']}")
    if expect.get("has_video"):
        add(v is not None, "has a picture")
    if expect.get("no_video"):
        add(v is None, "no picture in the file")
    if "vcodec" in expect:
        add(v and v.get("codec_name") == expect["vcodec"], f"picture is {expect['vcodec']}")
    if "side" in expect and v:
        side = min(v["width"], v["height"])
        add(side == expect["side"], f"short side is {expect['side']} (got {v['width']}x{v['height']})")
    if expect.get("has_audio"):
        add(a is not None, "has sound")
    if "acodec" in expect:
        if expect["acodec"] is None:
            add(a is None, "no sound track")
        else:
            add(a and a.get("codec_name") == expect["acodec"], f"sound is {expect['acodec']}")
    if expect.get("mp3_320"):
        rate = int((a or {}).get("bit_rate") or 0)
        add(315_000 <= rate <= 325_000, f"MP3 is about 320 kbps (got {rate // 1000} kbps)")
    return results


def main():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    failures = []
    names = []
    for label, link, preset, expect in CASES:
        print("=" * 78)
        print(label)
        started = time.time()
        try:
            path = run_preset(link, preset, OUT)
        except EngineError as error:
            print(f"  FAIL  the job stopped: {error.friendly}")
            print(f"        details: {error.details[:300]}")
            failures.append(f"{label}: {error.friendly}")
            continue
        except Exception as error:
            print(f"  FAIL  unexpected error: {error}")
            failures.append(f"{label}: {error}")
            continue

        media = probe(path)
        names.append(os.path.basename(path))
        print(f"  file  : {os.path.basename(path)}   (took {time.time() - started:.0f} s)")
        print("  " + describe(media))
        for passed, text in check(path, media, expect):
            print(f"  {'PASS' if passed else 'FAIL'}  {text}")
            if not passed:
                failures.append(f"{label}: {text}")

    print("=" * 78)
    left = sorted(os.listdir(OUT))
    print("Files in the folder:")
    for item in left:
        print("  " + item)
    folder_ok = len(left) == len(names) == len(set(names)) and "_working" not in left
    print(f"{'PASS' if folder_ok else 'FAIL'}  every job left its own file, nothing was overwritten, no _working folder left")
    if not folder_ok:
        failures.append("folder: files were overwritten or a leftover remained")

    print("=" * 78)
    if failures:
        print(f"{len(failures)} check(s) FAILED:")
        for item in failures:
            print("  - " + item)
    else:
        print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()