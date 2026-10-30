# tests/studio/test_build_extra_args_golden.py
#
# רשת ביטחון לפירוק _build_extra_args לטבלה לפי סקריפט: 1420 מטענים (נוצרו עם זרע קבוע מהקוד *לפני* הפירוק)
# חייבים להניב בדיוק את אותם ארגומנטים (או אותה חריגה) גם אחרי. נתיב תיקיית הכתוביות תלוי במחשב, אז בקובץ
# ה-golden הוא שמור כ-<CAPTIONS_EDITS_DIR> והטסט מפנה אליו את web_app.CAPTIONS_EDITS_DIR.
import json
from tests import TESTS_DIR
import os


from entrypoints import web_app

GOLDEN = os.path.join(TESTS_DIR, "golden", "build_extra_args.json")
CAPTIONS_PLACEHOLDER = "<CAPTIONS_EDITS_DIR>"


def test_build_extra_args_matches_the_recorded_golden_outputs(monkeypatch):
    monkeypatch.setattr(web_app, "CAPTIONS_EDITS_DIR", CAPTIONS_PLACEHOLDER)
    with open(GOLDEN, encoding="utf-8") as f:
        cases = json.load(f)
    assert len(cases) >= 1400
    bad = []
    for case in cases:
        try:
            out = web_app._build_extra_args(case["script"], case["payload"], batch_overrides_path="bo", layers_path="ly")
        except Exception as e:
            out = "EXC:" + type(e).__name__
        if out != case["out"]:
            bad.append((case["script"], case["payload"], out, case["out"]))
    assert not bad, f"{len(bad)} שינויי פלט, ראשון: {bad[0]}"


def test_unknown_script_gets_no_args():
    assert web_app._build_extra_args("nope.py", {"codec": "h265"}) == []