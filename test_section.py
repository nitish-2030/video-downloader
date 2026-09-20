import subprocess
import sys

from app.engine import get_info, plan_section, download, EngineError

url, start, end, extra = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

try:
    info = get_info(url)
    print("Video length:", info["duration"], "seconds")
    plan = plan_section(start, end, float(extra), info["duration"])
    print("Plan:", plan)
    path = download(
        url, "original", "test_out",
        section=(plan["padded_start"], plan["padded_end"]),
    )
except EngineError as error:
    print("FRIENDLY MESSAGE:", error.friendly)
    sys.exit(1)

print("SAVED:", path)
probe = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
     "-of", "default=noprint_wrappers=1", path],
    capture_output=True, text=True,
)
print(probe.stdout.strip())