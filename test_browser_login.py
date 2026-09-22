"""test_browser_login.py - checks the sign-in (cookies.txt) flow.

The old browser-login dropdown is gone; sign-in now works only through an exported
cookies.txt file. This test does not download anything or touch the network - it only
checks settings validation, the option yt-dlp gets, and the friendly error messages.

Run: python test_browser_login.py
"""

import os
import sys
import tempfile
import types
from pathlib import Path

passed = 0
failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ok   - {name}")
    else:
        failed += 1
        print(f"  FAIL - {name}")


# ---------- stub yt_dlp so this runs without the real dependency or network ----------
yt_dlp = types.ModuleType("yt_dlp")


class _DummyYDL:
    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


yt_dlp.YoutubeDL = _DummyYDL
utils = types.ModuleType("yt_dlp.utils")


class DownloadCancelled(Exception):
    pass


class DownloadError(Exception):
    pass


def download_range_func(*a, **k):
    return None


utils.DownloadCancelled = DownloadCancelled
utils.DownloadError = DownloadError
utils.download_range_func = download_range_func
yt_dlp.utils = utils
sys.modules["yt_dlp"] = yt_dlp
sys.modules["yt_dlp.utils"] = utils

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app.settings as settings  # noqa: E402
import app.engine as engine  # noqa: E402

# Point settings at a throwaway folder so this never touches the real data/settings.json.
_tmp_dir = Path(tempfile.mkdtemp(prefix="cookies_test_"))
settings.DATA_DIR = _tmp_dir
settings.SETTINGS_FILE = _tmp_dir / "settings.json"
settings.reload_settings()

print("Settings ------------------------------------------------------------")

# 1. Fresh settings have no cookies file set.
check("default cookies_file is empty", settings.get_settings()["cookies_file"] == "")

# 2. The old browser_login setting is gone - not present, and not accepted anymore.
check("browser_login is no longer a known setting", "browser_login" not in settings.get_settings())
try:
    settings.update_settings({"browser_login": "chrome"})
    check("saving browser_login is rejected", False)
except settings.SettingsError:
    check("saving browser_login is rejected", True)

# 3. A cookies_file path that doesn't exist is rejected with a friendly message.
try:
    settings.update_settings({"cookies_file": str(_tmp_dir / "does_not_exist.txt")})
    check("missing cookies file is rejected", False)
except settings.SettingsError as error:
    check("missing cookies file is rejected", True)
    check("missing-file message mentions 'cookies'", "cookies" in error.friendly.lower())

# 4. A real file (any name - it does NOT have to be called "cookies.txt") is accepted.
real_cookie_file = _tmp_dir / "youtube.com_cookies.txt"
real_cookie_file.write_text("# Netscape HTTP Cookie File\n")
saved = settings.update_settings({"cookies_file": str(real_cookie_file)})
check("a real file with any name is accepted", saved["cookies_file"] == str(real_cookie_file))

# 5. Quotes pasted around the path (common when copying a Windows path) are stripped.
saved = settings.update_settings({"cookies_file": f'"{real_cookie_file}"'})
check("quoted path is accepted", saved["cookies_file"] == str(real_cookie_file))

# 6. An empty string is always fine - it just means "don't sign in".
saved = settings.update_settings({"cookies_file": ""})
check("empty cookies_file is accepted", saved["cookies_file"] == "")

print("\nEngine options --------------------------------------------------------")

# 7. With no cookies file, yt-dlp gets no cookie-related option at all.
check("no cookie option when unset", engine._cookie_options() == {})

# 8. With a cookies file set, yt-dlp gets exactly {"cookiefile": <path>}.
settings.update_settings({"cookies_file": str(real_cookie_file)})
check("cookiefile option when set", engine._cookie_options() == {"cookiefile": str(real_cookie_file)})
settings.update_settings({"cookies_file": ""})

print("\nFriendly error messages -------------------------------------------------")

# 9. Age-restricted, no cookies file yet -> tells the user to add one, flags "need_cookies".
friendly, action = engine._classify_download_error(
    "ERROR: [youtube] abc123: Sign in to confirm your age"
)
check("age-restricted (no file) mentions adding a cookies.txt", "cookies.txt" in friendly.lower())
check("age-restricted (no file) action is need_cookies", action == "need_cookies")

# 10. Age-restricted, a cookies file IS already set -> different message (expired/wrong account).
settings.update_settings({"cookies_file": str(real_cookie_file)})
friendly2, action2 = engine._classify_download_error(
    "ERROR: [youtube] abc123: Sign in to confirm your age"
)
settings.update_settings({"cookies_file": ""})
check("age-restricted (file set) message differs from the no-file case", friendly2 != friendly)
check("age-restricted (file set) still flags need_cookies", action2 == "need_cookies")

# 11. Private video and members-only both get a sign-in message too.
friendly3, action3 = engine._classify_download_error(
    "ERROR: [youtube] abc123: Private video. Sign in if you've been granted access"
)
check("private video flags need_cookies", action3 == "need_cookies")

friendly4, action4 = engine._classify_download_error(
    "ERROR: [youtube] abc123: This video is members-only"
)
check("members-only flags need_cookies", action4 == "need_cookies")

# 12. An unrelated error (rate limiting) is NOT treated as a sign-in issue.
friendly5, action5 = engine._classify_download_error("HTTP Error 429: Too Many Requests")
check("rate-limit error has no need_cookies action", action5 is None)

# 13. _is_signin_error only fires for the sign-in style messages, not everything else.
check("age-restricted text is a signin error", engine._is_signin_error("Sign in to confirm your age"))
check("private video text is a signin error", engine._is_signin_error("Private video"))
check("members-only text is a signin error", engine._is_signin_error("This is members-only"))
check("bot-check text is NOT a signin error",
      not engine._is_signin_error("Sign in to confirm you're not a bot"))
check("reload-hiccup text is NOT a signin error",
      not engine._is_signin_error("The page needs to be reloaded"))
check("rate-limit text is NOT a signin error", not engine._is_signin_error("429 Too Many Requests"))

print("\nNormal video with a cookies.txt set (must stay on the fast, no-cookies path) ----")


class _FakeYDL_AlwaysWorks:
    """Succeeds no matter what - simulates a normal, public video. Used to make sure a
    cookies.txt left over from an earlier exceptional video doesn't add a second attempt
    (or any cookie option at all) to an ordinary download."""

    calls = []

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def extract_info(self, url, download=False):
        _FakeYDL_AlwaysWorks.calls.append(dict(self.opts))
        return {
            "id": "abc123", "title": "A normal public video", "uploader": "someone",
            "formats": [{"height": 1080, "width": 1920, "vcodec": "avc1"}],
            "webpage_url": url, "duration": 100, "thumbnail": "https://example/thumb.jpg",
            "is_live": False,
        }

    def prepare_filename(self, info):
        return "/tmp/abc123.mp4"


_real_ydl = yt_dlp.YoutubeDL
yt_dlp.YoutubeDL = _FakeYDL_AlwaysWorks
settings.update_settings({"cookies_file": str(real_cookie_file)})
try:
    info = engine.get_info("https://www.youtube.com/watch?v=IbYzjh1_8RA")
    check("a normal video loads fine even with cookies.txt set",
          info["title"] == "A normal public video")
    check("only ONE attempt was made, and it carried no cookiefile",
          len(_FakeYDL_AlwaysWorks.calls) == 1 and "cookiefile" not in _FakeYDL_AlwaysWorks.calls[0])
except Exception as error:
    check(f"a normal video loads fine even with cookies.txt set ({error})", False)
finally:
    yt_dlp.YoutubeDL = _real_ydl
    settings.update_settings({"cookies_file": ""})

print("\nAge-restricted video with cookies.txt set (must retry WITH cookies) -----------")


class _FakeYDL_NeedsSignin:
    """Fails with an age-restricted error unless a cookiefile is present - simulates a video
    that genuinely needs sign-in, and a cookies.txt that actually works for it."""

    calls = []

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def extract_info(self, url, download=False):
        _FakeYDL_NeedsSignin.calls.append(dict(self.opts))
        if "cookiefile" not in self.opts:
            raise DownloadError("ERROR: [youtube] abc123: Sign in to confirm your age")
        return {
            "id": "xyz789", "title": "An age-restricted video", "uploader": "someone",
            "formats": [{"height": 720, "width": 1280, "vcodec": "avc1"}],
            "webpage_url": url, "duration": 60, "thumbnail": "https://example/thumb.jpg",
            "is_live": False,
        }

    def prepare_filename(self, info):
        return "/tmp/xyz789.mp4"


yt_dlp.YoutubeDL = _FakeYDL_NeedsSignin
settings.update_settings({"cookies_file": str(real_cookie_file)})
try:
    info = engine.get_info("https://www.youtube.com/watch?v=xyz789")
    check("age-restricted video succeeds once cookies are tried",
          info["title"] == "An age-restricted video")
    check("it tried once without cookies, then once with cookies",
          len(_FakeYDL_NeedsSignin.calls) == 2
          and "cookiefile" not in _FakeYDL_NeedsSignin.calls[0]
          and "cookiefile" in _FakeYDL_NeedsSignin.calls[1])
except Exception as error:
    check(f"age-restricted video succeeds once cookies are tried ({error})", False)
finally:
    yt_dlp.YoutubeDL = _real_ydl
    settings.update_settings({"cookies_file": ""})

print("\nNon-signin error with cookies.txt set (must NOT waste a cookies retry) --------")


class _FakeYDL_UnrelatedError:
    """Always fails with a non-signin error - simulates a bot-check / network hiccup that
    cookies can't fix. Should never be retried with cookies."""

    calls = []

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def extract_info(self, url, download=False):
        _FakeYDL_UnrelatedError.calls.append(dict(self.opts))
        raise DownloadError("ERROR: The page needs to be reloaded.")

    def prepare_filename(self, info):
        return "/tmp/none.mp4"


yt_dlp.YoutubeDL = _FakeYDL_UnrelatedError
settings.update_settings({"cookies_file": str(real_cookie_file)})
try:
    engine.get_info("https://www.youtube.com/watch?v=none")
    check("a non-signin error is not silently swallowed", False)
except engine.EngineError as error:
    check("a non-signin error is raised straight away (no cookies retry)",
          len(_FakeYDL_UnrelatedError.calls) == 1)
    check("its message is the generic reload hiccup, not a sign-in message",
          "temporary hiccup" in error.friendly.lower() and error.action is None)
finally:
    yt_dlp.YoutubeDL = _real_ydl
    settings.update_settings({"cookies_file": ""})

print(f"\n{passed} passed, {failed} failed out of {passed + failed}")
sys.exit(1 if failed else 0)