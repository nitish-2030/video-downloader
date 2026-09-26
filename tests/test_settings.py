"""test_settings.py - checks the settings (Phase 7, Step 1). Uses a temporary folder, so your real
data/settings.json is not touched.  Run:  python test_settings.py"""

import json
import os
import tempfile
from pathlib import Path

from app import settings

failures = []


def check(name, condition, extra=""):
    print(("PASS  " if condition else "FAIL  ") + name + (f"   {extra}" if extra and not condition else ""))
    if not condition:
        failures.append(name)


def expect_error(name, changes):
    try:
        settings.update_settings(changes)
    except settings.SettingsError as error:
        check(name, bool(error.friendly), "no friendly message")
        return
    check(name, False, "no error was raised")


with tempfile.TemporaryDirectory() as temp:
    temp = Path(temp)
    settings.DATA_DIR = temp / "data"
    settings.SETTINGS_FILE = settings.DATA_DIR / "settings.json"
    good_folder = str(temp / "My Videos")

    # 1. No file yet -> defaults
    settings.reload_settings()
    current = settings.get_settings()
    check("no file: defaults are used", current == settings.default_settings())

    # 2. A valid change is saved to the file and survives a restart
    saved = settings.update_settings({"output_folder": good_folder, "parallel_downloads": 2})
    check("valid change is returned", saved["parallel_downloads"] == 2 and saved["output_folder"] == good_folder)
    check("the folder was created", os.path.isdir(good_folder))
    settings.reload_settings()   # like closing and opening the tool
    again = settings.get_settings()
    check("change survives a restart", again["parallel_downloads"] == 2 and again["output_folder"] == good_folder)
    check("other settings stayed the same", again["default_preset"] == "premiere" and again["extra_seconds"] == 2)

    # 3. No half-written files are left behind
    leftovers = [name for name in os.listdir(settings.DATA_DIR) if name.endswith(".tmp")]
    check("no temporary files left", leftovers == [], str(leftovers))

    # 4. Bad values are refused, and nothing changes
    before = settings.get_settings()
    expect_error("unknown preset refused", {"default_preset": "nope"})
    expect_error("0 downloads at once refused", {"parallel_downloads": 0})
    expect_error("9 downloads at once refused", {"parallel_downloads": 9})
    expect_error("negative extra seconds refused", {"extra_seconds": -1})
    expect_error("huge extra seconds refused", {"extra_seconds": 500})
    expect_error("empty folder refused", {"output_folder": "   "})
    expect_error("relative folder refused", {"output_folder": "just/a/name"})
    expect_error("unknown setting refused", {"volume": 5})
    a_file = temp / "a_file.txt"
    a_file.write_text("x")
    expect_error("folder inside a file refused", {"output_folder": str(a_file / "sub")})
    expect_error("very long folder refused", {"output_folder": str(temp / ("x" * 200))})
    check("refused values changed nothing", settings.get_settings() == before)

    # 5. One bad value in a request stops the whole request (nothing is half-saved)
    expect_error("mixed good+bad refused", {"extra_seconds": 5, "parallel_downloads": 99})
    check("...and the good part was not saved", settings.get_settings()["extra_seconds"] == before["extra_seconds"])

    # 6. Decimals and text numbers
    check("2.5 extra seconds kept", settings.update_settings({"extra_seconds": 2.5})["extra_seconds"] == 2.5)
    check("0 extra seconds allowed", settings.update_settings({"extra_seconds": 0})["extra_seconds"] == 0)
    check("preset can be changed", settings.update_settings({"default_preset": "audio"})["default_preset"] == "audio")

    # 7. A broken file does not stop the tool: defaults are used
    settings.SETTINGS_FILE.write_text("{ this is not json", encoding="utf-8")
    settings.reload_settings()
    check("broken file: defaults are used", settings.get_settings() == settings.default_settings())

    # 8. A file with one bad value keeps the good ones
    settings.SETTINGS_FILE.write_text(json.dumps({"parallel_downloads": 3, "default_preset": "gone"}), encoding="utf-8")
    settings.reload_settings()
    partial = settings.get_settings()
    check("bad value falls back, good value kept", partial["parallel_downloads"] == 3 and partial["default_preset"] == "premiere")

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
if __name__ == "__main__":
    raise SystemExit(1 if failures else 0)
