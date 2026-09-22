"""test_updater.py - Phase 8 Step 3: yt-dlp update check.

Mostly offline (latest_version and run_update are mocked so no real network call or real pip
install happens during the test). One real, live PyPI check is also made at the end, purely
informational - it never fails the test suite if the network isn't reachable.
"""

from unittest.mock import patch

from app import updater

passed = 0
failed = 0


def check(label, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {label}")
    else:
        failed += 1
        print(f"FAIL: {label}")


# 1) current_version() always works offline.
current = updater.current_version()
check("current_version() returns a non-empty string", bool(current))

# 2) check_for_update() shape, with latest_version() mocked so no internet is needed.
with patch.object(updater, "latest_version", return_value="9999.01.01"):
    result = updater.check_for_update()
    check("check_for_update reports current version", result["current"] == current)
    check("check_for_update reports the mocked latest version", result["latest"] == "9999.01.01")
    check("update_available is True when latest differs", result["update_available"] is True)

with patch.object(updater, "latest_version", return_value=current):
    result = updater.check_for_update()
    check("update_available is False when latest == current", result["update_available"] is False)

with patch.object(updater, "latest_version", return_value=None):
    result = updater.check_for_update()
    check("update_available is False when PyPI can't be reached", result["update_available"] is False)
    check("latest is None when PyPI can't be reached", result["latest"] is None)

# Regression: PyPI normalizes '2026.08.19' to '2026.8.19' (PEP 440 drops leading zeros) - that
# should NOT count as an update, even though the strings differ.
with patch.object(updater, "current_version", return_value="2026.08.19"), \
     patch.object(updater, "latest_version", return_value="2026.8.19"):
    result = updater.check_for_update()
    check("zero-padded vs unpadded same version is NOT flagged as an update",
          result["update_available"] is False)


# 3) run_update(), with subprocess mocked so this test never actually reinstalls anything.
class FakeResult:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


with patch.object(updater.subprocess, "run",
                   return_value=FakeResult(0, stdout="Successfully installed yt-dlp")):
    ok, msg = updater.run_update()
    check("run_update() succeeds when pip returncode is 0", ok is True)
    check("run_update() returns pip's output", "installed" in msg.lower())

with patch.object(updater.subprocess, "run", return_value=FakeResult(1, stderr="network error")):
    ok, msg = updater.run_update()
    check("run_update() fails when pip returncode is nonzero", ok is False)
    check("run_update() returns pip's error", "network error" in msg.lower())

# 4) A real, live PyPI check - informational only, never fails the test suite.
try:
    live = updater.latest_version(timeout=5)
    if live:
        print(f"INFO: live PyPI check reached the internet, latest yt-dlp is {live}")
    else:
        print("INFO: live PyPI check could not reach the internet (not a failure)")
except Exception as error:
    print(f"INFO: live PyPI check raised {error!r} (not a failure)")

print(f"\n{passed} passed, {failed} failed out of {passed + failed}")
if failed:
    raise SystemExit(1)