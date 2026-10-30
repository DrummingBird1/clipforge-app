# Name: 🎞️ הרכבת Highlight Reel
# Name (EN): 🎞️ Highlight Reel Maker
# Description: מאחד כמה קליפים (למשל מתיקיית הקליפים שאושרו) לסרטון סיכום אחד - כל קליפ מתועלה לרזולוציה/פריימרייט אחידים לפני החיבור, כדי שזה יעבוד גם עם קליפים ממשחקים/הקלטות שונות.
# Description (EN): Merges several clips (e.g. from the approved-clips folder) into one summary video - each clip is normalized to a shared resolution/framerate before concatenation, so it works even with clips from different games/recordings.
# Safety: read-only

import argparse
import glob
import json
import os
import sys

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
from utils.shared.workspace_dir import HIGHLIGHT_REELS  # CLIPFORGE_WORKSPACE_DIR (טסטים, שרת בדיקה) - ברירת המחדל workspace/ כמו קודם
from utils.shared.ffmpeg_locator import get_ffmpeg_exe
from utils.media.ffmpeg_progress import run_ffmpeg_with_progress
from utils.media.ffprobe_cache import probe_video
from utils.media.highlight_reel import build_concat_filter_complex
from utils.media.timelapse import HORIZONTAL_SCALE_CHAIN, VERTICAL_SCALE_CHAIN, VIDEO_EXTENSIONS

FFMPEG_EXE = get_ffmpeg_exe()

parser = argparse.ArgumentParser()
parser.add_argument("--input_dir", type=str, default="")
parser.add_argument("--max-clips", type=int, default=20, help="מספר קליפים מקסימלי לכלול (ברירת מחדל: 20) - הכי חדשים ראשונים.")
parser.add_argument("--fps", type=int, default=30, help="קצב פריימים של הפלט (ברירת מחדל: 30).")
parser.add_argument("--vertical", action="store_true", help="פלט אנכי (1080x1920) במקום אופקי (1920x1080).")
args = parser.parse_args()

INPUT_DIR = args.input_dir
MAX_CLIPS = args.max_clips
OUTPUT_FPS = args.fps
SCALE_CHAIN = VERTICAL_SCALE_CHAIN if args.vertical else HORIZONTAL_SCALE_CHAIN

OUTPUT_DIR = output_dir(HIGHLIGHT_REELS, "vertical" if args.vertical else "horizontal")  # עד 19.10.2026: <כיוון>/highlight_reels
os.makedirs(OUTPUT_DIR, exist_ok=True)

if not INPUT_DIR:
    print("[ERROR] לא נבחרה תיקייה. ביטול פעולה.")
    sys.stdout.flush()
    exit()


def find_clips(input_dir, max_clips):
    """הכי חדשים ראשונים (mtime יורד) - קליפים "אושרו לאחרונה" סבירים יותר
    להיות מה שרוצים ב-highlight reel מאשר קליפים ישנים שנשארו בתיקייה."""
    files = []
    for ext in VIDEO_EXTENSIONS:
        files.extend(glob.glob(os.path.join(input_dir, f"*{ext}")))
    files.sort(key=os.path.getmtime, reverse=True)
    return files[:max_clips]


def main():
    clip_paths = find_clips(INPUT_DIR, MAX_CLIPS)
    if len(clip_paths) < 2:
        print(f"[ERROR] נדרשים לפחות 2 קליפים ליצירת highlight reel - נמצאו {len(clip_paths)} ב-{INPUT_DIR}.")
        sys.stdout.flush()
        return

    print(f"[INFO] נמצאו {len(clip_paths)} קליפים - מאחד לסרטון אחד.")
    sys.stdout.flush()

    durations = []
    has_audio_flags = []
    for path in clip_paths:
        # probe_video (item 20) - קריאת ffprobe אחת (משך+אודיו יחד) במקום שתיים
        # נפרדות לכל קליפ, וממוטמנת (data/ffprobe_cache.json) אם קליפ כלשהו
        # כבר נבדק בריצה אחרת (למשל שלב קודם בפייפליין, item 15).
        info = probe_video(path)
        if info["duration"] is None:
            print(f"[ERROR] לא הצלחתי לקרוא את אורך {os.path.basename(path)} - מדלג על כל התהליך (קליפ פגום עלול לשבש את כל החיבור).")
            sys.stdout.flush()
            return
        durations.append(info["duration"])
        has_audio_flags.append(info["has_audio"])

    filter_complex, lavfi_indices = build_concat_filter_complex(len(clip_paths), has_audio_flags, SCALE_CHAIN, OUTPUT_FPS)

    cmd = [FFMPEG_EXE, "-y"]
    for path in clip_paths:
        cmd += ["-i", path]
    for idx in lavfi_indices:
        cmd += ["-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100:duration={durations[idx]:.3f}"]

    orientation_suffix = "vertical" if args.vertical else "horizontal"
    output_path = os.path.join(OUTPUT_DIR, f"highlight_reel_{len(clip_paths)}clips_{orientation_suffix}.mp4")
    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        output_path,
    ]

    total_frames = int(sum(durations) * OUTPUT_FPS)
    ok = run_ffmpeg_with_progress(cmd, total_frames, "highlight reel")

    result = {"clips_merged": len(clip_paths), "output": None}
    if ok:
        print(f"\n[SUCCESS] נוצר: {os.path.basename(output_path)}")
        result["output"] = os.path.basename(output_path)
    else:
        print("\n[ERROR] יצירת ה-highlight reel נכשלה.")
    print("RESULT: " + json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
