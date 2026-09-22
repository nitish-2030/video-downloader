"""test_disk_space.py - Phase 8 Step 2: free disk-space check.

Fully offline - uses the real disk but a fake `minimum_bytes` threshold, so no
need to actually fill up or empty a disk to test both branches.
"""

import tempfile

from app.engine import EngineError, check_disk_space

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


with tempfile.TemporaryDirectory() as tmp:
    # 1) An impossibly high requirement should always raise EngineError.
    try:
        check_disk_space(tmp, minimum_bytes=10 * 1024 ** 4)  # 10 TB
        check("raises EngineError when not enough space", False)
    except EngineError as error:
        check("raises EngineError when not enough space", True)
        check("message mentions free disk space", "disk space" in error.friendly.lower())

    # 2) A tiny requirement should always pass (assuming the test machine has >1 byte free).
    try:
        check_disk_space(tmp, minimum_bytes=1)
        check("does not raise when space is plainly enough", True)
    except EngineError:
        check("does not raise when space is plainly enough", False)

    # 3) It creates the folder if it doesn't exist yet.
    import os
    new_folder = os.path.join(tmp, "not_here_yet")
    check_disk_space(new_folder, minimum_bytes=1)
    check("creates the folder if missing", os.path.isdir(new_folder))

print(f"\n{passed} passed, {failed} failed out of {passed + failed}")
if failed:
    raise SystemExit(1)