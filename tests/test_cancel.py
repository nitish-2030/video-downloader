"""test_cancel.py - throwaway test. Starts jobs on real links, cancels them, and checks that everything stops
and that no half-made files or ffmpeg programs are left behind.

Run from the downloader folder (venv active):   python test_cancel.py
It writes into the folder test_cancel_out (you can delete that folder afterwards). Takes about 2-3 minutes.
"""

import os
import shutil
import subprocess
import threading
import time

from app.engine import Canceled, EngineError
from app.pipeline import run_preset
from app.presets import build_custom_preset

OUT = "test_cancel_out"
YOUTUBE = "https://www.youtube.com/watch?v=_Sl8diqCAFw"   # 16 s, up to 4K, so we ask for 720p to keep it small
X_LINK = "https://x.com/PrettyCitiesX/status/2100991213621092475?s=20"


def ffmpeg_running():
    """True if any ffmpeg program is running on this computer right now."""
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ffmpeg.exe", "/NH"],
                             capture_output=True, text=True).stdout
        return "ffmpeg.exe" in out.lower()
    return subprocess.run(["pgrep", "-x", "ffmpeg"], capture_output=True).returncode == 0


def fresh_folder():
    """Empties the test folder (tries again for a few seconds, Windows can hold a file for a moment)."""
    for _ in range(10):
        shutil.rmtree(OUT, ignore_errors=True)
        if not os.path.exists(OUT):
            break
        time.sleep(0.5)
    os.makedirs(OUT, exist_ok=True)


SKIPPED = []   # cases where the website itself refused the video before Cancel was pressed


def try_cancel(label, link, preset, when, section=None):
    """Runs a job, presses Cancel at the chosen moment, then checks the result. Returns a list of problems."""
    print("=" * 78)
    print(label)
    fresh_folder()

    cancel = threading.Event()
    marks = {}

    def press_cancel():
        if "at" not in marks:
            marks["at"] = time.time()
            cancel.set()

    def on_progress(event):
        if when == "first_progress" and event["status"] == "downloading":
            press_cancel()
        if when == "converting_20" and event["status"] == "converting" and (event["percent"] or 0) >= 20:
            press_cancel()

    if isinstance(when, (int, float)):
        threading.Timer(when, press_cancel).start()

    started = time.time()
    problems = []
    try:
        path = run_preset(link, preset, OUT, on_progress=on_progress, section=section, cancel=cancel)
        if "at" in marks:
            problems.append("Cancel was pressed but the job still finished")
            print(f"  FAIL  the job finished anyway: {os.path.basename(path)}")
        else:
            print("  NOTE  the job finished before the cancel moment (too fast); this case proves nothing")
            return problems
    except Canceled:
        stopped = time.time() - marks["at"]
        ok = stopped <= 12
        print(f"  {'PASS' if ok else 'FAIL'}  the job stopped {stopped:.1f} s after Cancel (limit 12 s)")
        if not ok:
            problems.append(f"{label}: stopping took {stopped:.1f} s")
    except EngineError as error:
        print(f"  details: {error.details[:200]}")
        if "at" not in marks:
            # The website refused the video before we pressed Cancel, so this case can't test anything.
            print("  SKIP  the website refused the video, not a cancel problem. Run the test again later.")
            SKIPPED.append(label)
            return []
        print(f"  FAIL  the job stopped with an error instead of Canceled: {error.friendly}")
        return [f"{label}: {error.friendly}"]

    time.sleep(1.0)
    left = sorted(os.listdir(OUT))
    print(f"  {'PASS' if not left else 'FAIL'}  no files or folders left behind {left if left else ''}")
    if left:
        problems.append(f"{label}: left behind {left}")
    running = ffmpeg_running()
    print(f"  {'PASS' if not running else 'FAIL'}  no ffmpeg program still running")
    if running:
        problems.append(f"{label}: ffmpeg is still running")
    return problems


def main():
    premiere_720 = build_custom_preset("video_audio", 720, "premiere")
    after_effects_720 = build_custom_preset("video_audio", 720, "after_effects")
    original_720 = build_custom_preset("video_audio", 720, "original")

    problems = []
    problems += try_cancel("YouTube 720p, Premiere ready: cancel at the first download progress",
                           YOUTUBE, premiere_720, "first_progress")
    problems += try_cancel("YouTube 720p, only a section (2-8 s): cancel after 4 s",
                           YOUTUBE, premiere_720, 4, section=(2.0, 8.0))
    problems += try_cancel("YouTube 720p, only a section (2-8 s): cancel after 10 s",
                           YOUTUBE, premiere_720, 10, section=(2.0, 8.0))
    problems += try_cancel("YouTube 720p, After Effects ready: cancel while converting (at 20%)",
                           YOUTUBE, after_effects_720, "converting_20")
    problems += try_cancel("YouTube 720p, Original: cancel at the first download progress",
                           YOUTUBE, original_720, "first_progress")
    problems += try_cancel("X, Premiere ready: cancel after 3 s",
                           X_LINK, "premiere", 3)

    print("=" * 78)
    print("After all the cancels, a normal download still works")
    fresh_folder()
    try:
        path = run_preset(YOUTUBE, "audio", OUT)
        left = sorted(os.listdir(OUT))
        ok = left == [os.path.basename(path)]
        print(f"  {'PASS' if ok else 'FAIL'}  only the finished file is in the folder {left}")
        if not ok:
            problems.append(f"normal run: folder has {left}")
    except EngineError as error:
        print(f"  SKIP  the website refused the video: {error.details[:150]}")
        SKIPPED.append("normal download after the cancels")
    except Exception as error:
        print(f"  FAIL  {error}")
        problems.append(f"normal run: {error}")

    print("=" * 78)
    if problems:
        print(f"{len(problems)} problem(s):")
        for item in problems:
            print("  - " + item)
    elif SKIPPED:
        print(f"No failures, but {len(SKIPPED)} case(s) were skipped because the website refused the video:")
        for item in SKIPPED:
            print("  - " + item)
        print("Run the test again later to cover them.")
    else:
        print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()