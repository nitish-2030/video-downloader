# Video Downloader for Editors

A local tool that turns a YouTube or X (Twitter) link into edit-ready footage — a Premiere-ready
MP4, an After Effects–ready ProRes MOV, silent B-roll, audio-only, or the untouched original —
without opening an editor's timeline with the wrong codec, frame rate, or a file full of audio
you don't need.

It runs entirely on your own machine. Nothing is uploaded anywhere; there's no account, no cloud
step, no third-party server in the loop besides the site you're downloading from.

## Why this exists

Downloading a video for an edit is usually a two-step chore: grab the file, then re-encode or
trim it before it's actually usable in a timeline. This tool folds both steps into one click by
offering a small set of **presets built around what an edit actually needs** — not a wall of
format/codec settings.

## Features

- **One-click presets** — Premiere-ready, After Effects–ready, B-roll (no audio), audio-only, or
  the original file untouched.
- **Custom mode** — pick content type, quality, and format by hand when a preset doesn't fit.
- **Section download** — grab just part of a video (with adjustable padding on each side for
  clean trims) instead of the whole thing.
- **Batch queue** — paste several links at once; downloads run in parallel with live progress,
  cancel, and retry.
- **Automatic file organization** — saved into `<Platform>/<Date>/<Title> [id]` folders, with a
  small sidecar file recording the source link, uploader, and download settings for each file.
- **History** — a running log of what's been downloaded, so you don't have to go re-find a link.
- **Sign-in support** — a `cookies.txt` file lets you fetch age-restricted, private, or
  members-only videos you have access to.

## Requirements

- Windows 10/11
- [Python 3.11+](https://www.python.org/downloads/)
- [ffmpeg](https://ffmpeg.org/download.html) available on your `PATH`

## Setup

```bash
git clone https://github.com/<your-username>/video-downloader.git
cd video-downloader
pip install -r requirements.txt
```

## Running it

```bash
python -m app.main
```

This starts a local server and opens the app in your browser at `http://127.0.0.1:<port>`.
Nothing here is exposed to the internet — it only listens on your own machine.

## Running the tests

Each module has a matching `test_*.py` that runs offline (no real network calls to YouTube/X):

```bash
python test_engine.py
python test_queue.py
# ...etc, or run everything with pytest:
pytest
```

## Project structure

```
app/            Core engine: yt-dlp integration, format presets, conversion, queue, settings
web/            The local browser UI (HTML/CSS/JS, no build step)
tests/          Offline unit tests, one file per module
docs/           Design notes and build log
```

## Roadmap

| Phase | Status |
|---|---|
| Core engine, server, and UI | Done |
| Presets, custom mode, section downloads | Done |
| Queue, batch downloads, cancel/retry | Done |
| Output organization, history, settings | Done |
| Error handling, sign-in via cookies, auto-update | Done |
| Full real-world testing (large/4K files, long sections) | Done |
| UI/UX redesign | In progress |
| Packaging as a standalone Windows app | Planned |

See [`docs/PROGRESS.md`](docs/PROGRESS.md) for the detailed build log.

## A note on legal use

This tool only downloads content you already have the right to use — for example your own
uploads, footage you're licensed to reuse, or material covered by fair use in your jurisdiction.
Respect the terms of service of the platform you're downloading from and the rights of the
original creator.

## License

MIT — see [`LICENSE`](LICENSE). This license covers the code in this repository only; it does not
grant any rights to content you download using it.