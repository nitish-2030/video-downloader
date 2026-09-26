import subprocess
import sys
import time

from app.engine import get_info, plan_section, EngineError
from app.pipeline import run_preset

url = sys.argv[1]
preset_id = sys.argv[2]
section_args = sys.argv[3:6]  # optional: start end extra
seen = set()


def show(p):
    if p["percent"] is None:
        return
    bucket = int(p["percent"] // 50) * 50
    key = (p["status"], bucket)
    if key not in seen:
        seen.add(key)
        print(f"  {p['status']}... {bucket}%+")


try:
    section = None
    if len(section_args) == 3:
        info = get_info(url)
        plan = plan_section(section_args[0], section_args[1], float(section_args[2]), info["duration"])
        section = (plan["padded_start"], plan["padded_end"])
        print("Section that will be downloaded:", section)
    start = time.time()
    out = run_preset(url, preset_id, "test_final", on_progress=show, section=section)
except EngineError as error:
    print("FRIENDLY MESSAGE:", error.friendly)
    print("DETAILS:", error.details[-500:])
    sys.exit(1)

print(f"SAVED: {out}  ({time.time() - start:.1f} s)")
probe = subprocess.run(
    ["ffprobe", "-v", "error",
     "-show_entries",
     "stream=codec_type,codec_name,pix_fmt,width,height,r_frame_rate,avg_frame_rate:format=duration",
     "-of", "default=noprint_wrappers=1", out],
    capture_output=True, text=True,
)
print(probe.stdout.strip())