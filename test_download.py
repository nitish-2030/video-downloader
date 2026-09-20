import subprocess
import sys

from app.engine import download, EngineError

url = sys.argv[1]
preset_id = sys.argv[2]
seen = set()


def show(p):
    if p["status"] == "finished":
        print("  one part finished")
        seen.clear()
    elif p["percent"] is not None:
        bucket = int(p["percent"] // 25) * 25
        if bucket not in seen:
            seen.add(bucket)
            print(f"  downloading... {bucket}%+")


try:
    path = download(url, preset_id, "test_out", on_progress=show)
except EngineError as error:
    print("FRIENDLY MESSAGE:", error.friendly)
    print("DETAILS:", error.details[:300])
    sys.exit(1)

print("SAVED:", path)
probe = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,codec_type",
     "-of", "csv=p=0", path],
    capture_output=True, text=True,
)
print(probe.stdout.strip())