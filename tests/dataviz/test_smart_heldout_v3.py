# tests/dataviz/test_smart_heldout_v3.py
#
# 20.10.2026: הבדיקה העיוורת הסופית (v3) של הגלאי החכם - tests/data/dataviz_smart_heldout_v3/, 8 תיקיות שנכתבו עם
# התשובות (_expected/) לפני כל הרצה ונשמרו מחוץ לריפו עד שתיקוני v2 של עורך הגרפים היו סופיים (master 22fa156), ואז
# נוקדו פעם אחת. אף צד לא כויל עליהן - זה מבחן ההכללה. אותה פונקציית ציון של הגלאי (score.score_folder), ובנוסף
# התפקיד של כל קובץ.
#
# הציון של ההרצה היחידה (73.5%) הוא רצפה; מה שנכשל בה - xfail(strict) עם הסיבה. מכאן v3 כבר לא עיוור: תיקון שמכוון
# אליו הוא כיול, ומבחן הכללה הבא צריך קבוצה חדשה.
import functools
import json
import os

import pytest

from dataviz.smart import scan, score
from tests import TESTS_DIR

ROOT = os.path.join(TESTS_DIR, "data", "dataviz_smart_heldout_v3")
EXPECTED_DIR = os.path.join(ROOT, "_expected")
FOLDERS = sorted(n[:-5] for n in os.listdir(EXPECTED_DIR) if n.endswith(".json"))
FIELDS = list(score.METRICS) + ["roles"]
FLOOR = 0.99   # ההרצה העיוורת היחידה (20.10.2026, master 22fa156): 0.735. אחרי תיקונים כלליים (מטבע ומפרידים בתאים, שורת
#               יחידות, README שמציין עמודת ערך, ישויות כעמודות, אירועים בכותרות עבריות, תאריך קבוע באמצע החודש, GWh = כמות): 1.0 -
#               מכויל (ראו את ההערה למעלה), לא מבחן הכללה.
XFAIL: dict = {}


def _expected(name):
    with open(os.path.join(EXPECTED_DIR, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


@functools.lru_cache(maxsize=None)
def _result(name):
    folder = os.path.join(ROOT, name)
    want = _expected(name)

    def expected_from_json(_folder):
        return {"file": sorted(want["series_files"]), "time": want["time"], "period": want["period"], "entity": want["entity"],
                "value": want["value"], "kind": want["kind"], "chart": want["chart"], "unit": want["unit"], "first_file": want["first_file"]}

    original = score.expected
    score.expected = expected_from_json   # פונקציית הציון של הגלאי, עם התשובות של הקורפוס הזה
    try:
        row = score.score_folder(folder)
    finally:
        score.expected = original
    kinds = {f["name"]: f["kind"] for f in scan.scan_folder(folder)["files"]}
    hits = dict(row["hits"])
    hits["roles"] = all(kinds.get(file) == kind for file, kind in want["files"].items())
    return {"score": row["score"], "hits": hits, "got": {**row["got"], "roles": kinds}, "want": {**row["want"], "roles": want["files"]}}


def _cases():
    for name in FOLDERS:
        for field in FIELDS:
            marks = [pytest.mark.xfail(reason=XFAIL[(name, field)], strict=True)] if (name, field) in XFAIL else []
            yield pytest.param(name, field, marks=marks, id=f"{name}-{field}")


@pytest.mark.parametrize("name, field", list(_cases()))
def test_heldout_v3_field(name, field):
    result = _result(name)
    hit = result["hits"][field]
    if hit is None:
        pytest.skip("no expectation for this field in this folder")
    assert hit, f"{name}.{field}: got {result['got'].get(field)!r}, expected {result['want'].get(field)!r}"


def test_heldout_v3_average_score_does_not_drop():
    scores = {name: _result(name)["score"] for name in FOLDERS}
    average = sum(scores.values()) / len(scores)
    assert len(scores) == 8
    assert average >= FLOOR, f"held-out v3 average {average:.1%} < floor {FLOOR:.0%}: {scores}"
