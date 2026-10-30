# Name: ⏩ טיימלאפס אוטומטי (דחיסת סרטון ארוך)
# Name (EN): ⏩ Automatic Timelapse (Long Video Compression)
# Description: דוחס סרטון ארוך (גם שעות) לסרטון קצר (60 שניות כברירת מחדל) שהכל בו רץ מהר מאוד - מייצא גרסה אופקית וגרסה אנכית.
# Description (EN): Compresses a long recording (even hours) into a short, very-fast-motion clip (60s by default) - exports both a horizontal and a vertical version.
# Safety: read-only

import argparse
import os
import sys
import json

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

from utils.shared.export_dir import output_dir  # תיקיית הייצוא (של הכלי, או הכללית), או workspace
from utils.shared.workspace_dir import TIMELAPSES  # CLIPFORGE_WORKSPACE_DIR (טסטים, שרת בדיקה) - ברירת המחדל workspace/ כמו קודם
from utils.shared.ffmpeg_locator import get_ffmpeg_exe
from utils.shared.disk_space import estimate_required_bytes_for_duration, has_enough_disk_space
from utils.media.ffmpeg_progress import run_ffmpeg_with_progress
from utils.shared.render_lock import render_lock_if_needed
from utils.media.ffprobe_cache import probe_video
from utils.media.timelapse import HORIZONTAL_SCALE_CHAIN, VERTICAL_SCALE_CHAIN, build_filter_complex, compute_speed_factor, find_video_files

FFMPEG_EXE = get_ffmpeg_exe()

parser = argparse.ArgumentParser()
parser.add_argument("--input_dir", type=str, default="")
parser.add_argument("--target-seconds", type=int, default=60, help="אורך היעד בשניות (ברירת מחדל: 60).")
parser.add_argument("--fps", type=int, default=30, help="קצב פריימים של הפלט (ברירת מחדל: 30).")
parser.add_argument("--keep-audio", action="store_true", help="שומר גם אודיו מואץ (atempo) - כבוי כברירת מחדל, כי במקדמי מהירות גבוהים זה יוצא בלתי מובן.")
args = parser.parse_args()

INPUT_DIR = args.input_dir
TARGET_SECONDS = args.target_seconds
OUTPUT_FPS = args.fps
KEEP_AUDIO = args.keep_audio

# workspace/timelapses/<כיוון> (עד 19.10.2026: <כיוון>/timelapses)
HORIZONTAL_OUTPUT_DIR = output_dir(TIMELAPSES, "horizontal")
VERTICAL_OUTPUT_DIR = output_dir(TIMELAPSES, "vertical")
OUTPUT_DIR = HORIZONTAL_OUTPUT_DIR  # ראו process_video - כל אורינטציה כותבת לתיקייה שלה בפועל
os.makedirs(HORIZONTAL_OUTPUT_DIR, exist_ok=True)
os.makedirs(VERTICAL_OUTPUT_DIR, exist_ok=True)

if not INPUT_DIR:
    print("[ERROR] לא נבחרה תיקייה. ביטול פעולה.")
    sys.stdout.flush()
    exit()


def process_video(video_path, results):
    filename = os.path.basename(video_path)
    base_name = os.path.splitext(filename)[0]

    duration = probe_video(video_path)["duration"]
    if not duration:
        print(f"[ERROR] לא הצלחתי לקרוא את אורך {filename} - מדלג.")
        results["errors"] += 1
        return

    speed_factor = compute_speed_factor(duration, TARGET_SECONDS)
    if speed_factor is None:
        print(f"[SKIP] {filename} כבר קצר מ-{TARGET_SECONDS} שניות ({duration:.0f}s) - מדלג.")
        results["skipped"] += 1
        return

    # פלט אופקי+אנכי, שני קבצים - ראו utils/shared/disk_space.py למה זה מבוסס אורך
    # יעד ולא גודל הקלט (מקור של שעות נדחס לשניות, לא הפוך).
    required_bytes = estimate_required_bytes_for_duration(TARGET_SECONDS, num_outputs=2)
    if not has_enough_disk_space(OUTPUT_DIR, required_bytes):
        print(f"[ERROR] שטח פנוי לא מספיק ב-{OUTPUT_DIR} עבור {filename} - מדלג (במקום להיכשל באמצע רינדור).")
        results["errors"] += 1
        return

    print(f"[INFO] {filename}: {duration:.0f}s -> {TARGET_SECONDS}s (מהירות פי {speed_factor:.1f})")
    sys.stdout.flush()
    setpts_expr = f"setpts=PTS/{speed_factor:.6f}"
    total_frames = TARGET_SECONDS * OUTPUT_FPS

    for label, scale_chain, label_output_dir in (
        ("horizontal", HORIZONTAL_SCALE_CHAIN, HORIZONTAL_OUTPUT_DIR),
        ("vertical", VERTICAL_SCALE_CHAIN, VERTICAL_OUTPUT_DIR),
    ):
        output_path = os.path.join(label_output_dir, f"{base_name}_{label}.mp4")
        filter_complex, maps = build_filter_complex(setpts_expr, scale_chain, OUTPUT_FPS, speed_factor, KEEP_AUDIO)

        cmd = [FFMPEG_EXE, "-y", "-i", video_path, "-filter_complex", filter_complex, *maps]
        if not KEEP_AUDIO:
            cmd += ["-an"]
        else:
            cmd += ["-c:a", "aac", "-b:a", "128k"]
        cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "20", output_path]

        ok = run_ffmpeg_with_progress(cmd, total_frames, f"{filename} ({label})")
        if ok:
            print(f"[APPROVED] נוצר: {os.path.basename(output_path)}")
            results["files_created"] += 1
        else:
            print(f"[ERROR] רינדור {label} עבור {filename} נכשל.")
            results["errors"] += 1


def main():
    video_files = find_video_files(INPUT_DIR)
    if not video_files:
        print(f"[ERROR] לא נמצאו קובצי וידאו בתיקייה: {INPUT_DIR}")
        sys.stdout.flush()
        return

    print(f"[INFO] נמצאו {len(video_files)} סרטונים לעיבוד.")
    sys.stdout.flush()

    def _log_waiting(_seconds_waited):
        print("⏳ ממתין לסיום רינדור אחר שרץ כרגע (GUI/דפדפן/בוט)...")
        sys.stdout.flush()

    results = {"files_created": 0, "skipped": 0, "errors": 0}
    # render_lock_if_needed - זהה ל-video_editor.py: מגן על עצמו גם כשמופעל
    # ישירות (טרמינל), לא רק דרך worker.py/remote_execution.py.
    with render_lock_if_needed(on_wait=_log_waiting):
        for idx, video_path in enumerate(video_files, start=1):
            process_video(video_path, results)
            print(f"PROGRESS:{int(idx / len(video_files) * 100)}")
            sys.stdout.flush()

    print("\n[SUCCESS] העיבוד הסתיים.")
    print("RESULT: " + json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
