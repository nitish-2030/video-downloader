"""test_quality.py - throwaway. Shows a video's real picture sizes and the quality list the page will offer.

Run from the downloader folder (venv active):
    python test_quality.py                 (uses the two test links)
    python test_quality.py <another link>  (any YouTube or X link, e.g. a 4K video)
"""

import sys

import yt_dlp

from app.engine import build_quality_options

DEFAULT_LINKS = [
    "https://www.youtube.com/watch?v=xuP4g7IDgDM",
    "https://x.com/PrettyCitiesX/status/2100991213621092475?s=20",
]

for link in sys.argv[1:] or DEFAULT_LINKS:
    print("=" * 70)
    print(link)
    options = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True}
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(link, download=False)
    sizes = {
        (fmt.get("width"), fmt["height"])
        for fmt in info.get("formats", [])
        if fmt.get("vcodec") != "none" and fmt.get("ext") != "mhtml" and fmt.get("height")
    }
    ordered = sorted(sizes, key=lambda size: (size[1], size[0] or 0), reverse=True)
    print("Real picture sizes found (width x height):")
    print("  " + ",  ".join(f"{w}x{h}" for w, h in ordered))
    print("What the dropdown will offer:")
    for option in build_quality_options(list(sizes)):
        print(f"  {option['label']:>6}  ->  {option['result']}")