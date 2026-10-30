# tests/web/test_web_frontend_areas.py - גל 37: כל קובץ JS שייך לאזור אחד (web/frontend_areas.json), וה-API הפנימי
# של האזורים (js/81-editor-api.js) מפנה רק לפונקציות שקיימות.
import json
import os
import re

from entrypoints.web import frontend_assembly as fa

AREAS_PATH = os.path.join(os.path.dirname(fa.FRONTEND_DIR), "frontend_areas.json")


def _areas():
    with open(AREAS_PATH, encoding="utf-8") as f:
        return json.load(f)["areas"]


def test_every_js_part_belongs_to_exactly_one_area():
    listed = [part for parts in _areas().values() for part in parts]
    js_parts = [part for part in fa.page_parts() if part.endswith(".js")]
    duplicates = sorted({part for part in listed if listed.count(part) > 1})
    assert duplicates == []
    assert sorted(set(js_parts) - set(listed)) == [], "קובץ JS חדש בלי אזור - הוסף אותו ל-web/frontend_areas.json"
    assert sorted(set(listed) - set(js_parts)) == [], "frontend_areas.json מזכיר קובץ שלא ב-parts.txt"


def test_the_internal_api_calls_only_existing_functions():
    api = fa.read_part("js/81-editor-api.js")
    bundle = fa.bundle("js")
    called = sorted(set(re.findall(r"=> \{? ?([A-Za-z_]\w*)\(", api)) | set(re.findall(r"; ([A-Za-z_]\w*)\(", api)))
    assert len(called) > 20
    missing = [name for name in called if not re.search(rf"(?:function\s+{name}\s*\(|(?:const|let|var)\s+{name}\s*=|^{name}\s*=)", bundle, re.M)]
    assert missing == [], missing
    for area in ("queue", "timeline", "inspector", "layers", "library", "player", "runs"):
        assert re.search(rf"^\s+{area}: Object\.freeze\(", api, re.M), area
