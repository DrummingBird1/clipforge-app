# tests/dataviz/test_smart_heldout_v2.py
#
# 20.10.2026: ציון עצמאי שני (v2) לגלאי החכם - tests/data/dataviz_smart_heldout_v2/, 8 תיקיות חדשות (v1 כבר שימש לכיול).
# התשובות ב-_expected/<תיקייה>.json - מחוץ לתיקיות הפרק, כדי שהגלאי (שסורק כל קובץ בתיקייה) לא יראה אותן - ונשמרו
# בקומיט לפני ההרצה הראשונה. אותה פונקציית ציון של הגלאי (score.score_folder), ובנוסף תפקיד כל קובץ, ובסדרה של ישות
# אחת - שלא נבחרה עמודת ישות.
#
# הציון של היום (51%) הוא רצפה; מה שנכשל היום - xfail(strict) עם הסיבה. כשמקרה מתוקן הוא נכשל כ-XPASS: להוציא אותו
# מ-XFAIL ולהעלות את FLOOR.
import functools
import json
import os

import pytest

from dataviz.smart import scan, score
from tests import TESTS_DIR

ROOT = os.path.join(TESTS_DIR, "data", "dataviz_smart_heldout_v2")
EXPECTED_DIR = os.path.join(ROOT, "_expected")
FOLDERS = sorted(n[:-5] for n in os.listdir(EXPECTED_DIR) if n.endswith(".json"))
FIELDS = list(score.METRICS) + ["roles", "no_entity"]
FLOOR = 0.99   # 20.10.2026: 0.511 -> 1.0 אחרי תיקונים כלליים בגלאי ובמנוע (מפריד ונקודה עשרונית, שנות כספים, JSON של רשומות,
#               שורת כותרת לפי תוכן, יחידות מסיומות, סדרה אחת = קו, מטבע לפי מחיר-ליחידה). שני השדות האחרונים (€ ותרשים של מחיר / תקציב)
#               תוקנו אחרי שהודעות הכישלון הראו את הערך הצפוי - כבר לא סמוי לגמרי.

_ALL = [f for f in FIELDS if f != "no_entity"]
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
    hits["no_entity"] = (row["got"].get("entity") is None) if want.get("no_entity") else None
    return {"score": row["score"], "hits": hits, "got": {**row["got"], "roles": kinds}, "want": {**row["want"], "roles": want["files"]}}


def _cases():
    for name in FOLDERS:
        for field in FIELDS:
            marks = [pytest.mark.xfail(reason=XFAIL[(name, field)], strict=True)] if (name, field) in XFAIL else []
            yield pytest.param(name, field, marks=marks, id=f"{name}-{field}")


@pytest.mark.parametrize("name, field", list(_cases()))
def test_heldout_v2_field(name, field):
    result = _result(name)
    hit = result["hits"][field]
    if hit is None:
        pytest.skip("no expectation for this field in this folder")
    assert hit, f"{name}.{field}: got {result['got'].get(field)!r}, expected {result['want'].get(field)!r}"


def test_heldout_v2_average_score_does_not_drop():
    scores = {name: _result(name)["score"] for name in FOLDERS}
    average = sum(scores.values()) / len(scores)
    assert len(scores) == 8
    assert average >= FLOOR, f"held-out v2 average {average:.1%} < floor {FLOOR:.0%}: {scores}"
