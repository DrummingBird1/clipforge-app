# tests/bot/test_super_streamer.py
#
# my_scripts/stream/super_streamer.py ("משדר-העל") מאחד את twitch_clip_import.py
# + obs_replay_watcher.py + capture_folder_watcher.py לסקריפט אחד עם בורר-מצב
# (--mode). בודק את מנגנון-הבורר (טעינה דינמית + main() לכל שלושת המצבים,
# כולל שני המצבים שעברו רפקטור קטן - עטיפת בלוק __main__ הקיים שלהם ב-def
# main() - כדי לתמוך בבורר) - לא את לוגיקת ההורדה/מעקב עצמה, שכבר מכוסה
# ב-tests/bot/test_obs_replay_watcher.py/test_capture_folder_watcher.py (אותם
# קבצי מקור בדיוק). מצב "obs" לא נבדק כאן ב-E2E מאותה סיבה שכבר תועדה ב-
# obs_replay_watcher.py עצמו - אין OBS אמיתי בסביבה הזו; "twitch"/"folder"
# נבדקים במצב-כשל-מוגדר-מראש (בלי אישורים/תיקיית-מעקב), אותו עיקרון בדיוק
# כמו test_duplicate_cleaner.py's test_missing_report_file_fails_clearly.
import os
from tests import PROJECT_ROOT
import subprocess
import sys

BASE_DIR = PROJECT_ROOT
SCRIPT = os.path.join(BASE_DIR, "my_scripts", "stream", "super_streamer.py")


def _run(args, timeout=30):
    cmd = [sys.executable, SCRIPT, *args]
    return subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=timeout)


def test_folder_mode_is_the_default_when_mode_omitted():
    result = _run([])
    assert result.returncode != 0  # capture_watch_dir לא מוגדר בסביבת הטסטים
    assert "לא הוגדרה תיקיית מעקב" in result.stdout


def test_folder_mode_fails_clearly_without_a_configured_watch_dir():
    result = _run(["--mode", "folder"])
    assert result.returncode != 0
    assert "לא הוגדרה תיקיית מעקב" in result.stdout


def test_twitch_mode_fails_clearly_without_credentials():
    result = _run(["--mode", "twitch"])
    assert result.returncode == 0  # twitch_clip_import.py's main() מדפיס ומחזיר בלי sys.exit
    assert "TWITCH_CLIENT_ID" in result.stdout


def test_twitch_mode_passes_through_the_limit_flag(monkeypatch, tmp_path):
    # לא ניתן לבדוק הורדה אמיתית (אין חשבון Twitch בסביבה הזו), אבל אפשר
    # לוודא ש---limit בכלל מגיע ל-argparse הפנימי של twitch_clip_import.py
    # ולא נבלע ע"י ה-parser החיצוני (שלא מגדיר אותו כלל) - אם היה נבלע,
    # ההרצה הייתה נכשלת עם "unrecognized arguments" במקום להגיע להודעת
    # האישורים-החסרים הרגילה.
    result = _run(["--mode", "twitch", "--limit", "3"])
    assert result.returncode == 0
    assert "unrecognized arguments" not in (result.stderr or "")
    assert "TWITCH_CLIENT_ID" in result.stdout


def test_invalid_mode_rejected_by_argparse_choices():
    result = _run(["--mode", "not-a-real-mode"])
    assert result.returncode != 0
    assert "invalid choice" in (result.stderr or "")


def test_obs_and_folder_watcher_scripts_expose_a_main_function_after_refactor():
    # item: איחוד סטרימינג - שני הסקריפטים המקוריים עברו רפקטור קטן (עטיפת
    # בלוק __main__ הקיים שלהם ב-def main(), התנהגות זהה) כדי שלשלושתם תהיה
    # אותה מוסכמת-כניסה כמו twitch_clip_import.py - בודק שהרפקטור לא "איבד"
    # את הפונקציה בטעות.
    sys.path.insert(0, os.path.dirname(BASE_DIR))
    from my_scripts.stream import obs_replay_watcher, capture_folder_watcher, twitch_clip_import
    assert callable(obs_replay_watcher.main)
    assert callable(capture_folder_watcher.main)
    assert callable(twitch_clip_import.main)


