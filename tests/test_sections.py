"""test_sections.py - throwaway test. Downloads sections on real links and checks length and names.

Run from the downloader folder (venv active):   python test_sections.py
It writes into the folder test_sections_out (you can delete that folder afterwards).
All clips go into ONE folder on purpose, to prove that different sections of one video don't overwrite each other.
"""

import json
import os
import shutil
import subprocess
import time

from app.engine import EngineError, get_info, plan_section
from app.pipeline import run_preset
from app.presets import build_custom_preset

OUT = "test_sections_out"
YOUTUBE = "https://www.youtube.com/watch?v=xuP4g7IDgDM"
X_LINK = "https://x.com/PrettyCitiesX/status/2100991213621092475?s=20"

# (label, link, preset id or custom choices, start, end, extra seconds, what we expect)
CASES = [
    ("yt near the START   0-3 s, extra 2", YOUTUBE, "premiere", "0", "3", 2,
     {"ext": ".mp4", "vcodec": "h264", "acodec": "aac"}),
    ("yt near the END     6-9 s, extra 2", YOUTUBE, "premiere", "6", "9", 2,
     {"ext": ".mp4", "vcodec": "h264", "acodec": "aac"}),
    ("yt VERY SHORT       3-5 s, extra 0", YOUTUBE, "premiere", "3", "5", 0,
     {"ext": ".mp4", "vcodec": "h264", "acodec": "aac"}),
    ("yt custom 360p video only 2-6 s, extra 1", YOUTUBE, build_custom_preset("video_only", 360, "premiere"),
     "2", "6", 1, {"ext": ".mp4", "vcodec": "h264", "acodec": None, "side": 360}),
    ("yt audio (WAV)      2-5 s, extra 1", YOUTUBE, "audio", "2", "5", 1,
     {"ext": ".wav", "no_video": True, "acodec": "pcm_s16le"}),
    ("x  in the middle    3-8 s, extra 2", X_LINK, "premiere", "3", "8", 2,
     {"ext": ".mp4", "vcodec": "h264", "acodec": "aac"}),
    ("x  near the END     12-15 s, extra 2", X_LINK, "premiere", "12", "15", 2,
     {"ext": ".mp4", "vcodec": "h264", "acodec": "aac"}),
]

# Times that must be refused with a friendly message (video length 9 s). No download happens here.
BAD_TIMES = [
    ("start after end", "5", "3", 2),
    ("start equals end", "4", "4", 2),
    ("not a time", "abc", "5", 2),
    ("empty start", "", "5", 2),
    ("start past the end of the video", "20", "25", 2),
    ("end past the end of the video", "3", "40", 2),
]


def probe(path):
    command = ["ffprobe", "-v", "error", "-show_entries",
               "stream=codec_type,codec_name,width,height:format=duration,size",
               "-of", "json", path]
    data = json.loads(subprocess.run(command, capture_output=True, text=True, check=True).stdout)
    streams = data.get("streams", [])
    return {
        "video": next((s for s in streams if s.get("codec_type") == "video"), None),
        "audio": next((s for s in streams if s.get("codec_type") == "audio"), None),
        "duration": float(data["format"].get("duration") or 0),
        "size": int(data["format"].get("size") or 0),
    }


def check(path, media, expect, wanted_length):
    v, a = media["video"], media["audio"]
    name = os.path.basename(path)
    results = []

    def add(passed, text):
        results.append((bool(passed), text))

    add(media["size"] > 0, "file is not empty")
    add(abs(media["duration"] - wanted_length) <= 0.25,
        f"length is {wanted_length:.2f} s (got {media['duration']:.2f} s)")
    add("_section_" in name, "name has the section times in it")
    add(os.path.splitext(name)[1].lower() == expect["ext"], f"file type is {expect['ext']}")
    if expect.get("no_video"):
        add(v is None, "no picture in the file")
    if "vcodec" in expect:
        add(v and v.get("codec_name") == expect["vcodec"], f"picture is {expect['vcodec']}")
    if "side" in expect and v:
        add(min(v["width"], v["height"]) == expect["side"], f"short side is {expect['side']}")
    if "acodec" in expect:
        if expect["acodec"] is None:
            add(a is None, "no sound track")
        else:
            add(a and a.get("codec_name") == expect["acodec"], f"sound is {expect['acodec']}")
    return results


def main():
    failures = []

    print("=" * 78)
    print("Refused times (no download)")
    for label, start, end, extra in BAD_TIMES:
        try:
            plan_section(start, end, extra, 9)
            print(f"  FAIL  {label}: was accepted")
            failures.append(f"bad times: {label} was accepted")
        except EngineError as error:
            print(f"  PASS  {label}: \"{error.friendly}\"")

    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    durations = {}
    names = []
    for label, link, preset, start, end, extra, expect in CASES:
        print("=" * 78)
        print(label)
        started = time.time()
        try:
            if link not in durations:
                durations[link] = get_info(link).get("duration")
            plan = plan_section(start, end, extra, durations[link])
            section = (plan["padded_start"], plan["padded_end"])
            wanted = section[1] - section[0]
            print(f"  video length {durations[link]} s   asked {start}-{end} s + {extra} s extra"
                  f"   -> will download {section[0]:.2f} to {section[1]:.2f} s")
            path = run_preset(link, preset, OUT, section=section)
        except EngineError as error:
            print(f"  FAIL  the job stopped: {error.friendly}")
            print(f"        details: {error.details[:300]}")
            failures.append(f"{label}: {error.friendly}")
            continue
        except Exception as error:
            print(f"  FAIL  unexpected error: {error}")
            failures.append(f"{label}: {error}")
            continue

        names.append(os.path.basename(path))
        media = probe(path)
        print(f"  file  : {os.path.basename(path)}   (took {time.time() - started:.0f} s)")
        for passed, text in check(path, media, expect, wanted):
            print(f"  {'PASS' if passed else 'FAIL'}  {text}")
            if not passed:
                failures.append(f"{label}: {text}")

    print("=" * 78)
    left = sorted(os.listdir(OUT))
    print("Files in the folder:")
    for item in left:
        print("  " + item)
    folder_ok = len(left) == len(names) == len(set(names)) and "_working" not in left
    print(f"{'PASS' if folder_ok else 'FAIL'}  every clip has its own file, nothing overwritten, no _working folder left")
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