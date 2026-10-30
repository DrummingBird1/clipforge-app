# tests/bot/test_script_metadata_conventions.py
#
# בדיקה סטטית שכל my_scripts/*.py עומד במוסכמת הכותרת (utils/shared/script_metadata.py)
# בדיוק - לא מסתמכת על get_script_metadata() עצמו (שיש לו fallback סלחני
# בכוונה בזמן ריצה: שם חסר -> שם הקובץ, תגית שגויה -> heavy), כדי לתפוס
# טעויות הקלדה אמיתיות (כמו "# Concurrency: ligth") שאף פעם לא היו גורמות
# לקריסה - רק לנפילה שקטה לברירת המחדל, בלי שום אזהרה.
import glob
from tests import PROJECT_ROOT
import os

import pytest

BASE_DIR = PROJECT_ROOT
SCRIPTS = sorted(glob.glob(os.path.join(BASE_DIR, "my_scripts", "**", "*.py"), recursive=True))
HEADER_WINDOW = 12  # תואם ל-utils/shared/script_metadata.py


def _read_header(path):
    with open(path, "r", encoding="utf-8") as f:
        return [f.readline() for _ in range(HEADER_WINDOW)]


def _ids(paths):
    return [os.path.relpath(p, BASE_DIR) for p in paths]


@pytest.mark.parametrize("path", SCRIPTS, ids=_ids(SCRIPTS))
def test_has_required_name_and_description_fields(path):
    header = _read_header(path)
    # # Safety: (בניגוד ל-# Concurrency:) הוא חובה, לא אופציונלי - זה תג אמון
    # (האם הסקריפט נוגע בקבצי המשתמש) שצריך שיהיה מפורש בכל סקריפט, לא מוסתר
    # מאחורי ברירת מחדל שמרנית ב-get_script_metadata().
    required = ["# Name:", "# Name (EN):", "# Description:", "# Description (EN):", "# Safety:"]
    missing = [field for field in required if not any(line.startswith(field) for line in header)]
    assert not missing, f"missing header field(s) in first {HEADER_WINDOW} lines: {missing}"


@pytest.mark.parametrize("path", SCRIPTS, ids=_ids(SCRIPTS))
def test_safety_tag_has_valid_value(path):
    header = _read_header(path)
    safety_lines = [line.strip() for line in header if line.strip().startswith("# Safety:")]
    if not safety_lines:
        return  # תלוי ב-test_has_required_name_and_description_fields כדי לתפוס היעדרות
    assert len(safety_lines) == 1, "more than one # Safety: line in the header"
    value = safety_lines[0][len("# Safety:"):].strip().lower()
    assert value in ("read-only", "modifies"), (
        f"'# Safety: {value}' is not 'read-only' or 'modifies' - "
        f"get_script_metadata() silently falls back to the conservative 'modifies' for any other value"
    )


@pytest.mark.parametrize("path", SCRIPTS, ids=_ids(SCRIPTS))
def test_concurrency_tag_is_valid_when_present(path):
    header = _read_header(path)
    concurrency_lines = [line.strip() for line in header if line.strip().startswith("# Concurrency:")]
    if not concurrency_lines:
        return  # אופציונלי - ברירת המחדל heavy תקפה
    assert len(concurrency_lines) == 1, "more than one # Concurrency: line in the header"
    # get_script_metadata() משווה עם .lower() - אז הבדיקה כאן צריכה לעשות אותו דבר,
    # ולתפוס רק ערכים שבאמת ייפלו בשקט ל-heavy (למשל "ligth"), לא רק אותיות גדולות.
    value = concurrency_lines[0][len("# Concurrency:"):].strip().lower()
    assert value in ("light", "heavy"), (
        f"'# Concurrency: {value}' is not 'light' or 'heavy' - "
        f"get_script_metadata() silently falls back to heavy for any other value"
    )
