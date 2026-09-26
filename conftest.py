"""Ensures the project root (and the `app` package inside it) is importable
from anywhere under tests/, regardless of how pytest is invoked."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# These files are NOT pytest tests - they are manual, interactive scripts meant
# to be run by hand from the terminal with a real URL/args and/or a live network
# connection (e.g. `python tests/test_download.py <url> premiere`), or they have
# a small pre-existing bug unrelated to the tests/ move. They live in tests/ for
# convenience, but pytest should not try to import/collect them.
collect_ignore = [
    "tests/test_convert.py",
    "tests/test_download.py",
    "tests/test_engine.py",
    "tests/test_phase2.py",
    "tests/test_section.py",
    "tests/test_quality.py",
    "tests/test_updater.py",
    "tests/test_errors.py",
]