# tests/infra/test_dev_folder.py
#
# 23.10.2026 (סדר התיקיות, 16): כלי הפיתוח והמשגרים עברו מ-src/scripts/ ל-dev/ - src/ נשאר לקוד שהאפליקציה מריצה. אין עוד
# הפניה לנתיב הישן (חוץ מהיסטוריה), וכל קובץ .vbs בשורש מפעיל .bat שקיים.
import os
import re

from tests import PROJECT_ROOT

SKIP_DIRS = {".git", ".venv", "node_modules", "ffmpeg", "workspace", "data", ".claude", os.path.join("docs", "handoff"),
             os.path.join("docs", "history")}


def test_nothing_points_at_src_scripts_any_more():
    # 25.10.2026: src/scripts/__pycache__ (בייטקוד שנשאר מלפני המעבר, לא בגיט) הוא לא קוד - רק קובץ אמיתי שם הוא חזרה אחורה
    old = os.path.join(PROJECT_ROOT, "src", "scripts")
    assert not os.path.exists(old) or all(name == "__pycache__" for name in os.listdir(old))
    stale = []
    for dirpath, dirnames, filenames in os.walk(PROJECT_ROOT):
        rel_dir = os.path.relpath(dirpath, PROJECT_ROOT)
        dirnames[:] = [d for d in dirnames if os.path.normpath(os.path.join(rel_dir, d)) not in SKIP_DIRS]
        for name in filenames:
            if os.path.join(dirpath, name) == os.path.abspath(__file__):
                continue   # הטסט עצמו מזכיר את הנתיב הישן
            if name.endswith((".py", ".pyw", ".md", ".js", ".css", ".html", ".bat", ".vbs", ".yml", ".toml")):
                with open(os.path.join(dirpath, name), encoding="utf-8", errors="replace") as f:
                    if re.search(r"src[/\\]scripts", f.read()):
                        stale.append(os.path.relpath(os.path.join(dirpath, name), PROJECT_ROOT))
    assert stale == [], f"הפניה ל-src/scripts (עבר ל-dev/): {stale}"


def test_every_launcher_runs_an_existing_batch_file():
    # (18) רק WebLauncher.vbs בשורש; dev/Launcher.vbs (ה-GUI השולחני) מפעיל את ה-.bat שלידו - batPath יחסית לתיקייה של ה-vbs
    assert sorted(n for n in os.listdir(PROJECT_ROOT) if n.endswith(".vbs")) == ["WebLauncher.vbs"]
    launchers = [(folder, n) for folder in (PROJECT_ROOT, os.path.join(PROJECT_ROOT, "dev"))
                 for n in sorted(os.listdir(folder)) if n.endswith(".vbs")]
    assert len(launchers) == 2
    for folder, name in launchers:
        with open(os.path.join(folder, name), encoding="utf-8", errors="replace") as f:
            match = re.search(r'batPath = scriptDir & "\\([^"]+)"', f.read())
        assert match, name
        assert os.path.isfile(os.path.join(folder, *match.group(1).split("\\"))), (name, match.group(1))
