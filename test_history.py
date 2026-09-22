"""test_history.py - checks that finished downloads are remembered (Phase 7, Step 4).

Nothing is downloaded (a fake download stands in, like test_filing.py) and a temporary folder is
used, so your real data\\history.json is not touched.  Run:  python test_history.py"""

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from app import history, jobs, pipeline, settings

failures = []


def check(name, condition, extra=""):
    print(("PASS  " if condition else "FAIL  ") + name + (f"   -> {extra}" if not condition and extra else ""))
    if not condition:
        failures.append(name)


temp = Path(tempfile.mkdtemp(prefix="history_test_"))
settings.DATA_DIR = temp / "data"
settings.SETTINGS_FILE = settings.DATA_DIR / "settings.json"
history.DATA_DIR = temp / "data"
history.HISTORY_FILE = history.DATA_DIR / "history.json"
settings.reload_settings()

# ---------- history.py on its own ----------

check("no file yet -> empty list", history.list_entries() == [])

entry = history.add_entry(title="My Trip \U0001F334", url="https://www.youtube.com/watch?v=abc",
                          platform_name="youtube", preset_summary="Premiere ready",
                          path=str(temp / "somewhere" / "My Trip [abc]_premiere.mp4"))
check("add_entry returns the entry", entry["title"] == "My Trip \U0001F334" and entry["platform"] == "youtube")

listed = history.list_entries()
check("one entry now listed", len(listed) == 1)
check("entry has all the fields", all(key in listed[0] for key in
     ("title", "url", "platform", "preset", "path", "finished_at", "file_exists")))
check("file_exists is False for a file that was never made", listed[0]["file_exists"] is False)

# a file that IS there
real_file = temp / "real.mp4"
real_file.write_text("x")
history.add_entry(title="Second", url="https://x.com/a/status/1", platform_name="x",
                  preset_summary="Audio only", path=str(real_file))
listed = history.list_entries()
check("newest entry comes first", listed[0]["title"] == "Second")
check("file_exists is True for a file that is there", listed[0]["file_exists"] is True)
check("older entry is still there, in order", listed[1]["title"] == "My Trip \U0001F334")

# survives a "restart" (module-level cache-free design: just read again)
reread = history.list_entries()
check("reading again gives the same two entries", len(reread) == 2)

# no half-written files left behind
leftovers = [name for name in os.listdir(history.DATA_DIR) if name.endswith(".tmp")]
check("no temporary files left", leftovers == [], str(leftovers))

# cap at MAX_ENTRIES
history.clear_history()
check("clear_history empties the list", history.list_entries() == [])
check("clear_history does not touch the actual file", real_file.exists())
for i in range(history.MAX_ENTRIES + 10):
    history.add_entry(title=f"Video {i}", url=f"https://x.com/a/status/{i}", platform_name="x",
                      preset_summary="Audio only", path=str(temp / f"v{i}.mp3"))
capped = history.list_entries()
check(f"list is capped at {history.MAX_ENTRIES} entries", len(capped) == history.MAX_ENTRIES, str(len(capped)))
check("the most recent one is kept (not the oldest)", capped[0]["title"] == f"Video {history.MAX_ENTRIES + 9}")

# a broken file doesn't crash anything, just starts empty
history.HISTORY_FILE.write_text("{ not json", encoding="utf-8")
check("broken file -> empty list, no crash", history.list_entries() == [])
history.clear_history()

# ---------- open_folder (only checked structurally: no real Explorer/Finder here) ----------
missing = history.open_folder(str(temp / "nowhere" / "gone.mp4"))
check("open_folder returns False when nothing exists", missing is False)
folder_only = temp / "folder_only"
folder_only.mkdir()
found_folder = history.open_folder(str(folder_only / "gone.mp4"))
check("open_folder returns True when at least the folder exists", found_folder is True)

# ---------- through jobs.py: a finished job becomes a history entry ----------
SOURCE = temp / "source.mkv"
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=1",
                "-f", "lavfi", "-i", "sine=duration=1",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(SOURCE)],
               check=True)


def fake_download(url, preset_id, output_dir, on_progress=None, section=None, cancel=None,
                  work_dir=None, info_out=None):
    os.makedirs(work_dir, exist_ok=True)
    path = os.path.join(work_dir, "vidxyz.mkv")
    shutil.copy(SOURCE, path)
    if info_out is not None:
        info_out.update({"id": "vidxyz", "title": "Queue Test Video", "uploader": "Chan",
                        "platform": "youtube", "webpage_url": url, "duration": 1})
    return path


pipeline.download = fake_download
out_dir = temp / "queue_out"
jobs.DOWNLOAD_DIR = out_dir
job_id = jobs.start_job("https://www.youtube.com/watch?v=vidxyz", "premiere")
deadline = time.time() + 60
while time.time() < deadline and jobs.get_job(job_id)["status"] not in ("done", "error", "canceled"):
    time.sleep(0.2)
job = jobs.get_job(job_id)
check("fake job finished", job["status"] == "done", job.get("error"))

listed = history.list_entries()
check("finished job appears in history", len(listed) == 1 and listed[0]["title"] == "Queue Test Video")
check("history entry's path matches the job's finished file", listed[0]["path"] == job["path"])
check("history entry's file really exists", listed[0]["file_exists"] is True)
check("history entry has the right preset summary", "Premiere" in listed[0]["preset"])

# a canceled/failed job must NOT show up in history
from app.engine import EngineError


def failing_download(url, preset_id, output_dir, on_progress=None, section=None, cancel=None,
                     work_dir=None, info_out=None):
    raise EngineError("Couldn't read this video.", "simulated failure for the test")


history.clear_history()
pipeline.download = failing_download
bad_id = jobs.start_job("https://www.youtube.com/watch?v=badlink", "premiere")
deadline = time.time() + 30
while time.time() < deadline and jobs.get_job(bad_id)["status"] not in ("done", "error", "canceled"):
    time.sleep(0.2)
check("a failed job doesn't reach 'done'", jobs.get_job(bad_id)["status"] == "error")
check("a failed job is NOT recorded in history", history.list_entries() == [])

shutil.rmtree(temp, ignore_errors=True)
print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
raise SystemExit(1 if failures else 0)