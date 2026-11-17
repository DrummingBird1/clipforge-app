# Name: ✂️ הקלטה ארוכה לכמה שורטס
# Name (EN): ✂️ Long Recording to Several Shorts
# Description: מוצא את הרגעים החזקים בהקלטה ארוכה או VOD (לפי שיאי השמע) וחותך מכל אחד Short אנכי - עם Facecam למעלה שעוקב אחרי הפנים כשיש מצלמה בקובץ, וזום והילוך איטי על השיא.
# Description (EN): Finds the strongest moments in a long recording or VOD (by audio peaks) and cuts a vertical Short from each - with a facecam on top that follows the face when the file has a camera track, and a zoom and slow motion on the peak.
# Safety: read-only
#
# 16.11.2026 (ClipForge 2.0). הבחירה: utils/media/moment_finder.py. הפקודה: utils/media/shorts_layout.py. הקבצים המקוריים לא משתנים;
# 17.11.2026 (2.0.1), מהבדיקה המעמיקה: המיקרופון של הקלטת ClipForge מעורבב לבד (--mic-track auto); Short שכבר קיים לא נדרס
# (שם חדש עם _2); רינדור שנכשל לא משאיר קובץ שבור; כשכל הרינדורים נכשלו הסקריפט יוצא עם שגיאה; תמונת עטיפה לא נחשבת מצלמה.
# 17.11.2026 (2.0.1): הילוך איטי על השיא (--no-slowmo מבטל) ומסגרת Facecam שעוקבת אחרי הפנים (utils/media/face_track.py; --no-face-track מבטל).
# הפלט ב-<תיקיית הייצוא / workspace>/long_to_shorts/vertical/<שם>_short_<n>.mp4.
import argparse
import json
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

from utils.media import audio_tracks, face_track, moment_finder, shorts_layout  # noqa: E402
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
    parser.add_argument("--no-slowmo", action="store_true", help="בלי הילוך איטי על השיא")
    parser.add_argument("--no-face-track", action="store_true", help="מסגרת ה-Facecam חתוכה למרכז ולא עוקבת אחרי הפנים")
    parser.add_argument("--mic-track", type=str, default="auto",
                        help="ערוץ מיקרופון לערבוב מעל המשחק: auto (ערוץ שכותרתו mic, כמו בהקלטה של ClipForge), none, או מספר ערוץ")
    parser.add_argument("--threshold", type=float, default=highlight_detect.DEFAULT_THRESHOLD_OFFSET_DB,
                        help="כמה dB מעל הממוצע נחשב שיא (נמוך = יותר רגעים)")
    parser.add_argument("--dry-run", action="store_true", help="רק מציג את הרגעים, בלי לרנדר")
    args, _unknown = parser.parse_known_args(argv)
    return args


def video_streams(path, ffprobe_exe):
    """(רוחב, גובה) של כל stream וידאו בקובץ, לפי הסדר - בלי תמונת עטיפה (attached_pic). כשל = stream אחד בגודל לא ידוע."""
    try:
        out = subprocess.run([ffprobe_exe, "-v", "error", "-select_streams", "v", "-show_entries",
                              "stream=width,height:stream_disposition=attached_pic", "-of", "json", path],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
                             creationflags=NO_WINDOW_FLAGS).stdout
        sizes = [(int(s.get("width") or 0), int(s.get("height") or 0)) for s in json.loads(out or "{}").get("streams") or []
                 if not (s.get("disposition") or {}).get("attached_pic")]
        return sizes or [(0, 0)]
    except (OSError, ValueError, subprocess.SubprocessError):
        return [(0, 0)]


def pick_mic_track(choice, titles):
    """ערוץ המיקרופון לקובץ הזה לפי --mic-track, או None (בלי ערבוב)."""
    choice = str(choice or "auto").strip().lower()
    if choice == "auto":
        return audio_tracks.find_mic_track(titles)
    if choice.isdigit():
        return audio_tracks.usable_mic_track(titles, int(choice))
    return None


def free_name(dest, name):
    """name אם הוא פנוי ב-dest, אחרת name_2, name_3... - ריצה חוזרת לא דורסת Short שכבר נוצר."""
    stem, ext = os.path.splitext(name)
    candidate, n = name, 2
    while os.path.exists(os.path.join(dest, candidate)):
        candidate, n = f"{stem}_{n}{ext}", n + 1
    return os.path.join(dest, candidate)


def source_fps(info):
    """קצב הפריימים מ-probe_video ("60/1", "30000/1001") כמספר, או None."""
    try:
        top, _, bottom = str(info.get("fps") or "").partition("/")
        value = float(top) / float(bottom or 1)
        return value if 1 <= value <= 240 else None
    except (ValueError, ZeroDivisionError):
        return None


def process_file(path, args, ffmpeg_exe, ffprobe_exe, dest):
    info = probe_video(path) or {}
    duration = float(info.get("duration") or 0)
    samples = highlight_detect.decode_mono_samples(path, ffmpeg_exe)
    if samples is None or duration <= 0:
        print(f"⚠️ {os.path.basename(path)}: אין שמע לניתוח - מדלג")
        return 0, 0
    levels, average = highlight_detect.chunk_levels_dbfs(samples, 8000)
    moments = moment_finder.find_moments(levels, average, duration, count=args.count, length=args.length,
                                         threshold_offset_db=args.threshold)
    if not moments:
        print(f"ℹ️ {os.path.basename(path)}: לא נמצאו רגעים חזקים (השמע אחיד מדי - אין שיאים שבולטים מעליו)")
        return 0, 0
    streams = video_streams(path, ffprobe_exe)
    has_cam = len(streams) > 1
    layout = ("facecam" if has_cam else "center") if args.layout == "auto" else args.layout
    stem = os.path.splitext(os.path.basename(path))[0]
    mic_track = pick_mic_track(args.mic_track, audio_tracks.audio_titles(path, ffprobe_exe))
    if mic_track is not None:
        print(f"   🎙️ המיקרופון (ערוץ {mic_track + 1}) מעורבב מעל המשחק")
    elif str(args.mic_track).isdigit():
        print(f"   ⚠️ אין בקובץ ערוץ שמע {int(args.mic_track) + 1} - ממשיך בלי ערבוב מיקרופון")
    made = failed = 0
    for n, moment in enumerate(moments, start=1):
        out = free_name(dest, f"{stem}_short_{n}.mp4")
        print(f"🎬 {stem} #{n}: {moment.start:.0f}-{moment.end:.0f} שניות (שיא ב-{moment.peak:.0f}, +{moment.score:.0f}dB) -> {os.path.basename(out)}")
        if args.dry_run:
            continue
        length = moment.end - moment.start
        cam_track = None
        if layout == "facecam" and has_cam and not args.no_face_track:
            cam_track = face_track.track(path, moment.start, length, ffmpeg_exe, *streams[1])
            print("   👤 המסגרת עוקבת אחרי הפנים" if cam_track else "   👤 לא זוהו פנים במצלמה - חיתוך למרכז")
        cmd = shorts_layout.build_command(ffmpeg_exe, path, moment.start, length, out, layout=layout,
                                          has_cam=has_cam, punch_at=None if args.no_punch_in else moment.peak_in_clip,
                                          mic_track=mic_track, cam_track=cam_track,
                                          slowmo_at=None if args.no_slowmo else moment.peak_in_clip, fps=source_fps(info))
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=1800, creationflags=NO_WINDOW_FLAGS)
            error = result.stderr.decode("utf-8", errors="replace")[-400:] if result.returncode != 0 else ""
        except subprocess.TimeoutExpired:
            error = "הרינדור לא הסתיים תוך 30 דקות"
        if error:
            print(f"❌ {os.path.basename(out)}: {error}")
            failed += 1
            try:
                os.remove(out)  # safe: this run's own failed output (a new name that did not exist before), not user input
            except OSError:
                pass
            continue
        made += 1
    return made, failed


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
    total = failed = 0
    with render_lock_if_needed():
        for path in files:
            made, bad = process_file(path, args, ffmpeg_exe, ffprobe_exe, dest)
            total, failed = total + made, failed + bad
    if args.dry_run:
        print("✅ בדיקה בלבד - לא רונדר כלום")
        return 0
    if failed and not total:
        print(f"❌ כל {failed} הרינדורים נכשלו - לא נוצר אף Short")
        return 1
    print(f"✅ נוצרו {total} שורטס ב-{dest}" + (f" ({failed} נכשלו)" if failed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
