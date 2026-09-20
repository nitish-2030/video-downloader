import subprocess
import sys
import time

from app.convert import convert, probe_media, is_already_suitable
from app.engine import EngineError

path = sys.argv[1]
treatment = sys.argv[2]
output_dir = sys.argv[3]
drop_audio = len(sys.argv) > 4 and sys.argv[4] == "drop_audio"
seen = set()


def show(p):
    if p["percent"] is None:
        return
    bucket = int(p["percent"] // 25) * 25
    if bucket not in seen:
        seen.add(bucket)
        print(f"  converting... {bucket}%+")


try:
    media = probe_media(path)
    print("Already suitable (copy only):", is_already_suitable(media, treatment, drop_audio))
    start = time.time()
    out = convert(path, treatment, output_dir, on_progress=show, drop_audio=drop_audio)
except EngineError as error:
    print("FRIENDLY MESSAGE:", error.friendly)
    print("DETAILS:", error.details[-500:])
    sys.exit(1)

print(f"SAVED: {out}  ({time.time() - start:.1f} s)")
probe = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,pix_fmt",
     "-of", "csv=p=0", out],
    capture_output=True, text=True,
)
print(probe.stdout.strip())