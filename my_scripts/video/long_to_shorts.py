# Name: ✂️ הקלטה ארוכה לכמה שורטס
# Name (EN): ✂️ Long Recording to Several Shorts
# Description: מוצא את הרגעים החזקים בהקלטה ארוכה או VOD (לפי שיאי השמע) וחותך מכל אחד Short אנכי - עם Facecam למעלה כשיש מצלמה בקובץ, וזום קצר על השיא.
# Description (EN): Finds the strongest moments in a long recording or VOD (by audio peaks) and cuts a vertical Short from each - with the facecam on top when the file has a camera track, and a quick zoom on the peak.
# Safety: read-only
#
# 16.11.2026 (ClipForge 2.0). הבחירה: utils/media/moment_finder.py. הפקודה: utils/media/shorts_layout.py. הקבצים המקוריים לא משתנים;
# הפלט ב-<תיקיית הייצוא / workspace>/long_to_shorts/vertical/<שם>_short_<n>.mp4.
import argparse
import os
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from utils.media import moment_finder, shorts_layout  # noqa: E402
from utils.media.ffprobe_cache import probe_video  # noqa: E402
from utils.media.timelapse import find_video_files  # noqa: E402
from utils.shared.export_dir import output_dir  # noqa: E402
from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe  # noqa: E402
from utils.shared.render_lock import render_lock_if_needed  # noqa: E402
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS  # noqa: E402
from utils.video import highlight_detect  # noqa: E402

TOOL = "long_to_shorts"


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_dir", type=str, default="")
    parser.add_argument("--count", type=int, default=5, help="כמה שורטס מכל הקלטה (ברירת מחדל 5)")
    parser.add_argument("--length", type=float, default=30.0, help="אורך כל Short בשניות (ברירת מחדל 30)")
    parser.add_argument("--layout", choices=["auto", "center", "facecam"], default="auto",
                        help="auto: Facecam למעלה כשיש מצלמה בקובץ, אחרת מרכז")
    parser.add_argument("--no-punch-in", action="store_true", help="בלי זום על השיא")
    parser.add_argument("--mic-track", type=int, default=None, help="ערוץ מיקרופון לערבוב מעל המשחק (הקלטה של ClipForge / OBS)")
    parser.add_argument("--threshold", type=float, default=highlight_detect.DEFAULT_THRESHOLD_OFFSET_DB,
                        help="כמה dB מעל הממוצע נחשב שיא (נמוך = יותר רגעים)")
    parser.add_argument("--dry-run", action="store_true", help="רק מציג את הרגעים, בלי לרנדר")
    args, _unknown = parser.parse_known_args(argv)
    return args


def video_streams(path, ffprobe_exe):
    try:
        out = subprocess.run([ffprobe_exe, "-v", "error", "-select_streams", "v", "-show_entries", "stream=index", "-of", "csv=p=0", path],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
                             creationflags=NO_WINDOW_FLAGS).stdout
        return len([line for line in out.split() if line.strip()])
    except (OSError, subprocess.SubprocessError):
        return 1


def process_file(path, args, ffmpeg_exe, ffprobe_exe, dest):
    info = probe_video(path) or {}
    duration = float(info.get("duration") or 0)
    samples = highlight_detect.decode_mono_samples(path, ffmpeg_exe)
    if samples is None or duration <= 0:
        print(f"⚠️ {os.path.basename(path)}: אין שמע לניתוח - מדלג")
        return 0
    levels, average = highlight_detect.chunk_levels_dbfs(samples, 8000)
    moments = moment_finder.find_moments(levels, average, duration, count=args.count, length=args.length,
                                         threshold_offset_db=args.threshold)
    if not moments:
        print(f"ℹ️ {os.path.basename(path)}: לא נמצאו רגעים חזקים (נסה --threshold נמוך יותר)")
        return 0
    has_cam = video_streams(path, ffprobe_exe) > 1
    layout = ("facecam" if has_cam else "center") if args.layout == "auto" else args.layout
    stem = os.path.splitext(os.path.basename(path))[0]
    made = 0
    for n, moment in enumerate(moments, start=1):
        out = os.path.join(dest, f"{stem}_short_{n}.mp4")
        print(f"🎬 {stem} #{n}: {moment.start:.0f}-{moment.end:.0f} שניות (שיא ב-{moment.peak:.0f}, +{moment.score:.0f}dB) -> {os.path.basename(out)}")
        if args.dry_run:
            continue
        cmd = shorts_layout.build_command(ffmpeg_exe, path, moment.start, moment.end - moment.start, out, layout=layout,
                                          has_cam=has_cam, punch_at=None if args.no_punch_in else moment.peak_in_clip,
                                          mic_track=args.mic_track)
        result = subprocess.run(cmd, capture_output=True, timeout=1800, creationflags=NO_WINDOW_FLAGS)
        if result.returncode != 0:
            print(f"❌ {os.path.basename(out)}: " + result.stderr.decode("utf-8", errors="replace")[-400:])
            continue
        made += 1
    return made


def main(argv=None):
    args = parse_args(argv)
    folder = args.input_dir
    if not folder or not os.path.isdir(folder):
        print("❌ בחר תיקייה עם הקלטות.")
        return 1
    files = find_video_files(folder)
    if not files:
        print("ℹ️ אין קובצי וידאו בתיקייה.")
        return 0
    dest = output_dir(TOOL, "vertical")
    os.makedirs(dest, exist_ok=True)
    ffmpeg_exe, ffprobe_exe = get_ffmpeg_exe(), get_ffprobe_exe()
    total = 0
    with render_lock_if_needed():
        for path in files:
            total += process_file(path, args, ffmpeg_exe, ffprobe_exe, dest)
    print(f"✅ נוצרו {total} שורטס ב-{dest}" if not args.dry_run else "✅ בדיקה בלבד - לא רונדר כלום")
    return 0


if __name__ == "__main__":
    sys.exit(main())
