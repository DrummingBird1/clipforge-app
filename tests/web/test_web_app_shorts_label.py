# tests/web/test_web_app_shorts_label.py
#
# 30.10.2026 (לפני ההפצה, אישור המשתמש): "Rocket Shorts" נקרא "Shorts" בממשק - הלשונית, כפתור הבית, תפריט הצד, ההודעות
# וחיפוש הפקודות. שמות פנימיים, מזהי DOM (data-tab="rocket"), נתיבי API ותיקיית הפלט rocket_shorts לא משתנים. ערכת הנושא
# "Rocket League" מוצגת בבורר כ"כתום", והמפתח שלה ב-config.json נשאר.
import re
from pathlib import Path

from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from tests import PROJECT_ROOT

FRONTEND = Path(PROJECT_ROOT) / "src" / "entrypoints" / "web" / "frontend"
COMMENT = re.compile(r"^\s*(//|<!--|#)")
client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)


def test_the_screens_say_shorts():
    hits = []
    for path in sorted(FRONTEND.rglob("*")):
        if path.suffix in (".html", ".js"):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                code = line.partition(" // ")[0]
                if not COMMENT.match(line) and ("Rocket Shorts" in code or "הגדרות Rocket" in code):
                    hits.append(f"{path.name}:{number}")
    assert hits == []
    top = (FRONTEND / "html" / "10-body-top.html").read_text(encoding="utf-8")
    assert 'data-tab="rocket" onclick="switchTab(\'rocket\')">🚀 Shorts</button>' in top


def test_the_server_messages_and_the_english_dictionary_say_shorts():
    # 30.10.2026, השלמה ל-#108: ההודעות של השרשור והשגיאה של השליחה מעורך הגרפים, וגם המפתחות והערכים ב-en.json
    from utils.media import auto_chain
    assert auto_chain.describe({"action": "publish"}, "clip.mp4") == "clip.mp4 נשלח ישר לפרסום Shorts"
    for path in (Path(PROJECT_ROOT) / "src" / "entrypoints" / "web" / "i18n" / "en.json",
                 Path(PROJECT_ROOT) / "src" / "entrypoints" / "web" / "routes" / "dataviz.py"):
        code = [line for line in path.read_text(encoding="utf-8").splitlines() if not COMMENT.match(line) and '"' in line]
        assert not [line for line in code if "Rocket Shorts" in line.partition("#")[0]], path.name


def test_the_theme_keeps_its_key_and_shows_a_general_label():
    themes = client.get("/api/settings/themes").json()
    assert themes["Rocket League"]["label"] == "כתום" and themes["Rocket League"]["accent"]
    assert themes["Green"]["label"] == "Green"
