# Name: 📁 מעקב תיקיית לכידה (Streamlabs/ShadowPlay/כל כלי אחר)
# Name (EN): 📁 Capture Folder Watcher (Streamlabs/ShadowPlay/any other tool)
# Description: מעקב אחרי תיקיית פלט של תוכנת לכידה כלשהי (Streamlabs, NVIDIA ShadowPlay/Instant Replay, או כל כלי אחר ששומר קבצי וידאו לתיקייה קבועה) ומעתיק אוטומטית כל קובץ חדש שיציב (לא עדיין נכתב) לתוך תיקיית ה-Import. בניגוד למעקב OBS (obs_replay_watcher.py) שמתחבר ל-API של OBS ומגיב על אירוע אמיתי, כאן אין API מוכר/אחיד לתוכנות האלה - הפתרון האמין היחיד הוא בדיקה תקופתית של התיקייה עצמה, ולכן זה גם עובד עם כל תוכנת לכידה אחרת ששומרת קבצים לתיקייה, לא רק שתיים ספציפיות.
# Description (EN): Watches a capture tool's output folder (Streamlabs, NVIDIA ShadowPlay/Instant Replay, or any other tool that saves video files to a fixed folder) and automatically copies every new, stable (no longer being written to) file into the Import folder. Unlike the OBS watcher (obs_replay_watcher.py), which connects to OBS's own API and reacts to a real event, there is no common/standard API for these tools - periodic polling of the folder itself is the only reliable option, which also makes this work with any other folder-based capture tool, not just two specific named ones.
# Safety: read-only
#
# זהו סקריפט מאזין ארוך-טווח (לא "הרץ פעם אחת וסיים" כמו שאר my_scripts) -
# מריצים אותו מה-GUI ומשאירים רץ ברקע; "🛑 עצור רינדור" ב-GUI עוצר אותו.
# אותו עיקרון בדיוק כמו my_scripts/stream/obs_replay_watcher.py.

import argparse
import json
import os
import shutil
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from utils.media.auto_chain import clip_ready_line  # noqa: E402
from utils.media.capture_watcher import already_copied, list_video_files, update_size_history  # noqa: E402
from utils.shared import data_paths

POLL_INTERVAL_SECONDS = 3

parser = argparse.ArgumentParser()
parser.add_argument("--input_dir", type=str, default="", help="לא בשימוש ישיר - נשמר לתאימות עם worker.py")
args, _unknown = parser.parse_known_args()


def load_settings():
    settings_path = data_paths.path(data_paths.ROCKET_SETTINGS)
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def watch(watch_dir, target_dir, poll_interval=POLL_INTERVAL_SECONDS):
    print(f"🟢 מעקב אחרי תיקיית לכידה: {watch_dir} -> מעתיק ל-{target_dir}...")
    sys.stdout.flush()

    size_history = {}  # filename -> list of sizes seen across the last checks
    while True:
        current_files = list_video_files(watch_dir)

        for filename in list(size_history.keys()):
            if filename not in current_files:
                del size_history[filename]

        for filename, full_path in current_files.items():
            if already_copied(filename, target_dir):
                size_history.pop(filename, None)
                continue
            try:
                size = os.path.getsize(full_path)
            except OSError:
                continue

            is_stable = update_size_history(size_history, filename, size)
            if not is_stable:
                continue

            try:
                dest = os.path.join(target_dir, filename)
                shutil.copy2(full_path, dest)
                print(f"✅ קובץ לכידה הועבר לפייפליין: {filename}")
                # גל 32: השרת (ממשק הדפדפן) ממשיך מכאן לפי "אחרי שקליפ נכנס" בהגדרות Rocket
                print(clip_ready_line(dest, "folder"))
            except Exception as e:
                print(f"❌ העברת {filename} נכשלה: {e}")
            sys.stdout.flush()
            size_history.pop(filename, None)

        time.sleep(poll_interval)


def main():
    settings = load_settings()
    configured_watch_dir = (settings.get("capture_watch_dir") or "").strip()
    if not configured_watch_dir:
        print("[ERROR] לא הוגדרה תיקיית מעקב (capture_watch_dir בהגדרות Rocket) - אין מה לעקוב אחריו. ביטול.")
        sys.stdout.flush()
        sys.exit(1)
    if not os.path.isdir(configured_watch_dir):
        print(f"[ERROR] תיקיית המעקב שהוגדרה אינה קיימת: {configured_watch_dir}")
        sys.stdout.flush()
        sys.exit(1)

    target = args.input_dir or settings.get("input_dir", BASE_DIR)
    os.makedirs(target, exist_ok=True)

    try:
        watch(configured_watch_dir, target)
    except KeyboardInterrupt:
        print("\n🛑 המאזין הופסק.")


if __name__ == "__main__":
    main()
