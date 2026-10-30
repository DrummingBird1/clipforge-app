# Name: 🕵️ בלש הכונן (כפילויות וקבצי זבל)
# Name (EN): 🕵️ Disk Detective (Duplicates & Junk)
# Description: סורק כונן/תיקייה שלמים - מפיק לכל קובץ גודל, ו-ffprobe (קודק/ביטרייט/משך)
# לקבצי מדיה, מאתר כפילויות לפי hash וקבצי זבל נפוצים, וכותב הכל ל-report.json בלבד
# (קורא-בלבד - לא מוחק/מזיז/משנה שום קובץ בכונן עצמו).
# Description (EN): Scans an entire drive/folder - produces size and ffprobe data (codec/bitrate/duration) for every media file, finds duplicates via hash, and flags common junk files. Read-only, writes only report.json.
# Concurrency: light
# Safety: read-only
#
# "חכם" = לא סתם hash מלא לכל קובץ. על כונן של טרה-בייטים זה היה לוקח נצח. במקום זה:
#   שלב 1: קיבוץ לפי גודל בייטים בדיוק - קובץ עם גודל ייחודי לא יכול להיות כפילות של
#           אף קובץ אחר, אז הוא כלל לא מועמד להמשך (רוב הקבצים בדרך כלל נופלים כאן).
#   שלב 2: quick_hash מהיר (1MB מההתחלה + 1MB מהסוף) לכל קובץ שחולק גודל עם קובץ אחר -
#           מסנן כמעט את כל ה"התאמות מקריות" של גודל זהה בלי לקרוא קבצים ענקיים בשלמותם.
#   שלב 3: full_hash (SHA-256 מלא) רק לקבוצות ששרדו גם גודל וגם quick_hash זהים -
#           רק שם באמת צריך לוודא זהות ביט-לביט.

import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from tqdm import tqdm

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from utils.shared.disk_report_paths import DEFAULT_REPORT_JSON
from utils.shared.ffmpeg_locator import get_ffprobe_exe
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

FFPROBE_EXE = get_ffprobe_exe()

MEDIA_EXTENSIONS = {
    ".mp4", ".mkv", ".mov", ".avi", ".wmv", ".flv", ".webm", ".m4v", ".mpg", ".mpeg", ".ts", ".m2ts",
    ".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".wma", ".opus",
}

# קבצי זבל מוכרים לפי שם/סיומת - כל אלה מוכרים כתוצרי לוואי חסרי ערך של Windows/
# תוכנות/דפדפנים, לא קבצי משתמש אמיתיים. לא כולל כלום שדורש שיפוט (כמו קבצי log) -
# רק דברים שאף אחד לא רוצה לשמור בכוונה.
JUNK_EXACT_NAMES = {"thumbs.db", "desktop.ini", ".ds_store", "ehthumbs.db"}
JUNK_EXTENSIONS = {".tmp", ".temp", ".bak", ".old", ".crdownload", ".part", ".download"}

# תיקיות מערכת שגישה אליהן חסומה ממילא ורק היו מייצרות ערמת שגיאות הרשאה בלוג
SKIP_DIR_NAMES = {"system volume information", "$recycle.bin"}

FILE_ATTRIBUTE_REPARSE_POINT = 0x400
skipped_reparse_points = []


def is_reparse_point(path):
    """מזהה Junction/Symlink של Windows (כמו אלה ש-pnpm/npm יוצרים ב-.pnpm-store).
    os.walk ממשיך "לרדת" לתוך Junction גם עם followlinks=False (זה משפיע רק על
    symlink רגיל, לא על junction) - אם ה-junction "תלוי" (מצביע על תיקייה שהוזזה/
    נמחקה, בדיוק כמו שקרה כאן עם .pnpm-store) זה מייצר "WinError 3: לא נמצא הנתיב"
    בשקט. יותר גרוע: junction שמצביע בחזרה על תיקיית-אב שלו יגרום לרקורסיה אינסופית.
    לכן מדלגים על junction/symlink לגמרי במקום לנסות להיכנס אליו."""
    if os.name != "nt":
        return False
    try:
        attrs = os.stat(path, follow_symlinks=False).st_file_attributes
        return bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)
    except (OSError, AttributeError):
        return False

QUICK_HASH_EDGE_BYTES = 1024 * 1024  # 1MB מכל קצה
FULL_HASH_READ_BUFFER = 1024 * 1024

# parse_known_args (לא parse_args) בכוונה: worker.py של ה-GUI מזין תמיד --input_dir
# <תיקיית הגיימפליי הנבחרת> לכל סקריפט שרץ מהסיידבר, בלי קשר לאיזה סקריפט זה -
# זו אותה מוסכמה בדיוק כמו ב-rocket_shorts_publisher.py/story_cutter.py. אסור
# להגדיר --input_dir כארגומנט אמיתי כאן ולתת לו לגבור על target_dir: הוא מייצג
# "תיקיית קליפים לעריכה" (מושג שלא קשור בכלל לסריקת כונן שלם), ואם המשתמש בחר
# פעם תיקייה כלשהי בטאב ההגדרות (למשל E:\), הסקריפט הזה היה סורק אותה בטעות
# במקום ברירת המחדל בכל הרצה מה-GUI - בדיוק מה שקרה בפועל. parse_known_args דואג
# שהדגל הזה פשוט יושמט בשקט, ו-target_dir נשאר תמיד מקור האמת היחיד.
parser = argparse.ArgumentParser(description="סורק כונן/תיקייה: ffprobe + כפילויות + קבצי זבל -> report.json")
# 30.10.2026: ברירת המחדל - תיקיית הבית של המשתמש (קודם כונן קבוע)
parser.add_argument("--target_dir", type=str, default=os.path.expanduser("~"), help="הכונן/תיקייה לסריקה (ברירת מחדל: תיקיית הבית)")
parser.add_argument("--output", type=str, default="", help="נתיב לקובץ הדוח (ברירת מחדל: workspace/reports/disk/report.json)")
parser.add_argument("--workers", type=int, default=4, help="כמה קבצים לעבד במקביל (hash/ffprobe)")
# ברירת המחדל היא ליצור גם Excel: הרצה מה-GUI (worker.py) לא מזינה שום דגל
# ספציפי-לסקריפט מלבד --input_dir הגנרי (שממילא מתעלמים ממנו למעלה) - אז דגל
# opt-in כמו "--export-excel" הישן לעולם לא היה מגיע להיות True דרך הכפתור,
# ורק JSON נוצר בפועל בכל הרצה מה-GUI. --no-excel הוא opt-out עבור הרצה
# ידנית מה-CLI שרוצה רק JSON (למשל סקריפט אוטומציה חיצוני).
parser.add_argument("--no-excel", action="store_true", help="מדלג על יצירת קובץ Excel - יוצר רק את ה-JSON")
parser.add_argument("--no-html", action="store_true", help="מדלג על יצירת עמוד HTML קליל לסיכום")
args, _unknown = parser.parse_known_args()

TARGET_DIR = args.target_dir
OUTPUT_PATH = args.output or DEFAULT_REPORT_JSON
WORKERS = max(1, args.workers)


def is_junk_by_name(filename):
    lower = filename.lower()
    if lower in JUNK_EXACT_NAMES:
        return True
    if lower.startswith("~$"):  # קבצי נעילה זמניים של Office
        return True
    _, ext = os.path.splitext(lower)
    return ext in JUNK_EXTENSIONS


def collect_files(target_dir):
    """מעבר ראשון - רק os.walk+stat (זול, בלי קריאת תוכן), כדי לדעת מראש כמה קבצים
    יש בסה"כ (לצורך פס התקדמות אמיתי) ולבנות את רשימת העבודה לשלב הכבד."""
    entries = []

    def on_error(exc):
        print(f"⚠️ שגיאת גישה לתיקייה: {exc}")

    for root, dirs, files in os.walk(target_dir, onerror=on_error):
        kept_dirs = []
        for d in dirs:
            if d.lower() in SKIP_DIR_NAMES:
                continue
            dir_path = os.path.join(root, d)
            if is_reparse_point(dir_path):
                skipped_reparse_points.append(dir_path)
                continue
            kept_dirs.append(d)
        dirs[:] = kept_dirs

        for filename in files:
            full_path = os.path.join(root, filename)
            try:
                size = os.path.getsize(full_path)
            except OSError as e:
                print(f"⚠️ לא ניתן לגשת ל-{full_path}: {e}")
                continue
            entries.append((full_path, filename, size))
    return entries


def quick_hash(path, size):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            h.update(f.read(QUICK_HASH_EDGE_BYTES))
            if size > QUICK_HASH_EDGE_BYTES * 2:
                f.seek(max(0, size - QUICK_HASH_EDGE_BYTES))
                h.update(f.read(QUICK_HASH_EDGE_BYTES))
        return h.hexdigest()
    except OSError:
        return None


def full_hash(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(FULL_HASH_READ_BUFFER), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def probe_media(path):
    """מריץ ffprobe ומחזיר dict עם קודק/ביטרייט/משך/רזולוציה, או None אם הקובץ פגום
    (סיומת מדיה אבל ffprobe לא הצליח לקרוא ממנו אף stream תקין)."""
    cmd = [
        FFPROBE_EXE, "-v", "error", "-show_entries",
        "format=duration,bit_rate:stream=codec_type,codec_name,width,height",
        "-of", "json", path,
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
        if result.returncode != 0 or not result.stdout.strip():
            return None
        data = json.loads(result.stdout)
        fmt = data.get("format", {})
        streams = data.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})
        if not video_stream and not audio_stream:
            return None
        return {
            "duration_seconds": float(fmt["duration"]) if fmt.get("duration") else None,
            "bitrate": int(fmt["bit_rate"]) if fmt.get("bit_rate") else None,
            "video_codec": video_stream.get("codec_name"),
            "audio_codec": audio_stream.get("codec_name"),
            "width": video_stream.get("width"),
            "height": video_stream.get("height"),
        }
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError, ValueError):
        return None


def process_entry(full_path, filename, size):
    """מעבד קובץ בודד: quick_hash תמיד (לצורך זיהוי כפילויות), ffprobe רק אם הסיומת
    מזוהה כמדיה. לא נוגע בקובץ עצמו מלבד קריאה בלבד."""
    result = {"path": full_path, "size_bytes": size}

    if size == 0:
        result["junk_reason"] = "קובץ ריק (0 בייט)"
        return result

    if is_junk_by_name(filename):
        result["junk_reason"] = "קובץ זבל מוכר (זמני/מטמון/נעילה)"
        return result

    result["quick_hash"] = quick_hash(full_path, size)

    ext = os.path.splitext(filename)[1].lower()
    if ext in MEDIA_EXTENSIONS:
        probe = probe_media(full_path)
        if probe:
            result.update(probe)
        else:
            result["junk_reason"] = "קובץ מדיה פגום (ffprobe נכשל בקריאתו)"

    return result


def find_duplicates(results, workers):
    """שלבים 1-3 שמתוארים למעלה בכותרת הקובץ. מחזיר (duplicate_groups, wasted_bytes)
    ומעדכן in-place כל רשומה שאושרה ככפילות עם full_hash."""
    by_size = defaultdict(list)
    for r in results:
        if "error" in r or r.get("size_bytes", 0) == 0:
            continue
        by_size[r["size_bytes"]].append(r)

    hash_candidates = []
    for group in by_size.values():
        if len(group) < 2:
            continue
        by_quick = defaultdict(list)
        for r in group:
            if r.get("quick_hash"):
                by_quick[r["quick_hash"]].append(r)
        for quick_group in by_quick.values():
            if len(quick_group) >= 2:
                hash_candidates.extend(quick_group)

    if not hash_candidates:
        return [], 0

    print(f"🔬 {len(hash_candidates)} קבצים חשודים בכפילות - מוודא עם hash מלא...")
    sys.stdout.flush()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(full_hash, r["path"]): r for r in hash_candidates}
        for future in as_completed(futures):
            r = futures[future]
            r["full_hash"] = future.result()

    by_full_hash = defaultdict(list)
    for r in hash_candidates:
        if r.get("full_hash"):
            by_full_hash[r["full_hash"]].append(r)

    duplicate_groups = []
    wasted_bytes = 0
    for fh, group in by_full_hash.items():
        if len(group) < 2:
            continue
        size = group[0]["size_bytes"]
        duplicate_groups.append({
            "hash": fh,
            "size_bytes": size,
            "count": len(group),
            "files": [g["path"] for g in group],
        })
        wasted_bytes += size * (len(group) - 1)

    duplicate_groups.sort(key=lambda g: g["size_bytes"] * (g["count"] - 1), reverse=True)
    return duplicate_groups, wasted_bytes


def main():
    if not os.path.exists(TARGET_DIR):
        print(f"❌ הנתיב לסריקה לא קיים: {TARGET_DIR}")
        sys.exit(1)

    print(f"🔍 סורק את {TARGET_DIR} (שלב 1/3: מיפוי קבצים)...")
    sys.stdout.flush()
    t_start = time.time()
    scan_started_at = datetime.datetime.now().isoformat()

    entries = collect_files(TARGET_DIR)
    total_files = len(entries)
    total_size = sum(e[2] for e in entries)
    print(f"📁 נמצאו {total_files:,} קבצים ({total_size / (1024**3):.1f} GB). שלב 2/3: ניתוח...")
    sys.stdout.flush()

    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(process_entry, *entry): entry for entry in entries}
        with tqdm(total=total_files, desc="מנתח קבצים", unit="קובץ", file=sys.stdout, dynamic_ncols=True) as pbar:
            for future in as_completed(futures):
                entry = futures[future]
                try:
                    results.append(future.result())
                except Exception as e:
                    results.append({"path": entry[0], "size_bytes": entry[2], "error": str(e)})
                pbar.update(1)

    print("שלב 3/3: איתור כפילויות...")
    sys.stdout.flush()
    duplicate_groups, wasted_bytes = find_duplicates(results, WORKERS)

    junk_files = [
        {"path": r["path"], "size_bytes": r.get("size_bytes", 0), "reason": r["junk_reason"]}
        for r in results if r.get("junk_reason")
    ]

    media_files = [
        {
            "path": r["path"],
            "size_bytes": r["size_bytes"],
            "video_codec": r.get("video_codec"),
            "audio_codec": r.get("audio_codec"),
            "bitrate": r.get("bitrate"),
            "duration_seconds": r.get("duration_seconds"),
            "width": r.get("width"),
            "height": r.get("height"),
            "quick_hash": r.get("quick_hash"),
            "full_hash": r.get("full_hash"),
        }
        for r in results if ("video_codec" in r or "audio_codec" in r) and not r.get("junk_reason")
    ]

    errors = [{"path": r["path"], "error": r["error"]} for r in results if "error" in r]
    scan_duration = time.time() - t_start

    report = {
        "scan_started_at": scan_started_at,
        "scan_finished_at": datetime.datetime.now().isoformat(),
        "scan_duration_seconds": round(scan_duration, 1),
        "target_directory": TARGET_DIR,
        "total_files_scanned": total_files,
        "total_size_bytes": total_size,
        "media_files_analyzed": len(media_files),
        "duplicate_groups_found": len(duplicate_groups),
        "duplicate_wasted_bytes": wasted_bytes,
        "junk_files_found": len(junk_files),
        "skipped_reparse_points_count": len(skipped_reparse_points),
        "skipped_reparse_points_sample": skipped_reparse_points[:50],
        "duplicates": duplicate_groups,
        "junk_files": junk_files,
        "media_files": media_files,
        "errors": errors,
    }

    os.makedirs(os.path.dirname(os.path.abspath(OUTPUT_PATH)), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n✅ הסריקה הושלמה תוך {scan_duration:.1f} שניות.")
    print(f"📊 {total_files:,} קבצים ({total_size/(1024**3):.1f} GB) | "
          f"{len(duplicate_groups)} קבוצות כפילויות ({wasted_bytes/(1024**3):.2f} GB לשחזור) | "
          f"{len(junk_files)} קבצי זבל | {len(media_files)} קבצי מדיה נותחו")
    if skipped_reparse_points:
        print(f"🔗 דילג על {len(skipped_reparse_points)} תיקיות Junction/Symlink (לא נכנס לתוכן - למניעת רקורסיה/כפילויות שגויות)")
    print(f"📄 הדוח נשמר ב: {OUTPUT_PATH}")

    if not args.no_excel:
        from utils.shared.report_excel import write_excel_report
        excel_path = os.path.splitext(OUTPUT_PATH)[0] + ".xlsx"
        write_excel_report(report, excel_path)
        print(f"📊 קובץ Excel נוצר בהצלחה: {excel_path}")

    if not args.no_html:
        from utils.shared.report_html import write_html_report
        html_path = os.path.splitext(OUTPUT_PATH)[0] + ".html"
        write_html_report(report, html_path)
        print(f"🌐 עמוד סיכום HTML נוצר בהצלחה: {html_path}")

    # שורת תוצאה מובנית ל-GUI (ראו RESULT_LINE_PREFIX ב-utils/shared/worker.py) - מאפשרת
    # להציג סיכום קריא בהתראה/webhook במקום רק "✅ הצליח" גולמי.
    print("RESULT: " + json.dumps({
        "files_scanned": total_files,
        "duplicate_groups": len(duplicate_groups),
        "junk_files": len(junk_files),
        "errors": len(errors),
    }, ensure_ascii=False))

    sys.stdout.flush()


if __name__ == "__main__":
    main()
