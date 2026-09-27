# Progress Log

A running log of how this project actually got built — what worked, what broke, and how it got
fixed. Built with AI help (mostly Claude) doing the heavy lifting on code, with me driving
decisions and testing everything on my own machine.

---

## The idea

I edit video sometimes, and I got tired of the YouTube-download-then-convert-in-Premiere dance —
download the video, open Premiere, realize the codec is wrong, convert it, re-import. Wanted a
tool that skips the middle step: paste a link, pick "Premiere ready" or "After Effects ready" or
whatever, get a file that just works.

## Phase 0–1: setup and a sanity check

Checked the basics first — Python, yt-dlp, ffmpeg all installed and working. Before writing any
real code, downloaded a video by hand and dragged it into CapCut (didn't have Premiere/AE
installed yet at that point) just to confirm the presets I had in mind (Premiere-ready MP4,
After-Effects-ready ProRes MOV, B-roll with no audio, audio-only) would actually make sense once
built.

## Phase 2–6: the actual engine

Built the core piece by piece:
- `engine.py` — talks to yt-dlp, figures out which platform a link is from, fetches video info,
  handles section timing math
- `presets.py` / `convert.py` — the five presets and the ffmpeg commands behind them
- `main.py` + a `web/` folder — a local FastAPI server with a browser-based UI (runs on
  `127.0.0.1`, never touches the internet except to actually fetch the video)
- A timeline UI for downloading just part of a video, with a bit of padding on each side so cuts
  land clean
- A queue so multiple links can download at once, with progress bars, cancel/retry, and pasting a
  batch of links at once

## Phase 7: where do files actually go

Once the core worked, the next problem was organization — files were dumping into one flat
folder with yt-dlp's default naming, which is unusable once you've downloaded more than a
handful of videos.

Settled on: `<Output>/<YouTube|X>/<date>/<clean title> [<video id>]<variant>.<ext>`, with a
`.source.txt` sidecar next to every file (title, uploader, original link, when it was saved) so
I'd never lose track of where a clip came from. Title cleaning turned out to be more involved
than expected — had to strip emoji (by Unicode category so new emoji don't need a code update
every year), strip Windows-illegal characters, keep non-Latin scripts intact (a lot of the
content I download has Hindi text in the title), and cap the length so the full path never
blows past Windows' ~260-character limit.

Added a settings panel (output folder, default preset, how many downloads run at once) and a
history panel (so I can find something I downloaded a week ago without re-searching for the
original link). History almost didn't happen — the first instinct was "just log everything," but
sat down and thought about what I'd actually use it for before building it, rather than adding it
for the sake of completeness.

## Phase 8: the annoying real-world stuff

This is the phase that made the tool actually usable day-to-day instead of just a demo:
- **Age-restricted / private / members-only videos** need cookies to download. Added a settings
  field for a cookies.txt export, and made the download logic smart about it — a normal public
  video never even tries cookies (stays fast), and only a sign-in-style failure triggers a retry
  with cookies attached.
- **YouTube's "sign in to confirm you're not a bot" check** is a completely different problem
  from the above, and cookies don't reliably fix it — it's an ongoing thing YouTube does that
  yt-dlp has to keep adapting to. Learned to tell these two error types apart in the code (and in
  my own head) instead of throwing cookies at every YouTube error that shows up.
- Added a one-click "check for yt-dlp update" button, since keeping yt-dlp current is basically
  the only lever available against YouTube changing things on their end.
- Added a disk-space check before starting a download, so a huge video doesn't fail halfway
  through with a confusing error.

## Hardening the public repo

Before pointing anyone else at this repo, went through and cleaned up a few things that had
drifted:

- `python -m app.main` didn't actually do anything — there was a FastAPI app defined but no
  runner. Added one (starts uvicorn on a free local port, opens the browser automatically).
- The README described a `tests/` folder and a `docs/PROGRESS.md` that didn't exist — everything
  was still sitting in the repo root from early development. Moved the test files and this log
  into the structure the README already promised, instead of the other way around.
- That move broke `pytest` in an interesting way: several of the "test" files in this repo
  aren't actually pytest tests — they're standalone scripts I'd write early on to manually check
  something against a real video, complete with a bare `sys.exit()` at the end. The moment pytest
  tried to *import* one of those files to look for tests inside it, that `sys.exit()` fired
  immediately and crashed pytest's entire collection process with an internal error. Took a bit
  of digging (`Select-String` across every test file for `sys.exit`/`SystemExit`) to find all of
  them. Fixed the ones that just needed an `if __name__ == "__main__":` guard, and told pytest to
  skip the rest outright — the ones that need a real URL typed in as an argument, or a live
  network connection, aren't things pytest can run anyway.
- Fixed a stale clone-URL placeholder in the README, and rewrote the testing section to describe
  what's actually true now instead of what I'd originally planned.

## Splitting into two versions

Realized partway through that "one repo does both jobs" wasn't going to work — a free,
open-source tool for developers and a paid, packaged tool for non-technical editors have
genuinely different needs (one needs source code and a MIT license, the other needs an installer
and a license-key check). Split it:

- **This repo** stays exactly what it's always been: free, open, source-only. Clone it, `pip
  install`, run it.
- **A separate, private repo** has the packaged version — same core engine, but built into a
  single Windows `.exe` with PyInstaller, sold with a license key.

## Building the packaged version — the fun debugging part

Packaging a FastAPI app into a single `.exe` surfaced a string of issues, each one a small
lesson:

- **Relative imports break under PyInstaller** if you point it straight at the file with the
  imports in it — it stops treating the surrounding folder as a package. Fixed by adding a tiny
  `run.py` at the root that imports properly and pointing PyInstaller at that instead.
- **The bundled exe couldn't find its own web UI.** The static files (`web/`) need to be
  explicitly bundled in with `--add-data`, and the code needs to know to look inside PyInstaller's
  temporary extraction folder (`sys._MEIPASS`) instead of next to the script, when running as a
  frozen exe.
- **Settings and history were getting wiped every restart** once packaged — a `--onefile` build
  extracts itself into a new temp folder every time it runs and deletes it on exit, and the
  original code stored its data folder relative to the script's own location. Moved that to a
  proper per-user AppData folder in packaged mode, left it untouched in normal dev mode.
- **ffmpeg needed to be bundled too**, and had to work identically whether or not the customer's
  own machine already has ffmpeg installed — bundled the binaries directly and pointed the code
  at them when running as a packaged exe.
- Even after all that, **section/clip downloads still failed on a clean test machine** with
  "ffmpeg is not installed," while full-video downloads worked fine. Turned out yt-dlp's internal
  ffmpeg check for clipped downloads doesn't always respect the `ffmpeg_location` option the way
  the rest of yt-dlp does — it sometimes just looks for a bare `ffmpeg` on the system PATH. Fixed
  by also adding the bundled ffmpeg folder to the process's own PATH at startup, so it gets found
  either way.
- Built a simple offline license system — a key tied to the machine's own ID, checked locally, no
  server involved. Hit one funny bug here: the license-check screen's own JavaScript file was
  being blocked by the same "block everything until licensed" rule it was supposed to work
  around, so the activate button silently did nothing. Had to explicitly exempt static files
  (JS/CSS/the page itself) from the license gate and only actually lock down the API endpoints.
- Ran the whole thing end-to-end on a brand-new Windows user account with nothing pre-installed —
  license activation, full download, section download, both YouTube and X, restart persistence —
  before calling it done.

## Adding Instagram

Added Instagram as a third supported platform. Mostly mechanical — platform detection, folder
naming, and a couple of frontend labels that were hardcoded as a YouTube/X toggle and needed to
become a proper three-way lookup. Public Instagram content works; haven't yet stress-tested
private/login-required Instagram content the way the cookies flow handles YouTube — that's a
known gap, not an assumption I'm making either way.

## Where things stand

- Public repo: stable, tested, documented, free.
- Packaged/paid version: built, licensed, tested clean on a fresh machine, currently in the hands
  of a small group of testers before I think about pricing/branding properly.
- Still open: full stress-testing with big/long videos (Phase 9 from the original plan), and a
  browser-extension shortcut (originally planned, still just an idea).
