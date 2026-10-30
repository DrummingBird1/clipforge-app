# tests/infra/test_atomic_write.py
#
# בודק utils/shared/atomic_write.py (item: בדיקת באגים מקיפה - כתיבה אטומית ל-JSON)
# - קורא ליעד רק אחרי הצלחה מלאה, לא משאיר קובץ זמני מאחור, ומוחק את הזמני
# גם על כשל תוך כדי כתיבה.
import json
import os


import pytest

from utils.shared.atomic_write import atomic_write_json


def test_writes_valid_json_readable_back(tmp_path):
    target = tmp_path / "data.json"
    atomic_write_json(str(target), {"a": 1, "b": "x"})

    with open(target, "r", encoding="utf-8") as f:
        assert json.load(f) == {"a": 1, "b": "x"}


def test_creates_parent_directory_if_missing(tmp_path):
    target = tmp_path / "nested" / "dir" / "data.json"
    atomic_write_json(str(target), {"ok": True})

    assert target.exists()


def test_passes_json_kwargs_through(tmp_path):
    target = tmp_path / "data.json"
    atomic_write_json(str(target), {"heb": "עברית"}, ensure_ascii=False, indent=2)

    content = target.read_text(encoding="utf-8")
    assert "עברית" in content  # ensure_ascii=False - לא ברח ל-\uXXXX
    assert "\n  " in content  # indent=2 - יש הזחה אמיתית


def test_no_leftover_temp_file_after_success(tmp_path):
    target = tmp_path / "data.json"
    atomic_write_json(str(target), {"a": 1})

    leftovers = [p for p in os.listdir(tmp_path) if p != "data.json"]
    assert leftovers == []


def test_overwrites_existing_file_completely(tmp_path):
    target = tmp_path / "data.json"
    atomic_write_json(str(target), {"old": True, "shared": 1})
    atomic_write_json(str(target), {"new": True})

    with open(target, "r", encoding="utf-8") as f:
        assert json.load(f) == {"new": True}


def test_leaves_original_file_untouched_when_dump_fails(tmp_path):
    target = tmp_path / "data.json"
    atomic_write_json(str(target), {"original": True})

    class Unserializable:
        pass

    with pytest.raises(TypeError):
        atomic_write_json(str(target), {"bad": Unserializable()})

    with open(target, "r", encoding="utf-8") as f:
        assert json.load(f) == {"original": True}  # הקובץ המקורי לא נגע בו כלל
    leftovers = [p for p in os.listdir(tmp_path) if p != "data.json"]
    assert leftovers == []  # קובץ הזמני נוקה גם על כשל
