# Name: 🧹 מפנה-המקום בארכיון
# Name (EN): 🧹 Archive Space Freer
# Description: מעביר (לא מוחק) קליפי מקור ישנים שכבר עברו רינדור לתיקיית ארכיון, כדי לפנות שטח דיסק לאורך זמן.
# Description (EN): Moves (never deletes) old source clips that were already rendered into an archive folder, to free up disk space over time.
# Concurrency: light
# Safety: modifies
#
# היוריסטיקה: rocket_shorts_publisher.py לא מוחק/מזיז קבצי מקור אחרי עיבוד, אז כל
# קובץ שישן יותר מהרצה מוצלחת אחרונה שנרשמה ב-job_history כבר עבר עיבוד כמעט בוודאות
# (כל הרצה סורקת את כל תיקיית ה-Import). הסקריפט אף פעם לא מוחק בפועל - רק מעביר
# לתיקיית ארכיון, כדי שהפעולה תישאר הפיכה.

import argparse
import glob
import json
import os
import shutil
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
from utils.shared import db
from utils.shared.move_undo_log import record_move_batch
from utils.shared import data_paths

DB_PATH = data_paths.path(data_paths.BOT_DB)

parser = argparse.ArgumentParser()
parser.add_argument("--input_dir", type=str, default="", help="תיקיית המקור לבדיקה (אם ריק, נלקח מ-rocket_settings.json)")
parser.add_argument("--retention_days", type=int, default=0, help="גיל מינימלי בימים לפני העברה לארכיון (0 = השבת את הבדיקה)")
parser.add_argument("--dry-run", action="store_true")
args, _unknown = parser.parse_known_args()


def load_settings():
    settings_path = data_paths.path(data_paths.ROCKET_SETTINGS)
    if os.path.exists(settings_path):
        import json
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def get_last_successful_publish_time():
    if not os.path.exists(DB_PATH):
        return None
    try:
        with db.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT MAX(finished_at) FROM job_history WHERE script_name LIKE '%rocket_shorts_publisher%' AND status = 'success'"
            ).fetchone()
            return row[0] if row and row[0] else None
    except Exception:
        return None


def main():
    settings = load_settings()
    input_dir = args.input_dir or settings.get("input_dir", "")
    retention_days = args.retention_days or int(settings.get("cleanup_retention_days", 0) or 0)

    if not input_dir or not os.path.exists(input_dir):
        print(f"❌ תיקיית מקור לא תקינה: {input_dir}")
        return

    if retention_days <= 0:
        print("ℹ️ cleanup_retention_days אינו מוגדר (0) - הניקוי מושבת. אין מה לעשות.")
        return

    last_publish_iso = get_last_successful_publish_time()
    if not last_publish_iso:
        print("ℹ️ לא נמצאה עדיין הרצת פרסום מוצלחת ב-job_history. לא מעבירים כלום כדי לא לטעות.")
        return

    from datetime import datetime
    last_publish_ts = datetime.fromisoformat(last_publish_iso).timestamp()

    cutoff_age_ts = time.time() - (retention_days * 86400)
    archive_dir = os.path.join(input_dir, "Archived_Sources")

    video_extensions = ("*.mp4", "*.mkv", "*.mov", "*.avi")
    candidates = []
    for ext in video_extensions:
        candidates.extend(glob.glob(os.path.join(input_dir, ext)))

    moved = 0
    moves = []  # {"src", "dst"} לכל קובץ שהועבר בפועל - item: undo last file-move operation
    for path in candidates:
        mtime = os.path.getmtime(path)
        # רק קבצים שגם ישנים מגיל השמירה וגם ישנים יותר מהרצת הפרסום המוצלחת האחרונה
        if mtime < cutoff_age_ts and mtime < last_publish_ts:
            if args.dry_run:
                print(f"[DRY-RUN] היה מעביר לארכיון: {os.path.basename(path)}")
            else:
                os.makedirs(archive_dir, exist_ok=True)
                dst = os.path.join(archive_dir, os.path.basename(path))
                shutil.move(path, dst)
                moves.append({"src": path, "dst": dst})
                print(f"📦 הועבר לארכיון: {os.path.basename(path)}")
            moved += 1

    if moved == 0:
        print("✅ אין קבצי מקור ישנים מספיק להעברה כרגע.")
    else:
        print(f"\n{'[DRY-RUN] ' if args.dry_run else ''}סה\"כ {moved} קבצים {'שהיו מועברים' if args.dry_run else 'הועברו'} ל-Archived_Sources.")

    if moves:
        record_move_batch("cleanup_published_sources.py", moves)
        print("↩️ ניתן לבטל את ההעברה הזו (להחזיר את כל הקבצים למקורם) עד ריצת ניקוי הבאה.")

    print("RESULT: " + json.dumps({"files_moved": moved, "dry_run": args.dry_run}, ensure_ascii=False))


if __name__ == "__main__":
    main()
