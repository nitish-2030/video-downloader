"""test_errors.py - Phase 8 Step 1: friendly error message classification.

Fully offline - just feeds fake yt-dlp error strings into engine._classify_download_error
and checks the right friendly message (or None) comes back. No internet/YouTube/X needed.
"""

from app.engine import _classify_download_error

CASES = [
    ("Sign in to confirm you're not a bot", "bot"),
    ("ERROR: [youtube] abc123: Sign in to confirm your age", "age-restricted"),
    ("ERROR: Private video. Sign in if you've been granted access", "private"),
    ("This video is members-only", "members"),
    ("ERROR: [youtube] xyz: Video unavailable", "isn't available anymore"),
    ("ERROR: Unsupported URL: https://example.com/nope", "isn't a video page"),
    ("ERROR: Requested format is not available", "downloadable version"),
    ("This video is not available due to a copyright claim", "copyright"),
    ("HTTP Error 429: Too Many Requests", "too many requests"),
    ("URLError: <urlopen error timed out>", "timed out"),
    ("Failed to establish a new connection", "connect"),
    ("This live event will begin in 2 hours", "hasn't started"),
    ("Something totally unrecognized happened here", None),  # should fall back to None
]

passed = 0
failed = 0

for raw_message, expect_snippet in CASES:
    result = _classify_download_error(raw_message)
    if expect_snippet is None:
        ok = result is None
    else:
        ok = result is not None and expect_snippet.lower() in result.lower()
    if ok:
        passed += 1
        print(f"PASS: {raw_message[:50]!r}")
    else:
        failed += 1
        print(f"FAIL: {raw_message[:50]!r} -> got {result!r}")

print(f"\n{passed} passed, {failed} failed out of {len(CASES)}")
if failed:
    raise SystemExit(1)