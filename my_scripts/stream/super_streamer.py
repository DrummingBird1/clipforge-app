# Name: 📡 משדר-העל (Twitch/OBS/תיקיית-לכידה)
# Name (EN): 📡 Super Streamer (Twitch/OBS/Capture Folder)
# Description: מאחד את twitch_clip_import.py + obs_replay_watcher.py + capture_folder_watcher.py לסקריפט אחד עם בורר-מצב
# (--mode twitch|obs|folder) - שלושתם עושים בעצם את אותו דבר ("הכנס קליפים לתיקיית Import"), רק ממקור-לכידה שונה.
# twitch הוא הרצה חד-פעמית (מוריד ומסיים); obs/folder הם מאזינים ארוכי-טווח (רצים עד שנעצרים) - ומשם, לפי
# "אחרי שקליפ נכנס" בהגדרות Rocket, השרת עורך בסגנון שמור ו/או מפרסם כל קליפ חדש לבד.
# Description (EN): Unifies twitch_clip_import.py + obs_replay_watcher.py + capture_folder_watcher.py into one script with a mode
# selector (--mode twitch|obs|folder) - all three do the same thing ("get clips into the Import folder"), just from a different
# capture source. twitch is a one-shot run (downloads and exits); obs/folder are long-running listeners (run until stopped) - and
# from there, per "after a clip comes in" in the Rocket settings, the server edits with a saved style and/or publishes each new clip.
# Concurrency: light
# Safety: read-only
#
# item: איחוד סקריפטי "סטרימינג" ל"משדר-על" - אותו עיקרון בדיוק כמו
# my_scripts/tools/super_manager.py: שלושת הסקריפטים המקוריים נשארים כמו
# שהם (עדיין ניתנים להרצה עצמאית ישירות, לפני שהועברו לארכיון) וכאן רק
# עטיפה דקה שטוענת את המודול הנכון ומריצה את main() שלו, אחרי סינון sys.argv
# לדגלים הרלוונטיים למצב הנבחר בלבד. obs_replay_watcher.py/capture_folder_watcher.py
# עברו רפקטור קטן (עטיפת בלוק __main__ הקיים שלהם ב-def main(), התנהגות
# זהה לגמרי) כדי שלשלושתם תהיה אותה מוסכמת-כניסה כמו ש-twitch_clip_import.py
# כבר השתמש בה - בלי זה הבורר כאן היה צריך שלושה מנגנוני-קריאה שונים.

import argparse
import importlib.util
import os
import sys

if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STREAM_DIR = os.path.dirname(os.path.abspath(__file__))

parser = argparse.ArgumentParser(description="משדר-העל - ייבוא Twitch/מעקב OBS/מעקב תיקיית-לכידה, לפי --mode")
parser.add_argument("--mode", choices=["twitch", "obs", "folder"], default="folder", help="איזה מקור-לכידה להריץ.")
# --input_dir (שworker.py מזין תמיד) לא מוגדר כאן בכוונה - אותה מוסכמה
# בדיוק כמו super_manager.py: נופל ל-_unknown ועובר למצב הפנימי הנבחר, ששם
# הוא כן מוכר ומשמש בפועל (כל שלושת המקוריים תומכים בו).
args, _unknown = parser.parse_known_args()

_MODE_TO_SCRIPT = {
    "twitch": "twitch_clip_import.py",
    "obs": "obs_replay_watcher.py",
    "folder": "capture_folder_watcher.py",
}


def _load_module_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    script_filename = _MODE_TO_SCRIPT[args.mode]
    module_name = os.path.splitext(script_filename)[0]
    original_argv = sys.argv
    try:
        sys.argv = [script_filename] + _unknown
        module = _load_module_from_path(module_name, os.path.join(STREAM_DIR, script_filename))
        module.main()
    finally:
        sys.argv = original_argv


if __name__ == "__main__":
    main()
