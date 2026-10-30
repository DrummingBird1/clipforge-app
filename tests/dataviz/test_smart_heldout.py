# tests/dataviz/test_smart_heldout.py
#
# 20.10.2026: ציון עצמאי (held-out) לגלאי החכם (src/dataviz/smart/) על 8 תיקיות שהוא לא כויל עליהן -
# tests/data/dataviz_smart_heldout/ (נתונים סינתטיים, expected.json נכתב לפני ההרצה הראשונה). אותה פונקציית ציון של
# הגלאי (score.score_folder), רק שה-expected בא מ-expected.json ולא מ-config.yaml. בנוסף: התפקיד של כל קובץ (סדרה /
# אירועים) ושורת סך שאסור שתהיה ישות.
#
# הציון של היום (55%) הוא רצפה; כל מה שנכשל היום מסומן xfail עם הסיבה - מטרות גלויות לעורך הגרפים. strict: כשמקרה
# מתוקן הטסט שלו נכשל כ-XPASS - להוציא אותו מ-XFAIL (ולהעלות את FLOOR), כדי שהרצפה רק תעלה.
import functools
import json
import os

import pytest

from dataviz.smart import scan, score
from tests import TESTS_DIR

ROOT = os.path.join(TESTS_DIR, "data", "dataviz_smart_heldout")
# התשובות מחוץ לתיקיות הפרק (מ-20.10.2026, כמו ב-v2) - הגלאי סורק כל קובץ בתיקייה, ולא אמור לראות אותן
EXPECTED_DIR = os.path.join(ROOT, "_expected")
FOLDERS = sorted(n[:-5] for n in os.listdir(EXPECTED_DIR) if n.endswith(".json"))
FIELDS = list(score.METRICS) + ["roles", "excludes"]
FLOOR = 0.96   # 20.10.2026 (אחרי תיקוני הגלאי - חודשים בעברית, טבלה רחבה, xlsx, רבעונים, שורת סך, אירועים בלי כותרת, MW,
#               עדות לחלקים של סך): 0.969. היה 0.549.

# מה שעדיין לא מתאים - קריאות שיפוט (המפנה, 20.10: לא חובה). עורך הגרפים: כותרת = הקובץ הראשון לפי שם, ושתי יחידות =
# קווים עם שני צירים; כאן ה-expected בוחר את ההכנסות ופיזור. אפשר להצדיק את שתיהן - נשאר xfail.
XFAIL = {
    ("two_units_tourism", "value"): "judgment call: the main series is the first file by name (hotel_nights) - expected the revenue source",
    ("two_units_tourism", "chart"): "judgment call: two units get dual-axis lines (line_race) - expected scatter_race for two measures per region",
}


def _expected(folder):
    with open(os.path.join(EXPECTED_DIR, os.path.basename(os.path.normpath(folder)) + ".json"), encoding="utf-8") as f:
        return json.load(f)


@functools.lru_cache(maxsize=None)
def _result(name):
    folder = os.path.join(ROOT, name)
    want = _expected(folder)

    def expected_from_json(_folder):
        return {"file": sorted(want["series_files"]), "time": want["time"], "period": want["period"], "entity": want["entity"],
                "value": want["value"], "kind": want["kind"], "chart": want["chart"], "unit": want["unit"], "first_file": want["first_file"]}

    original = score.expected
    score.expected = expected_from_json   # פונקציית הציון של הגלאי, עם ה-expected של הקורפוס הזה
    try:
        row = score.score_folder(folder)
    finally:
        score.expected = original
    files = scan.scan_folder(folder)["files"]
    kinds = {f["name"]: f["kind"] for f in files}
    hits = dict(row["hits"])
    hits["roles"] = all(kinds.get(file) == kind for file, kind in want["files"].items())
    entities = [n for f in files if (f.get("roles") or {}).get("entity") for n in f["roles"]["entity"].get("names") or []]
    hits["excludes"] = None if "entity_excludes" not in want else not any(x in entities for x in want["entity_excludes"])
    return {"score": row["score"], "hits": hits, "got": {**row["got"], "roles": kinds}, "want": {**row["want"], "roles": want["files"]}}


def _cases():
    for name in FOLDERS:
        for field in FIELDS:
            marks = [pytest.mark.xfail(reason=XFAIL[(name, field)], strict=True)] if (name, field) in XFAIL else []
            yield pytest.param(name, field, marks=marks, id=f"{name}-{field}")


@pytest.mark.parametrize("name, field", list(_cases()))
def test_heldout_field(name, field):
    result = _result(name)
    hit = result["hits"][field]
    if hit is None:
        pytest.skip("no expectation for this field in this folder")
    assert hit, f"{name}.{field}: got {result['got'].get(field)!r}, expected {result['want'].get(field)!r}"


def test_heldout_average_score_does_not_drop():
    scores = {name: _result(name)["score"] for name in FOLDERS}
    average = sum(scores.values()) / len(scores)
    assert len(scores) == 8
    assert average >= FLOOR, f"held-out average {average:.1%} < floor {FLOOR:.0%}: {scores}"
