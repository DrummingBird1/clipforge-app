# Name: 🔁 גלאי הדז'ה-וו
# Name (EN): 🔁 Déjà Vu Detector
# Description: סורק כל סרטון בתיקייה בנפרד ומאתר סצנות שחוזרות בתוך אותו סרטון (מסך טעינה שחוזר, קטע שהוקלט פעמיים בטעות) - שונה מ-disk_scanner.py, שמאתר קבצים כפולים שלמים, לא סצנות בתוך קובץ. גם מאתר זוגות קבצים שכנראה אותו קליפ בעצם (למשל highlight שיוצא/יובא פעמיים בטעות תחת שני שמות), על בסיס אותם פריימים שכבר נדגמו. קורא-בלבד, כותב רק דוח JSON.
# Description (EN): Scans each video in a folder separately and finds scenes that repeat within that same video (a recurring loading screen, a segment accidentally recorded twice) - unlike disk_scanner.py, which finds whole duplicate files, not repeated scenes within one. Also finds pairs of files that likely are the same clip (e.g. a highlight exported/imported twice under different names), reusing the same already-sampled frames. Read-only, writes only a JSON report.
# Concurrency: light
# Safety: read-only

import argparse
import json
import os
import subprocess
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure") and sys.stderr.encoding != "utf-8":
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import cv2

from utils.shared.disk_report_paths import DUPLICATE_SCENES_REPORT_JSON
from utils.media.duplicate_scene_detector import compute_average_hash_from_gray, find_cross_file_duplicate_pairs, find_duplicate_scene_pairs
from utils.shared.ffmpeg_locator import get_ffmpeg_exe
from utils.media.ffprobe_cache import probe_video
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
from utils.media.timelapse import VIDEO_EXTENSIONS

FFMPEG_EXE = get_ffmpeg_exe()

parser = argparse.ArgumentParser()
parser.add_argument("--input_dir", type=str, default="")
parser.add_argument("--interval-seconds", type=float, default=3.0, help="כל כמה שניות לדגום פריים (ברירת מחדל: 3.0) - דגימה צפופה יותר תופסת כפילויות קצרות אבל לוקחת יותר זמן.")
parser.add_argument("--hash-threshold", type=int, default=8, help="מרחק Hamming מקסימלי (מתוך 64 ביט) כדי להיחשב 'כמעט זהה' (ברירת מחדל: 8, כ-12.5%%).")
parser.add_argument("--min-gap-seconds", type=float, default=5.0, help="מרחק זמן מינימלי בין שני פריימים כדי להיחשב 'סצנה שחוזרת' ולא רק רגע סטטי סמוך (ברירת מחדל: 5.0).")
parser.add_argument("--output", type=str, default="", help="נתיב לקובץ הדוח (ברירת מחדל: workspace/reports/disk/duplicate_scenes_report.json)")
args = parser.parse_args()

INPUT_DIR = args.input_dir
INTERVAL_SECONDS = args.interval_seconds
HASH_THRESHOLD = args.hash_threshold
MIN_GAP_SECONDS = args.min_gap_seconds
OUTPUT_PATH = args.output or DUPLICATE_SCENES_REPORT_JSON

if not INPUT_DIR:
    print("[ERROR] לא נבחרה תיקייה. ביטול פעולה.")
    sys.stdout.flush()
    exit()


def _format_timestamp(seconds):
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"


def _extract_frame_hash(video_path, timestamp, tmp_dir):
    frame_path = os.path.join(tmp_dir, "frame.jpg")
    cmd = [FFMPEG_EXE, "-y", "-ss", str(timestamp), "-i", video_path, "-vframes", "1", "-q:v", "4", frame_path]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, creationflags=NO_WINDOW_FLAGS)
    except Exception:
        return None
    if not os.path.exists(frame_path):
        return None

    img = cv2.imread(frame_path)
    os.remove(frame_path)  # safe: temp frame this function extracted itself into tmp_dir, not user input
    if img is None:
        return None

    small = cv2.resize(img, (8, 8), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    return compute_average_hash_from_gray(gray.flatten().tolist())


def analyze_video(video_path):
    duration = probe_video(video_path)["duration"]
    if not duration or duration < MIN_GAP_SECONDS * 2:
        return {"error": "הסרטון קצר מדי לניתוח משמעותי"} if duration else {"error": "לא הצלחתי לקרוא את אורך הסרטון"}

    timestamps = []
    hashes = []
    with tempfile.TemporaryDirectory() as tmp_dir:
        t = 0.0
        while t < duration:
            frame_hash = _extract_frame_hash(video_path, t, tmp_dir)
            if frame_hash is not None:
                timestamps.append(t)
                hashes.append(frame_hash)
            t += INTERVAL_SECONDS

    pairs = find_duplicate_scene_pairs(timestamps, hashes, HASH_THRESHOLD, MIN_GAP_SECONDS)
    return {
        "frames_sampled": len(timestamps),
        "duplicate_pairs": [
            {"first": _format_timestamp(t1), "second": _format_timestamp(t2), "distance": dist}
            for t1, t2, dist in pairs
        ],
        # hashes (לא נכתב ל-report.json הסופי - ראו main(), נפרד מ"pairs" למעלה) -
        # נשמר כאן כדי ש-main() יוכל להשתמש בהם ל-cross-file duplicate detection
        # בלי לחלץ את אותם פריימים פעם נוספת מכל קובץ.
        "_hashes": hashes,
    }


def find_videos(input_dir):
    import glob
    files = []
    for ext in VIDEO_EXTENSIONS:
        files.extend(glob.glob(os.path.join(input_dir, f"*{ext}")))
    return sorted(files)


def main():
    video_files = find_videos(INPUT_DIR)
    if not video_files:
        print(f"[ERROR] לא נמצאו קובצי וידאו בתיקייה: {INPUT_DIR}")
        sys.stdout.flush()
        return

    print(f"[INFO] נמצאו {len(video_files)} סרטונים לניתוח.")
    sys.stdout.flush()

    report = {}
    total_pairs_found = 0
    for idx, video_path in enumerate(video_files, start=1):
        filename = os.path.basename(video_path)
        result = analyze_video(video_path)
        report[filename] = result

        if "error" in result:
            print(f"[SKIP] {filename}: {result['error']}")
        else:
            pair_count = len(result["duplicate_pairs"])
            total_pairs_found += pair_count
            if pair_count:
                print(f"[FOUND] {filename}: {pair_count} סצנות כפולות אפשריות (מתוך {result['frames_sampled']} פריימים שנדגמו).")
                for pair in result["duplicate_pairs"][:5]:
                    print(f"        {pair['first']} <-> {pair['second']} (מרחק {pair['distance']}/64)")
            else:
                print(f"[OK] {filename}: לא נמצאו סצנות כפולות (מתוך {result['frames_sampled']} פריימים שנדגמו).")
        sys.stdout.flush()
        print(f"PROGRESS:{int(idx / len(video_files) * 100)}")
        sys.stdout.flush()

    # cross-file duplicate detection (item) - קבצים נפרדים שכנראה אותו קליפ
    # בעצם (למשל highlight שיוצא/יובא פעמיים בטעות תחת שני שמות) - שונה
    # מ-duplicate_pairs למעלה, שמחפש סצנות חוזרות *בתוך* קובץ בודד. משתמש
    # ב-hashes שכבר נדגמו למעלה - בלי לחלץ שוב אף פריים מאף קובץ.
    file_hashes = {filename: result["_hashes"] for filename, result in report.items() if "_hashes" in result}
    cross_file_pairs = find_cross_file_duplicate_pairs(file_hashes, HASH_THRESHOLD)
    if cross_file_pairs:
        print(f"\n[FOUND] {len(cross_file_pairs)} זוגות קבצים שנראים כמו אותו קליפ:")
        for name_a, name_b, similarity in cross_file_pairs:
            print(f"        {name_a} <-> {name_b} (דמיון {similarity:.0%})")
    else:
        print("\n[OK] לא נמצאו קבצים שנראים כמו אותו קליפ.")
    sys.stdout.flush()

    for result in report.values():
        result.pop("_hashes", None)  # פנימי בלבד - לא רלוונטי לדוח שנכתב לדיסק
    report["_cross_file_duplicates"] = [
        {"file_a": name_a, "file_b": name_b, "similarity": similarity} for name_a, name_b, similarity in cross_file_pairs
    ]

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n[SUCCESS] הניתוח הסתיים. דוח מלא ב-{OUTPUT_PATH}")
    print("RESULT: " + json.dumps({
        "videos_analyzed": len(video_files), "duplicate_pairs_found": total_pairs_found,
        "cross_file_duplicates_found": len(cross_file_pairs),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
