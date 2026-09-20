"""test_queue.py - throwaway test for the download queue (Phase 6).

Adds six jobs at once and checks: they run in order, one at a time; a waiting job can be canceled; a running job
can be canceled; a bad link fails with a friendly message; canceled and failed jobs can be retried; and two
jobs can run together when that is allowed. Real links, real downloads.

Run from the downloader folder (venv active):   python test_queue.py
It writes into the folder test_queue_out (you can delete that folder afterwards). Takes about 3-4 minutes.
"""

import os
import shutil
import time
from pathlib import Path

import app.jobs as jobs
from app.presets import build_custom_preset

OUT = Path("test_queue_out").resolve()
YOUTUBE = "https://www.youtube.com/watch?v=_Sl8diqCAFw"
X_LINK = "https://x.com/PrettyCitiesX/status/2100991213621092475?s=20"
BAD_LINK = "https://www.youtube.com/watch?v=aaaaaaaaaaa"      # a video that does not exist
YOUTUBE_ID = "_Sl8diqCAFw"
X_ID = "2100991132930842624"    # the id yt-dlp uses in the file name of the X test video

results = []


def check(passed, text):
    results.append((bool(passed), text))
    print(f"  {'PASS' if passed else 'FAIL'}  {text}")


def state_line(names, ids):
    parts = []
    for name, job_id in zip(names, ids):
        job = jobs.get_job(job_id)
        parts.append(f"{name}:{job['status'][:5]}")
    return "  ".join(parts)


def run_until(ids, names, done, limit=300, on_tick=None):
    """Polls the queue, prints every change, and stops when done() is true. Returns the highest number of jobs that ran together."""
    started = time.time()
    last, most = "", 0
    while time.time() - started < limit:
        line = state_line(names, ids)
        if line != last:
            print(f"  {time.time() - started:5.1f} s   {line}")
            last = line
        active = sum(1 for job_id in ids if jobs.get_job(job_id)["status"] in ("downloading", "converting"))
        most = max(most, active)
        if on_tick:
            on_tick()
        if done():
            return most
        time.sleep(0.25)
    print("  TIMED OUT")
    return most


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    jobs.DOWNLOAD_DIR = OUT
    jobs.set_max_parallel(1)

    print("=" * 78)
    print("Part 1: six jobs at once, one at a time")
    print("  A X Premiere | B YouTube 720p Premiere | C bad link | D X audio | E YouTube audio | F YouTube 720p After Effects")
    a = jobs.start_job(X_LINK, "premiere")
    b = jobs.start_job(YOUTUBE, build_custom_preset("video_audio", 720, "premiere"))
    c = jobs.start_job(BAD_LINK, "premiere")
    d = jobs.start_job(X_LINK, "audio")
    e = jobs.start_job(YOUTUBE, "audio")
    f = jobs.start_job(YOUTUBE, build_custom_preset("video_audio", 720, "after_effects"))
    ids, names = [a, b, c, d, e, f], "ABCDEF"

    jobs.cancel_job(e)     # E is still waiting: it must be canceled at once and never start
    check(jobs.get_job(e)["status"] == "canceled", "E (waiting) was canceled at once")

    pressed = {}

    def cancel_f_while_converting():
        job = jobs.get_job(f)
        if job["status"] == "converting" and (job["percent"] or 0) >= 15 and "at" not in pressed:
            pressed["at"] = time.time()
            print("  >>> Cancel pressed on F (it is converting)")
            jobs.cancel_job(f)

    def all_over():
        return all(jobs.get_job(i)["status"] in ("done", "error", "canceled") for i in ids)

    most = run_until(ids, names, all_over, on_tick=cancel_f_while_converting)

    status = {name: jobs.get_job(job_id)["status"] for name, job_id in zip(names, ids)}
    check(most == 1, f"never more than one job ran at a time (highest: {most})")
    check(status["A"] == "done" and status["B"] == "done" and status["D"] == "done",
          f"A, B and D finished ({status})")
    check(status["C"] == "error", "C (bad link) failed")
    bad = jobs.get_job(c)["error"] or {}
    print(f"        friendly message for C: {bad.get('friendly')!r}")
    check(bool(bad.get("friendly")), "C has a friendly message")
    check(status["E"] == "canceled", "E stayed canceled")
    check(status["F"] == "canceled", "F (running) was canceled" if "at" in pressed
          else f"F ended as {status['F']} (it never reached the converting step)")
    started = {name: jobs.get_job(job_id)["started"] for name, job_id in zip(names, ids)}
    order = [name for name, when in sorted(started.items(), key=lambda item: item[1] or 0) if when]
    check(order == ["A", "B", "C", "D", "F"], f"jobs started in the order they were added {order} (E never started)")
    check(started["E"] is None, "E never started")
    titles = [jobs.get_job(i)["title"] for i in (a, b, d)]
    print(f"        titles seen: {titles}")
    check(all(titles), "the titles were filled in while downloading")
    check(not (OUT / "_working").exists(), "no _working folder left")
    for name in ("F",):
        check(not any("after_effects" in file for file in os.listdir(OUT)), "nothing half-made from F is left")

    print("=" * 78)
    print("Part 2: retry the canceled job (E) and the failed job (C)")
    jobs.retry_job(e)
    jobs.retry_job(c)
    check([job["id"] for job in jobs.list_jobs()][-2:] == [e, c], "retried jobs went to the back of the line")
    run_until([e, c], "EC", lambda: all(jobs.get_job(i)["status"] in ("done", "error", "canceled") for i in (e, c)))
    check(jobs.get_job(e)["status"] == "done", "E finished this time")
    check(jobs.get_job(c)["status"] == "error", "C failed again (the link is still bad, as expected)")

    print("=" * 78)
    print("Part 3: two at a time (limit set to 2)")
    jobs.set_max_parallel(2)
    g = jobs.start_job(X_LINK, "broll")
    h = jobs.start_job(YOUTUBE, build_custom_preset("video_only", 720, "premiere"))
    most = run_until([g, h], "GH", lambda: all(jobs.get_job(i)["status"] in ("done", "error", "canceled") for i in (g, h)))
    check(most == 2, f"two jobs ran together (highest: {most})")
    check(jobs.get_job(g)["status"] == "done" and jobs.get_job(h)["status"] == "done", "both finished")
    jobs.set_max_parallel(1)

    print("=" * 78)
    print("Part 4: clear finished")
    before = len(jobs.list_jobs())
    removed = jobs.clear_finished()
    left = [(job["status"]) for job in jobs.list_jobs()]
    check(left == ["error"], f"removed {removed} of {before}; only the failed job C is left ({left})")

    print("=" * 78)
    files = sorted(os.listdir(OUT))
    print("Files in the output folder:")
    for name in files:
        print("  " + name)
    expected = [f"{X_ID}_premiere.mp4", f"{YOUTUBE_ID}_720p_premiere.mp4", f"{X_ID}.wav", f"{YOUTUBE_ID}.wav",
                f"{X_ID}_broll.mp4", f"{YOUTUBE_ID}_720p_broll.mp4"]
    missing = [name for name in expected if name not in files]
    check(not missing, f"all expected files are there {('missing: ' + str(missing)) if missing else ''}")
    check(len(files) == len(expected), f"and nothing else ({len(files)} files)")

    print("=" * 78)
    failed = [text for passed, text in results if not passed]
    if failed:
        print(f"{len(failed)} check(s) FAILED:")
        for text in failed:
            print("  - " + text)
    else:
        print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()