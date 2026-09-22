# Video Downloader for Editors — PROGRESS.md

**Read this whole file first.** Then read the code (see "File map" below). Then reply with a short
summary of what you understood and what you'll do next, BEFORE writing any code. The user (owner)
will confirm or correct you, then say "go ahead".

Project folder (Windows): `C:\Users\nitis\downloader`
Log date of this file: 2026-09-22
Communication style: the owner writes in Hindi/English mix (Hinglish). Reply in the same style —
short, clear, no fluff.

**IMPORTANT — who the owner is:** the owner (nitish) IS a coder/developer — he is building this
tool himself. He is NOT the end user. The **end user is a video editor** (could be nitish himself
wearing an editor hat sometimes, or someone else / a client he's building this for — unclear which,
doesn't matter much yet since it's single-player for now). So:
- You CAN talk to the owner in technical/coder terms — code, trade-offs, architecture, "why" at an
  engineering level. No need to dumb things down for him.
- But every FEATURE decision should still be judged from the **end editor's workflow** ("does a
  video editor actually need this while downloading/editing clips"), not from what's
  technically neat. This is why History almost got cut — it was evaluated against "what does an
  editor actually do with this", not "wouldn't it be nice to log everything".
- Don't over-engineer; only build what's actually useful for an editor's real download → edit →
  delete workflow. When proposing a feature, briefly justify it in terms of the editor's workflow,
  not just "for completeness".

---

## 1. WHAT THIS PROJECT IS

A **local tool** (not a website — runs only on the owner's own PC via `127.0.0.1`, not exposed to
the internet) that lets a video editor paste a YouTube or X (Twitter) link and get back
edit-ready files: original download, B-roll (no sound), audio only, a Premiere-ready MP4, or an
After Effects–ready ProRes MOV. Also supports downloading just a section of a video (with a bit
of extra padding at each end for clean cuts) and a queue so several links can be downloaded at once.

Currently a Python script the owner runs with `uvicorn` and opens in Chrome. **Not yet an .exe** —
that's Phase 10 (Packaging). Until then, correctly call it a "local tool", not "website" or "app".

## 2. THE MASTER PLAN — 12 PHASES

The whole build follows a **Master Build Brief** (uploaded once, not repeated here) with 12 phases,
0 through 11. Status as of this file:

| Phase | What it is | Status |
|---|---|---|
| 0 | Setup & checks (Python, yt-dlp, ffmpeg, Deno) | DONE |
| 1 | Manual media test in an editor (CapCut used; Premiere/AE not installed) | DONE (Premiere/AE confirmation still pending from client) |
| 2 | Core engine in Python (`engine.py`, `presets.py`, `convert.py`, `pipeline.py`) | DONE |
| 3 | Local server + first web page (`main.py`, `web/`) | DONE |
| 4 | Presets shown on the page + custom mode (quality/format dropdowns) | DONE |
| 5 | Timeline / section-download UI (`section.js`) | DONE |
| 6 | Queue, progress bars, batch (paste many links), cancel/retry | DONE, tested, committed |
| 7 | **Output folders, file naming, history, settings** | **IN PROGRESS — see section 4** |
| 8 | Errors (incl. "sign in to confirm you're not a bot"), auto-updates, YouTube login/cookies, disk space checks | NOT STARTED |
| 9 | Full testing (big videos, 4K, long sections, real Premiere/AE confirmation) | NOT STARTED |
| 10 | Packaging into a distributable .exe / installer | NOT STARTED |
| 11 | Browser extension button (extra/nice-to-have) | NOT STARTED |

Each phase is broken into small numbered Steps by whoever is driving (the AI). After each step:
write test(s), run them, only move on once they pass, then update this file.

## 3. HOW WE WORK (process — follow this)

1. One step at a time. Never jump ahead or bundle multiple steps into one giant change.
2. For every code change, also write/update a `test_*.py` in the project root that proves it works,
   **without needing real internet/YouTube/X access** wherever possible (use a tiny local ffmpeg-made
   fake video standing in for a "download" — see `test_filing.py` for the pattern). Real-download
   tests are reserved for a final check per phase, since YouTube sometimes blocks the sandbox
   ("Sign in to confirm you're not a bot" — this is a known intermittent yt-dlp/YouTube issue, not
   a bug in our code; retry, or use the X link, or wait).
3. Give the owner: the changed/new files, the test file, exact commands to run, and what output to
   expect. The owner runs it on their real Windows machine (the assistant's own sandbox has no
   internet access to YouTube/X, only local Python + ffmpeg — so sandbox tests must be offline).
4. Owner pastes back real output. Compare against expected. Fix if needed.
5. Only once a step's tests pass on the owner's machine, move to the next step.
6. At the end of a whole Phase: one end-to-end manual test pass (like Phase 6's A–H list), then
   `git add -A && git commit -m "..."`, then `git push`.
7. Update this PROGRESS.md after each meaningful step (not necessarily after every tiny edit).

## 4. PHASE 7 — DETAILED STATUS (current phase)

Goal: decide where files are saved and what they're named, remember settings between runs, and
remember what was downloaded before (history), with a way to see/manage both from the page.

### Steps

- **Step 0 — Planning.** DONE. Read old code, brief, and a very old BUILD_LOG. Asked the owner for
  defaults (naming format, folder layout, etc.) and diagnostic commands. Owner accepted defaults
  as proposed (see section 5).
- **Step 1 — `app/settings.py` + `GET/PUT /api/settings`.** DONE, tested, owner confirmed via
  FastAPI `/docs` (all 4 manual checks passed) and `test_settings.py` (ALL PASSED).
  - Settings stored in `data/settings.json` (already gitignored). Safe write (temp file +
    `os.replace`, never leaves a half-written file).
  - Four settings: `output_folder`, `default_preset`, `extra_seconds`, `parallel_downloads`
    (allowed 1–4).
  - Validated with friendly error messages + `details` field (for a "Show details" toggle,
    consistent with how download errors are already shown per Phase 6).
  - A broken/missing settings file silently falls back to defaults; one bad key in an otherwise
    good file falls back only for that key.
- **Step 2 — `app/naming.py`.** DONE, tested (`test_naming.py`, 48 PASS), owner confirmed no
  changes needed.
  - Cleans a title for use in a filename: strips Windows-illegal characters, emoji (by Unicode
    category, not a hardcoded emoji list — so new emoji are handled too), links (X posts end with
    a t.co link); keeps all non-Latin scripts (Hindi etc.) including combining marks;
    cuts to 80 chars at a word boundary without breaking a multi-codepoint letter.
  - `display_title()`: X has no real "title" (it's the post text), so we prefix the poster's name:
    `"PrettyCitiesX - post text"`.
  - `plan_output()`: decides folder = `<output_folder>/<YouTube|X>/<YYYY-MM-DD>/` (date = day of
    download) and filename = `<clean title> [<video id>]<variant>` where variant is things like
    `_premiere`, `_broll`, `_720p_section_1-8_after_effects`, taken from the existing filename
    suffix logic in engine/pipeline.
  - Shrinks the title further if the full path would approach Windows' ~260-char limit.
  - `reserve_path()`: picks a free name, avoiding both existing media files AND existing
    `.source.txt` sidecar files, adding `(2)`, `(3)`... on collision. Thread-safe (uses a lock +
    atomically creates an empty placeholder file) so two simultaneous queue jobs never collide.
- **Step 3 — Wire naming + settings into the real download pipeline.** DONE, tested
  (`test_filing.py`, offline with fake ffmpeg video, 33 PASS), owner confirmed with one real
  download (X, audio-only) — filename and `.source.txt` content look correct.
  - `engine.download()` gained an optional `info_out` dict param that gets filled with id, title,
    uploader, platform, webpage_url, duration — backward compatible (old callers/tests unaffected).
  - `pipeline.run_preset()` gained optional `organize` (dict with `summary` + `section` plan) and
    `info_out` params. When `organize` is given: conversion happens in a working folder, then the
    finished file is moved (`os.replace`, falls back to copy+delete across drives) into its final
    `naming.plan_output()` location, and a `.source.txt` sidecar is written next to it (title,
    uploader, link, platform, video id, saved-on timestamp, what preset/summary was used, and the
    section timing if any). If `organize` is omitted, old flat-in-output-dir behavior is preserved
    (kept for backward compat / any old test scripts).
  - On any failure during the move, the reserved placeholder filename is deleted (no ghost 0-byte
    files left behind).
  - `jobs.py`: `DOWNLOAD_DIR` is now `None` by default, meaning "use `settings.get_settings()
    ['output_folder']`" via a new `output_dir()` helper — but test scripts can still override
    `jobs.DOWNLOAD_DIR` directly to point at a temp folder (kept for compatibility with existing
    test files like `test_queue.py`, `test_cancel.py` etc. — **not yet verified these older tests
    still pass after this change; should double check in a step soon**).
  - `jobs.MAX_PARALLEL` is now set from settings via `apply_settings()`, called at server startup
    and again right after any successful `PUT /api/settings`.
  - Each job dict now also carries `platform`, `video_id`, and `path` (full final file path) —
    used by the page to show "Saved as ... [folder]" and will be needed for the History feature
    (Step 4) and for an "Open folder" button.
  - **Known non-bug quirk (owner already saw this, noted here so it isn't "fixed" by mistake):**
    for X links, the filename uses the **video's own id** (from yt-dlp), which differs from the
    **post id** that's in the URL. E.g. filename had `2100991132930842624`, but the link is
    `.../status/2100991213621092475`. Both are correct — different things. Owner was told this and
    has NOT yet decided whether to change naming to use the post-id-from-URL instead for
    less confusion. **Ask the owner before changing this if it comes up.**

- **Step 4 — History (`app/history.py`) + `/api/history` + "Open folder".** ← WE ARE HERE, NOT
  STARTED YET (was about to start when this file was requested).
  - Plan: on every job reaching "done", append an entry to `data/history.json` (already gitignored)
    with: title, link, platform, preset used, finished timestamp, final file path. Cap at last 200
    entries (oldest dropped). Separate from the in-memory jobs queue (which disappears on restart) —
    history is meant to persist across restarts/days.
  - `GET /api/history` to list it (maybe with simple newest-first order, no pagination needed yet
    at 200-entry scale).
  - An "open the containing folder in Explorer" action — done **server-side by job id or history
    entry** (so the browser never needs to accept an arbitrary path from the page — keeps the
    local server safer). On Windows this is something like `subprocess.run(['explorer',
    '/select,', path])`.
  - Owner explicitly confirmed they DO want history (not skipping it) after being told the
    tradeoffs — reasoning: re-finding a link they already downloaded, or re-downloading a deleted
    file, without having to search for the original link again.
  - Owner does NOT yet have a mental model of what "History" and "Settings" being separate "panels"
    (UI sections) on the page means — this was just explained in conversation (a panel = a
    section/box on the page you open, e.g. by clicking a button/tab, as opposed to something
    that's always visible). Keep UI copy simple when we get to Step 5.

- **Step 5 — Page UI for History + Settings panels.** NOT STARTED.
  - A "History" section: list of past downloads (title, when, preset, "Open folder" button).
  - A "Settings" section: output folder (with a Browse-folder button using `tkinter.filedialog`
    server-side, since tkinter 8.6 confirmed available on owner's machine — plus a typed-path
    fallback), default preset dropdown, extra-seconds number field, parallel-downloads number
    field. Wire these to the `/api/settings` GET/PUT already built in Step 1.
  - "Clear history" button: clears `data/history.json` entries only, never deletes actual media
    files.

- **Step 6 — Full Phase 7 end-to-end test + git commit.** NOT STARTED. Model this on the Phase 6
  end-to-end test list (A–H etc. that the owner ran and confirmed "all passed"). Then
  `git commit -m "Phase 7: output folders, naming, settings, history"` + push.

### Open question for the owner (not yet answered)
"Save as my preset" (from the original brief's Phase 4, a custom-mode feature) was apparently never
built — not in the current code. Never got a clear answer on whether this was deliberately skipped
or just missed. If picked up later, it plugs naturally into `settings.py`'s storage pattern (would
need a new settings key or its own small json file, e.g. `data/custom_presets.json`). **Ask again
when convenient, doesn't block Phase 7.**

## 5. KEY DECISIONS / DEFAULTS ALREADY AGREED (don't re-litigate these without reason)

Owner approved all of these as-is (said "defaults" essentially by not objecting):

- **Folder layout:** `<Output>\<YouTube|X>\<YYYY-MM-DD>\<Clean Title> [<video id>]<variant>.<ext>`
  Date = day of download (local time).
- **Filename cleaning:** keep all languages/scripts (Hindi etc.), strip emoji and Windows-illegal
  characters (`< > : " / \ | ? *` and control chars), strip URLs, cap title at ~80 chars cut at a
  word boundary. X filenames get `"<uploader> - <post text>"` since X has no real title.
- **Source-info sidecar:** one `.source.txt` per media file (same full name + `.source.txt`, so a
  video's `.wav` and `.mp3` sidecars don't collide) with: title, uploader, link, platform, video
  id, saved-on date/time, what preset/summary was used, and section timing if applicable.
- **Duplicate names:** never overwritten — `(2)`, `(3)` etc. appended, thread-safe.
- **Default output folder:** `C:\Users\nitis\Videos\Video Downloader`.
- **Folder picking (Step 5, not built yet):** native Browse-folder dialog (tkinter confirmed
  available) + typed-path fallback.
- **History:** `data/history.json`, last 200 entries, "Clear history" never deletes files.
- **Old files already in the old flat `downloads\` folder:** left where they are, not migrated.
- **Settings limits:** `parallel_downloads` 1–4, `extra_seconds` 0–60.

## 6. FILE MAP (as of end of Phase 7 Step 3)

```
downloader/
├── requirements.txt
├── .gitignore                (correct — ignores .venv, downloads/, data/*.json, media exts, etc.
│                               NOTE: does NOT ignore test_*_out/ folders like test_cancel_out,
│                               test_queue_out etc. — media inside them still covered by *.mp4 etc.
│                               rules, but consider tidying the pattern list some day, not urgent)
├── test_engine.py, test_download.py, test_section.py, test_sections.py, test_convert.py,
│   test_phase2.py, test_presets.py, test_quality.py, test_queue.py, test_cancel.py, test_custom.py
│                              (pre-Phase-7 tests — NOT re-verified since jobs.py's DOWNLOAD_DIR
│                               change in Step 3; should sanity-check these still pass)
├── test_settings.py          (Phase 7 Step 1 — ALL PASSED)
├── test_naming.py            (Phase 7 Step 2 — ALL PASSED, 48 checks)
├── test_filing.py            (Phase 7 Step 3 — ALL PASSED, 33 checks, fully offline via fake ffmpeg video)
├── app/
│   ├── __init__.py
│   ├── engine.py              talks to yt-dlp: platform detection, get_info, time parsing,
│   │                          section validation (plan_section), download() [now takes optional
│   │                          info_out], progress reporting
│   ├── presets.py             the five presets, ffmpeg conversion settings (CONVERSIONS), audio
│   │                          formats (AUDIO_FORMATS), build_custom_preset(), resolve_preset()
│   ├── convert.py             ffmpeg conversion, copy-skip check, remove audio (for B-roll),
│   │                          progress
│   ├── naming.py              NEW (Step 2) — clean_title, display_title, plan_output,
│   │                          reserve_path, sidecar_path, variant_from_stem, day_folder,
│   │                          platform_folder
│   ├── settings.py            NEW (Step 1) — get_settings/update_settings, data/settings.json,
│   │                          SettingsError
│   ├── pipeline.py            run_preset(): download + conversion + cleanup; NOW also does file
│   │                          organizing/naming + .source.txt sidecar when `organize` param given
│   │                          (Step 3)
│   ├── jobs.py                the in-memory download queue: add/list/cancel/retry/remove jobs,
│   │                          MAX_PARALLEL worker pool; NOW reads output folder + parallel count
│   │                          from settings.py via output_dir()/apply_settings() (Step 3); job
│   │                          dicts now also carry platform/video_id/path
│   ├── history.py             NOT YET CREATED — Step 4
│   └── main.py                local FastAPI server (127.0.0.1 only): /api/health, /api/info,
│                              /api/download, /api/jobs (queue), /api/presets,
│                              /api/settings [GET/PUT, added Step 1], /api/history [NOT YET —
│                              Step 4], serves web/ as the page
└── web/
    ├── index.html             page structure (link box, info card, presets, custom mode, queue)
    ├── style.css
    ├── app.js                 link check → info card, paste button, error display
    ├── section.js             the "only a section" timeline UI
    ├── custom.js               custom mode dropdowns (quality/video-audio/audio-type/format)
    └── queue.js                the download queue UI: rows, progress, cancel/retry/remove,
                                 "Waiting · N downloads ahead", batch paste-many-links
                                 (Settings/History panels NOT YET ADDED — Step 5)
```

## 7. KNOWN ISSUES / QUIRKS TO REMEMBER (not to be "fixed" without checking first)

1. **X post id vs X video id differ in filenames** — see Step 3 notes above. Intentional/unavoidable,
   not a bug. Ask owner before changing.
2. **YouTube sometimes returns "Sign in to confirm you're not a bot"** intermittently (seen once on
   owner's machine on link `_Sl8diqCAFw`). This is expected to be properly handled in **Phase 8**
   (errors/login/cookies). For now: just retry, or use a different YouTube video, or use the X test
   link instead, and don't treat it as a Phase 7 bug.
3. **The assistant's own sandbox has no internet access to YouTube/X** — only local Python +
   ffmpeg + pip. All Phase 7 tests were designed to run fully offline (fake short ffmpeg-generated
   video standing in for a real download). Real-video checks are done by the owner on their own
   Windows machine after being given code + exact steps.
4. From way back (BUILD_LOG, pre-Phase-4, likely already handled by now — verify if it comes up
   again): a `608`-style odd quality variant appearing in YouTube's quality list, and X's very long
   post-text-based filenames — both were meant to be cleaned up by "Phase 4" custom mode /
   filename work; naming.py's title-cleaning (Step 2) may have already solved the "long name" half
   of this as a side effect. The "608" odd-quality-in-dropdown issue is a **separate, still-open**
   concern for the custom-mode quality list, unrelated to Phase 7 — not yet re-verified.
5. Pre-Phase-7 test scripts (`test_queue.py`, `test_cancel.py`, etc.) that reference
   `jobs.DOWNLOAD_DIR` directly — should still work since that variable still exists and can still
   be overridden, but this has **not been explicitly re-run/re-confirmed** since Step 3's change to
   `jobs.py`. Worth a quick sanity pass before Phase 7's Step 6 final commit.

## 8. HOW TO TALK TO THE OWNER

- Owner (nitish) is a **coder** building this tool, "vibe-coding" it with AI help — he is NOT the
  end user. The end user is a **video editor**. You can be technical with the owner directly, but
  justify feature decisions in terms of the editor's real workflow (download → use in edit →
  delete), not abstract completeness. If a feature doesn't clearly help that workflow, say so
  plainly and let the owner decide to skip it (this already happened once — see History discussion,
  section 4, Step 4 intro — owner chose to keep it after hearing concrete use cases).
- Give code as downloadable files, not huge pasted blocks in chat, matching the file names/paths
  they should replace.
- Always give an exact list of PowerShell commands to run and describe the exact expected output
  (numbers, pass counts, JSON shapes) so the owner can just compare, not judge correctness themselves.
- Keep responses in Hinglish, short, plain.
- Don't skip ahead of what's been explicitly agreed. If unsure about a decision (naming, defaults,
  scope), ask, don't assume.

---
*Next action when resuming: start Phase 7 Step 4 — build `app/history.py`, wire it into
`jobs.py`'s "done" transition, add `GET /api/history`, add a server-side "open folder" action,
write `test_history.py` (offline, following the `test_filing.py` pattern), give files + test to
owner.*
Step 4 done. Ab Step 5: page par History aur Settings panel — pehle current web files dekh leta hoon taaki wahi style/pattern follow karu.
step 5 done next step 6 
