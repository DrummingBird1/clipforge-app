# Name: 📅 ריקאפ תקופתי
# Name (EN): 📅 Periodic Recap
# Description: מאחד את קליפי ה-YouTube שפורסמו בשבוע/חודש/שנה האחרונים (או מספר ימים לבחירה) לסרטון ריקאפ אחד, כולל קובץ פרקים ליוטיוב.
# Description (EN): Merges the YouTube clips published in the last week/month/year (or a chosen number of days) into a single recap video, with a YouTube chapters file alongside it.
# Safety: read-only

import argparse
import glob
import json
import os
import subprocess
import sys
import time

if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from utils.media.compilation import build_chapters_text, recap_label_for_period, resolve_period_days
from utils.shared.workspace_dir import ROCKET_SHORTS, existing_output_dir
from utils.shared.export_dir import follow_global  # כמו OUTPUT_BASE_DIR של rocket_shorts_publisher.py
from utils.shared.ffmpeg_locator import get_ffmpeg_exe
from utils.media.ffprobe_cache import probe_video
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
from utils.shared import data_paths
FFMPEG_EXE = get_ffmpeg_exe()

parser = argparse.ArgumentParser()
parser.add_argument("--input_dir", type=str, default="", help="לא בשימוש ישיר - נשמר לתאימות עם worker.py")
parser.add_argument("--days", type=int, default=None, help="כמה ימים אחורה לכלול בריקאפ - גובר על --period אם שניהם ניתנו")
parser.add_argument("--period", choices=["week", "month", "year"], default=None, help="נוחות במקום --days: week=7, month=30, year=365 ימים")
parser.add_argument("--source", choices=["youtube", "tiktok"], default="youtube")
parser.add_argument("--output_base", type=str, default="", help="דריסת תיקיית הבסיס לבדיקות - ברירת מחדל: output_dir מההגדרות")
args, _unknown = parser.parse_known_args()
args.days = resolve_period_days(args.period, args.days)


def load_settings():
    settings_path = data_paths.path(data_paths.ROCKET_SETTINGS)
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def main():
    settings = load_settings()
    output_base = args.output_base or follow_global(settings.get("output_dir", BASE_DIR))
    # אותן תיקיות כמו rocket_shorts_publisher.py's YT_DIR/TT_DIR (rocket_shorts/YouTube|TikTok); לפני סקריפט ההעברה -
    # התיקייה הישנה (horizontal/YouTube, vertical/TikTok) אם רק היא קיימת
    source_dir = existing_output_dir(ROCKET_SHORTS, "YouTube" if args.source == "youtube" else "TikTok", base=output_base)

    if not os.path.exists(source_dir):
        print(f"❌ תיקיית המקור לא קיימת: {source_dir}")
        return

    cutoff = time.time() - (args.days * 86400)
    clips = []
    for path in glob.glob(os.path.join(source_dir, "*.mp4")):
        # מדלג על פלטי ריקאפ קודמים (Weekly_Recap_/Monthly_Recap_/Yearly_Recap_,
        # כולם יושבים באותה source_dir כמו הקליפים הרגילים) - אחרת ריקאפ חודשי
        # היה כולל בטעות ריקאפים שבועיים קודמים כ"קליפים" משלו.
        if "_Recap_" in os.path.basename(path):
            continue
        if os.path.getmtime(path) >= cutoff:
            clips.append(path)

    clips.sort(key=os.path.getmtime)

    if not clips:
        print(f"ℹ️ לא נמצאו קליפים חדשים ב-{args.days} הימים האחרונים ב-{source_dir}.")
        return

    print(f"🎬 נמצאו {len(clips)} קליפים לריקאפ מ-{args.days} הימים האחרונים:")
    for c in clips:
        print(f"  • {os.path.basename(c)}")
    sys.stdout.flush()

    concat_list_path = os.path.join(source_dir, "_weekly_concat_list.txt")
    with open(concat_list_path, "w", encoding="utf-8") as f:
        for c in clips:
            escaped = c.replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")

    date_str = time.strftime("%Y-%m-%d")
    recap_label = recap_label_for_period(args.period)
    output_path = os.path.join(source_dir, f"{recap_label}_Recap_{date_str}.mp4")

    # ניסיון ראשון: concat מהיר בלי רה-קידוד (-c copy) - עובד רק אם כל הקליפים חולקים פרמטרים זהים
    cmd_copy = [FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path, "-c", "copy", output_path]
    result = subprocess.run(cmd_copy, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=NO_WINDOW_FLAGS)

    success = result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0

    if not success:
        print("⚠️ concat מהיר (ללא רה-קידוד) נכשל - כנראה שהקליפים לא חולקים פרמטרים זהים. מנסה עם רה-קידוד...")
        sys.stdout.flush()
        cmd_reencode = [
            FFMPEG_EXE, "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-c:a", "aac", output_path
        ]
        result = subprocess.run(cmd_reencode, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=NO_WINDOW_FLAGS)
        success = result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0

    os.remove(concat_list_path)  # safe: temp ffmpeg concat-list file this script wrote itself, not user input

    if success:
        print(f"\n✅ ריקאפ נוצר בהצלחה: {output_path}")
        # פרקים אוטומטיים (item) - קובץ טקסט צמוד מוכן-להדבקה בתיאור יוטיוב;
        # יוטיוב יזהה את זה כפרקים לבד (chapters) כל עוד יש לפחות 3 קטעים בני
        # 10+ שניות - לא נאכף כאן, רק מיוצר. משך כל קליפ נשלף דרך אותו
        # probe_video ממוטמן ש-video_editor.py/timelapse_maker.py כבר משתמשים
        # בו, לא ffprobe נפרד לכל קובץ.
        chapter_entries = [(os.path.basename(c), probe_video(c).get("duration") or 0.0) for c in clips]
        chapters_path = output_path + ".chapters.txt"
        try:
            with open(chapters_path, "w", encoding="utf-8") as f:
                f.write(build_chapters_text(chapter_entries))
            print(f"📑 פרקים ליוטיוב (הדבק בתיאור הסרטון): {chapters_path}")
        except OSError as e:
            print(f"⚠️ יצירת קובץ הפרקים נכשלה (הריקאפ עצמו כן נוצר): {e}")
    else:
        print(f"\n❌ יצירת הריקאפ נכשלה: {result.stderr[-800:]}")


if __name__ == "__main__":
    main()
