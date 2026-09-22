"""test_filing.py - checks where finished files land and what they are called (Phase 7, Step 3).

Nothing is downloaded: a tiny fake video is made with ffmpeg and used instead of a real download,
so this runs in about a minute, needs no internet, and touches only a temporary folder.
Run:  python test_filing.py
"""

import os
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import date
from pathlib import Path

from app import engine, jobs, pipeline, settings
from app.engine import Canceled, quality_label

failures = []


def check(name, condition, extra=""):
    print(("PASS  " if condition else "FAIL  ") + name + (f"   -> {extra}" if not condition and extra else ""))
    if not condition:
        failures.append(name)


TODAY = date.today().strftime("%Y-%m-%d")
temp = Path(tempfile.mkdtemp(prefix="filing_test_"))
settings.DATA_DIR = temp / "data"
settings.SETTINGS_FILE = settings.DATA_DIR / "settings.json"
settings.reload_settings()

# One tiny source video (2 seconds, picture + sound), copied for every fake download.
SOURCE = temp / "source.mkv"
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=2",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(SOURCE)],
               check=True)

INFO = {"id": "vid123", "title": "Test Video: Goa \U0001F334 trip", "uploader": "Some Channel",
        "platform": "youtube", "webpage_url": "https://www.youtube.com/watch?v=vid123", "duration": 2}
FAKE = {"info": dict(INFO), "cancel_after_download": None}


def fake_download(url, preset_id, output_dir, on_progress=None, section=None, cancel=None,
                  work_dir=None, info_out=None):
    """Stands in for engine.download: same file naming, no internet."""
    preset = pipeline.resolve_preset(preset_id)
    info = FAKE["info"]
    name = info["id"]
    if preset.get("quality"):
        name += "_" + quality_label(preset["quality"])
    if section:
        name += f"_section_{engine._time_tag(section[0])}-{engine._time_tag(section[1])}"
    os.makedirs(work_dir, exist_ok=True)
    path = os.path.join(work_dir, name + ".mkv")
    shutil.copy(SOURCE, path)
    if info_out is not None:
        info_out.update(info)
    if FAKE["cancel_after_download"] is not None:
        FAKE["cancel_after_download"].set()
    return path


pipeline.download = fake_download


def run(preset, out, section=None, organize=True, cancel=None):
    """Runs one job the way the queue does. Returns the final path."""
    plan = None
    times = None
    if section:
        plan = {"start": section[0], "end": section[1], "padded_start": max(0, section[0] - 2), "padded_end": section[1] + 2}
        times = (plan["padded_start"], plan["padded_end"])
    summary = preset if isinstance(preset, str) else preset.get("summary", "Custom")
    if isinstance(preset, str):
        summary = pipeline.resolve_preset(preset)["name"]
    return pipeline.run_preset("https://www.youtube.com/watch?v=vid123", preset, str(out), section=times,
                               cancel=cancel, organize={"summary": summary, "section": plan} if organize else None)


def tree(folder):
    return sorted(str(p.relative_to(folder)) for p in Path(folder).rglob("*") if p.is_file())


# 1. Premiere ready ------------------------------------------------------------
out = temp / "out1"
final = run("premiere", out)
folder = out / "YouTube" / TODAY
check("premiere: file is in Platform/date", Path(final).parent == folder, final)
check("premiere: clean name (no emoji or colon, id in brackets)",
      Path(final).name == "Test Video Goa trip [vid123]_premiere.mp4", Path(final).name)
check("premiere: the file exists and has data", os.path.getsize(final) > 1000)
side = Path(final + ".source.txt")
check("premiere: source-info file is next to it", side.exists())
text = side.read_text(encoding="utf-8-sig") if side.exists() else ""
check("source info has title, uploader, link, id, what was asked",
      all(part in text for part in ("Test Video: Goa", "Some Channel", "watch?v=vid123", "vid123", "Premiere ready")), text)
check("premiere: working folder is gone", not (out / "_working").exists())
check("premiere: only the video and its info file exist", len(tree(out)) == 2, str(tree(out)))

# 2. Same job again -> (2) ------------------------------------------------------
second = run("premiere", out)
check("duplicate gets (2)", Path(second).name == "Test Video Goa trip [vid123]_premiere (2).mp4", Path(second).name)
check("duplicate has its own info file", Path(second + ".source.txt").exists())
check("first file was not touched", os.path.exists(final))

# 3. Audio: WAV and MP3 of one video do not clash --------------------------------
wav = run("audio", out)
mp3 = run({"name": "Custom", "content": "audio_only", "treatment": None, "audio_format": "mp3",
           "warning": None, "quality": None, "label": None, "summary": "Custom: Sound only \u00b7 MP3"}, out)
check("wav name", Path(wav).name == "Test Video Goa trip [vid123].wav", Path(wav).name)
check("mp3 name", Path(mp3).name == "Test Video Goa trip [vid123].mp3", Path(mp3).name)
check("wav and mp3 each have their own info file", Path(wav + ".source.txt").exists() and Path(mp3 + ".source.txt").exists())

# 4. B-roll, Original, After Effects -----------------------------------------------
broll = run("broll", out)
check("broll name", Path(broll).name == "Test Video Goa trip [vid123]_broll.mp4", Path(broll).name)
original = run("original", out)
check("original name (mkv kept, no conversion word)", Path(original).name == "Test Video Goa trip [vid123].mkv", Path(original).name)
check("original: working folder is gone", not (out / "_working").exists())
ae = run("after_effects", out)
check("after effects name", Path(ae).name == "Test Video Goa trip [vid123]_after_effects.mov", Path(ae).name)

# 5. Custom 720p keeps its extras in the name ------------------------------------------
custom = pipeline.resolve_preset("premiere").copy()
custom.update({"name": "Custom", "quality": 720, "label": None, "summary": "Custom: Video with sound \u00b7 720p \u00b7 Premiere ready"})
c720 = run(custom, out)
check("custom 720p name", Path(c720).name == "Test Video Goa trip [vid123]_720p_premiere.mp4", Path(c720).name)

# 6. Section: extras in the name and the info file says which part ---------------------
sec = run("premiere", out, section=(3, 6))
check("section name", Path(sec).name == "Test Video Goa trip [vid123]_section_1-8_premiere.mp4", Path(sec).name)
stext = Path(sec + ".source.txt").read_text(encoding="utf-8-sig")
check("info file has the section", "Section:   0:03 to 0:06 (saved 0:01 to 0:08" in stext, stext)

# 7. X post: folder X, poster's name in front, link and emoji gone ---------------------------
FAKE["info"] = {"id": "2100991213621092475", "title": "a nice view \U0001F525 https://t.co/abc", "uploader": "PrettyCitiesX",
                "platform": "x", "webpage_url": "https://x.com/PrettyCitiesX/status/2100991213621092475", "duration": 2}
xfile = run("premiere", out)
check("X: goes to the X folder", Path(xfile).parent == out / "X" / TODAY, xfile)
check("X: name is poster - text", Path(xfile).name == "PrettyCitiesX - a nice view [2100991213621092475]_premiere.mp4", Path(xfile).name)
FAKE["info"] = dict(INFO)

# 8. Cancel: nothing is left behind -----------------------------------------------------------
out8 = temp / "out8"
flag = threading.Event()
FAKE["cancel_after_download"] = flag
try:
    run("premiere", out8, cancel=flag)
    check("cancel raises Canceled", False, "no error")
except Canceled:
    check("cancel raises Canceled", True)
FAKE["cancel_after_download"] = None
check("cancel leaves no files or folders", not out8.exists() or tree(out8) == [], str(tree(out8)) if out8.exists() else "")
check("cancel leaves no empty platform folder", not (out8 / "YouTube").exists())

# 9. Moving the file fails: the claimed name is given back ------------------------------------
out9 = temp / "out9"
real_replace, real_copy = os.replace, shutil.copy2


def boom(*args, **kwargs):
    raise PermissionError("simulated: file is locked")


os.replace, shutil.copy2 = boom, boom
try:
    run("premiere", out9)
    check("failed move raises an error", False, "no error")
except PermissionError:
    check("failed move raises an error", True)
finally:
    os.replace, shutil.copy2 = real_replace, real_copy
check("failed move leaves no empty claimed file", not out9.exists() or tree(out9) == [], str(tree(out9)) if out9.exists() else "")

# 10. The old way still works (organize off) -----------------------------------------------------------
out10 = temp / "out10"
old = run("premiere", out10, organize=False)
check("old way: flat file with the id name", Path(old) == out10 / "vid123_premiere.mp4", old)

# 11. Through the queue (jobs.py) ----------------------------------------------------------------------------
out11 = temp / "out11"
jobs.DOWNLOAD_DIR = out11
settings.update_settings({"parallel_downloads": 3})
jobs.apply_settings()
check("settings: 3 downloads at once reach the queue", jobs.get_max_parallel() == 3, str(jobs.get_max_parallel()))
ids = [jobs.start_job("https://www.youtube.com/watch?v=vid123", "premiere") for _ in range(3)]
deadline = time.time() + 120
while time.time() < deadline and any(jobs.get_job(i)["status"] not in ("done", "error", "canceled") for i in ids):
    time.sleep(0.3)
done = [jobs.get_job(i) for i in ids]
check("3 identical jobs all finish", all(job["status"] == "done" for job in done), str([j["status"] for j in done]))
paths = [job["path"] for job in done]
check("3 identical jobs get 3 different files", len(set(paths)) == 3 and all(os.path.exists(p) for p in paths), str(paths))
check("job knows title, platform, folder and file",
      done[0]["title"] == INFO["title"] and done[0]["platform"] == "youtube"
      and done[0]["folder"] == str(Path(done[0]["path"]).parent) and done[0]["file"] == Path(done[0]["path"]).name)
check("queue leaves no working folder", not (out11 / "_working").exists())

shutil.rmtree(temp, ignore_errors=True)
print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
raise SystemExit(1 if failures else 0)