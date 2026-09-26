"""test_naming.py - checks file names and folders (Phase 7, Step 2). Nothing is downloaded and
your real folders are not touched (a temporary folder is used).  Run:  python test_naming.py"""

import os
import tempfile
import threading
import unicodedata
from datetime import date

from app import naming

failures = []


def check(name, condition, extra=""):
    print(("PASS  " if condition else "FAIL  ") + name + (f"   -> {extra}" if not condition and extra else ""))
    if not condition:
        failures.append(name)


def same(name, got, wanted):
    check(name, got == wanted, f"got {got!r}, wanted {wanted!r}")


# ---- clean_title ----
same("plain title stays", naming.clean_title("My Trip to Goa"), "My Trip to Goa")
same("Windows-illegal characters become spaces",
     naming.clean_title('Q&A: what/why? "Best" <of> 2026 | part*1'), "Q&A what why Best of 2026 part 1")
same("emoji are removed", naming.clean_title("Fire \U0001F525\U0001F525 video \U0001F602"), "Fire video")
same("skin tone, family and flag emoji are removed",
     naming.clean_title("Hi \U0001F44D\U0001F3FD and \U0001F468\u200D\U0001F469\u200D\U0001F467 and \U0001F1EE\U0001F1F3 done"),
     "Hi and and done")
same("keycap emoji leaves the digit", naming.clean_title("Top 1\ufe0f\u20e3 clip"), "Top 1 clip")
same("Hindi is kept, emoji removed", naming.clean_title("नमस्ते दुनिया \U0001F64F"), "नमस्ते दुनिया")
same("Hindi with marks stays whole", naming.clean_title("किताबें और कहानियाँ"), unicodedata.normalize("NFC", "किताबें और कहानियाँ"))
same("trailing dots and spaces removed", naming.clean_title("  Hello world...  "), "Hello world")
same("leading dots removed", naming.clean_title("..hidden file"), "hidden file")
same("tabs and new lines become one space", naming.clean_title("line one\n\nline\ttwo"), "line one line two")
same("links are removed", naming.clean_title("Nice view https://t.co/AbC123 wow"), "Nice view wow")
same("only emoji -> empty", naming.clean_title("\U0001F525\U0001F525"), "")
same("empty input -> empty", naming.clean_title(None), "")

long_title = ("word " * 40).strip()
cut = naming.clean_title(long_title)
check("long title is cut to 80 or less", len(cut) <= 80, str(len(cut)))
check("cut title doesn't end with a space or a half word", cut == "word " * 0 + cut.rstrip() and cut.endswith("word"), repr(cut))

hindi = "कृष्णक्षत्रिय" * 15          # no spaces, full of joined letters and marks
for limit in (7, 8, 9, 10, 11, 12, 20, 33):
    result = naming.clean_title(hindi, limit)
    nxt = hindi[len(result)] if len(result) < len(hindi) else "a"
    # the cut may only fall before a new letter, or before a virama that was dropped with it
    ok = ((not unicodedata.category(nxt).startswith("M") or unicodedata.combining(nxt) == 9)
          and (not result or unicodedata.combining(result[-1]) != 9))
    check(f"Hindi cut at {limit} doesn't split a letter or end on a half letter", ok, repr(result))

# ---- display_title ----
same("YouTube title unchanged", naming.display_title("youtube", "My Trip", "Some Channel"), "My Trip")
same("X: poster's name goes in front",
     naming.display_title("x", "beautiful city https://t.co/x1", "PrettyCitiesX"), "PrettyCitiesX - beautiful city")
same("X: not repeated if the title already starts with it",
     naming.display_title("x", "prettycitiesx - beautiful city", "PrettyCitiesX"), "prettycitiesx - beautiful city")
same("X: no title -> just the poster", naming.display_title("x", "", "PrettyCitiesX"), "PrettyCitiesX")

# ---- variant_from_stem ----
same("variant after the id", naming.variant_from_stem("xuP4g7IDgDM_720p_premiere", "xuP4g7IDgDM"), "_720p_premiere")
same("no variant", naming.variant_from_stem("xuP4g7IDgDM", "xuP4g7IDgDM"), "")
same("id with _ and -", naming.variant_from_stem("_Sl8di-CAFw_broll", "_Sl8di-CAFw"), "_broll")
same("unknown stem -> empty", naming.variant_from_stem("something_else", "abc"), "")

# ---- day and platform ----
same("day folder", naming.day_folder(date(2026, 9, 21)), "2026-09-21")
same("YouTube folder", naming.platform_folder("youtube"), "YouTube")
same("X folder", naming.platform_folder("x"), "X")
same("unknown platform folder", naming.platform_folder("vimeo"), "Other")

# ---- plan_output ----
out = os.path.join("base", "Videos")
plan = naming.plan_output(out, "youtube", "xuP4g7IDgDM", "My Trip: Goa \U0001F334", "Chan", "_720p_premiere", "mp4", date(2026, 9, 21))
same("folder layout", plan["folder"], os.path.join("base", "Videos", "YouTube", "2026-09-21"))
same("file name", plan["base"], "My Trip Goa [xuP4g7IDgDM]_720p_premiere")

plan = naming.plan_output(out, "youtube", "abc", "\U0001F525\U0001F525", "Cool Channel", "", "mp4", date(2026, 9, 21))
same("emoji-only title falls back to the uploader", plan["base"], "Cool Channel [abc]")
plan = naming.plan_output(out, "youtube", "abc", "", "", "", "mp4", date(2026, 9, 21))
same("no title and no uploader -> 'Video'", plan["base"], "Video [abc]")

deep = os.path.join("C:" + os.sep, "x" * 116)   # 120 characters: the longest folder settings allow
plan = naming.plan_output(deep, "youtube", "xuP4g7IDgDM", "Very long title " * 20, "Chan",
                          "_2160p_section_1000-2000_after_effects_nosound", "mov")
longest = os.path.join(plan["folder"], plan["base"] + " (99).mov" + naming.SIDECAR_SUFFIX)
check("even the longest neighbour stays under the Windows limit", len(longest) <= 260, str(len(longest)))

# ---- reserve_path ----
with tempfile.TemporaryDirectory() as temp:
    folder = os.path.join(temp, "YouTube", "2026-09-21")
    first = naming.reserve_path(folder, "Clip [id]_premiere", "mp4")
    same("first file gets the plain name", os.path.basename(first), "Clip [id]_premiere.mp4")
    check("...and is claimed on disk", os.path.exists(first))
    second = naming.reserve_path(folder, "Clip [id]_premiere", "mp4")
    same("second one gets (2)", os.path.basename(second), "Clip [id]_premiere (2).mp4")
    third = naming.reserve_path(folder, "Clip [id]_premiere", "mp4")
    same("third one gets (3)", os.path.basename(third), "Clip [id]_premiere (3).mp4")

    other = naming.reserve_path(folder, "Clip [id]", "wav")
    same("another kind of file is not affected", os.path.basename(other), "Clip [id].wav")

    with open(naming.sidecar_path(os.path.join(folder, "Solo [id].mp4")), "w") as file:
        file.write("old info")
    solo = naming.reserve_path(folder, "Solo [id]", "mp4")
    same("a leftover source-info file also counts as taken", os.path.basename(solo), "Solo [id] (2).mp4")

    # many jobs at the same moment must never get the same name
    picked, lock = [], threading.Lock()

    def grab():
        path = naming.reserve_path(folder, "Race [id]", "mp4")
        with lock:
            picked.append(path)

    threads = [threading.Thread(target=grab) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    check("12 jobs at once get 12 different names", len(set(picked)) == 12, str(len(set(picked))))

same("source-info file name", naming.sidecar_path("a/Clip [id].mp4"), "a/Clip [id].mp4.source.txt")

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
if __name__ == "__main__":
    raise SystemExit(1 if failures else 0)