# tests/infra/test_public_default_names.py
#
# 30.10.2026, הכנה להפצה ציבורית: הטקסטים שמשתמש חדש רואה לא מזכירים שמות ערוצים מסוימים (RLShorts, PShorts), שמות מהקובץ
# המקומי או את Rocket League כדוגמה - רק דוגמאות כלליות ("Clip #42", "קליפים של משחקים"). שמות קבצים ומודולים
# (rocket_shorts_publisher.py) לא בכלל הזה, וגם לא זיהוי משחקים (game_detector, seo_generator).
import importlib.util
import re
from pathlib import Path

from tests import PROJECT_ROOT
from utils.video.video_editor_field_help import FIELD_HELP

# 30.10.2026: שמות הבעלים לא כתובים כאן (הקובץ יוצא לציבור) - הם בדפוסים המקומיים של dev/export_public.py, כשהקובץ קיים
_spec = importlib.util.spec_from_file_location("export_public", Path(PROJECT_ROOT) / "dev" / "export_public.py")
_export_public = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_export_public)
_LOCAL = _export_public.personal_patterns(_export_public.local_patterns_file(PROJECT_ROOT))
PERSONAL = re.compile("|".join([r"RLShorts|PShorts|Rocket League"] + [p for k, p in _LOCAL.items() if k == "owner-name"]),
                      re.IGNORECASE)
ROOT = Path(PROJECT_ROOT)
FRONTEND = ROOT / "src" / "entrypoints" / "web" / "frontend"


def test_the_web_screens_use_generic_examples():
    hits = []
    for path in sorted(FRONTEND.rglob("*")):
        if path.suffix in (".html", ".js", ".css"):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if PERSONAL.search(line):
                    hits.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()[:120]}")
    assert hits == []


def test_the_editor_field_help_uses_generic_examples():
    hits = [key for key, help_ in FIELD_HELP.items() if PERSONAL.search(f"{help_[0]} {help_[1]}")]
    assert hits == []
    assert "Clip #42" in FIELD_HELP["number_videos"][1]
