# tests/infra/test_dev_scripts_no_local_paths.py
#
# 31.10.2026: dev/make_demo_video.py יצא לריפו הציבורי עם נתיב של המחשב הזה כברירת מחדל ובתיעוד, והסריקה של הייצוא הציבורי
# (dev/export_public.py) עצרה את 1.1.3. בקבצים ב-dev/ שיוצאים אין נתיב של המחשב הזה - לא התיקייה העליונה שמעל הריפו
# (הכונן והתיקייה הראשונה בנתיב של PROJECT_ROOT) ולא תיקיית משתמש. הפלט יחסי לריפו (build/), ונתיב של מחשב מסוים עובר
# כארגומנט. נתיבים כלליים (גופן של Windows, דוגמאות כמו D:/Videos) בסדר.
import os
import re

from tests import PROJECT_ROOT

_drive, _rest = os.path.splitdrive(os.path.abspath(PROJECT_ROOT))
_top = _rest.strip("\\/").split(os.sep)[0] if _rest.strip("\\/") else ""
MACHINE = re.compile("|".join(filter(None, [
    re.escape(_drive) + r"[\\/]{1,2}" + re.escape(_top) + r"\b" if _drive and _top else "",   # כונן\תיקייה, בכל סוג קו נטוי
    r"\b[A-Za-z]:[\\/]{1,2}Users[\\/]{1,2}(?!Public\b)\w",
])), re.IGNORECASE)


def test_dev_scripts_have_no_paths_of_this_machine():
    hits = []
    dev = os.path.join(PROJECT_ROOT, "dev")
    for name in sorted(os.listdir(dev)):
        if name.endswith((".py", ".bat", ".vbs")):
            with open(os.path.join(dev, name), encoding="utf-8", errors="replace") as f:
                for number, line in enumerate(f, 1):
                    if MACHINE.search(line):
                        hits.append(f"dev/{name}:{number}: {line.strip()[:100]}")
    assert hits == []


def test_the_demo_video_goes_to_build_by_default():
    import importlib.util
    spec = importlib.util.spec_from_file_location("make_demo_video", os.path.join(PROJECT_ROOT, "dev", "make_demo_video.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out = module.default_out()
    assert os.path.relpath(out, PROJECT_ROOT).replace("\\", "/").startswith("build/demo/clipforge-demo-") and out.endswith(".mp4")
