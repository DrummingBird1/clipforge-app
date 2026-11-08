# Name: 🛠️ עורך-העל (Watermark / אנכי / Timelapse / קידוד)
# Name (EN): 🛠️ Video Swiss Army Knife (Watermark / Vertical / Timelapse / Codec)
# Description: סקריפט עריכה כללי לפעולות מהירות: הוספת watermark/לוגו, המרה לפורמט אנכי (טיקטוק/שורטס), דחיסת אורך (timelapse) ובחירת קידוד יצוא (H.264/HEVC/AV1). עובר רקורסיבית תיקיה-תיקיה אם INPUT_DIR מכיל תת-תיקיות (כל תת-תיקייה מקבלת תיקיית פלט מקבילה משלה), אז אפשר להצביע גם על תיקיית-על עם הרבה תיקיות סרטונים בפנים.
# Description (EN): General-purpose quick-edit script: add a watermark/logo, convert to vertical (TikTok/Shorts) format, compress duration (timelapse), and choose the export codec (H.264/HEVC/AV1). Recurses folder-by-folder if INPUT_DIR contains subfolders (each gets its own mirrored output folder), so you can point it at a parent folder full of video subfolders too.
# Concurrency: heavy
# Safety: read-only

import atexit
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

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

from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# תיקיית הפלט - אותו משתנה סביבה כמו web_app.WORKSPACE_DIR ו-dataviz_maker (הרצות ניסיון בלי לגעת ב-workspace/ האמיתית).
# בלעדיו התוצרים וה-run manifests נכתבו ל-workspace/ של הפרויקט, והדפדפן חיפש אותם בתיקייה החלופית (manifest -> 404)
WORKSPACE_ROOT = os.environ.get("CLIPFORGE_WORKSPACE_DIR") or os.path.join(BASE_DIR, "workspace")
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from utils.video.contact_sheet import generate_contact_sheet
from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
from utils.video.color_audio import (build_audio_fx_chain, build_color_grade_filter)
from utils.shared.disk_space import estimate_required_bytes, has_enough_disk_space
from utils.media.ffmpeg_progress import FfmpegCancelled, run_ffmpeg_with_progress, run_ffmpeg_with_progress_and_nvenc_retry
from utils.video.run_control import RunControl, next_task_index, run_tasks
from utils.shared.workspace_dir import STUDIO
from utils.shared.export_dir import output_dir as export_output_dir  # תיקיית הייצוא (של הסטודיו, או הכללית), או workspace
from utils.media.ffprobe_cache import probe_video
from utils.media.nvenc_probe import DEFAULT_MAX_TO_TRY as NVENC_PROBE_MAX_TO_TRY
from utils.media.nvenc_probe import probe_max_concurrent_nvenc_sessions
from utils.shared.render_lock import render_lock_if_needed
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
from utils.media.timelapse import compute_speed_factor, find_video_files_by_folder
from utils.video.video_editor import BATCH_OVERRIDE_ALLOWED_FIELDS as SHARED_BATCH_OVERRIDE_ALLOWED_FIELDS
from utils.video.video_editor import (
    EFFORT_NVENC_PRESET,
    loudnorm_output_lufs,
    loudnorm_target_lufs,
    build_concat_transitions_filter_complex,
    build_edit_filter_complex,
    compute_removal_region,
    compute_render_signature,
    compute_silence_trim_bounds,
    compute_target_bitrate_kbps,
    DENOISE_LEVELS,
    SHARPEN_LEVELS,
    apply_pad_color,
    apply_resolution_preset,
    apply_scale_algorithm,
    build_eq_filter,
    build_fit_scale_chain,
    build_hybrid_gpu_prefix,
    build_orientation_filters,
    parse_cuda_filters,
    build_tonemap_filter,
    compute_custom_removal_region,
    compute_watermark_geometry,
    get_codec_args,
    get_hdr_output_args,
    get_two_pass_codec_args,
    get_vidstabdetect_filter,
    is_hdr_source,
    is_high_bit_depth,
    parse_fps_value,
    parse_region_fractions,
    parse_silence_intervals,
    resolve_auto_effort,
    orientation_for_dimensions,
    resolve_aspect_dimensions,
    resolve_effective_output_dimensions,
    resolve_effort_thread_count,
    resolve_output_dimensions,
    resolve_output_filename,
    resolve_output_fps,
    resolve_scale_chain,
    resolve_sig_path,
    resolve_trim_bounds,
    should_skip_scale,
    validate_output_template,
)
from utils.video.video_editor_report import write_csv_report, write_xlsx_report
from utils.video import video_editor_post as post_steps
from utils.video.video_editor_layers import (
    build_broll_audio_sources, build_ken_burns_filter, build_video_layer_input_args, build_vignette_filter,
    fill_filename_layers, sanitize_layers, video_layer_end, write_layer_text_files,
)
from utils.video.video_editor_counter import get_next_number, save_number
from utils.shared.hardware import get_gpu_stats, get_system_stats
from utils.shared.notifications import send_toast_notification, send_webhook_notification
from utils.shared.state import state

from utils.video.video_editor_cli import build_parser
from utils.video.video_editor_settings import VideoEditorSettings
from types import SimpleNamespace

FFMPEG_EXE = get_ffmpeg_exe()
FFPROBE_EXE = get_ffprobe_exe()

parser = build_parser()
args = parser.parse_args()
# גל 37: כל הדגלים של הריצה באובייקט אחד קבוע (utils/video/video_editor_settings.py). גל 48: process_video קורא את
# הערכים הנגזרים מהם (הגלובלים שלמטה) מאובייקט RenderConfig - ראו RENDER_CONFIG ליד process_video.
SETTINGS = VideoEditorSettings.from_args(args)

INPUT_DIR = args.input_dir
# item: תור-אצווה ניתן-לעריכה - JSON לא-תקין/לא-רשימה מתעלם בשקט (נופל
# לברירת המחדל - כל הקבצים) במקום להפיל את כל הריצה על קלט לא-תקין ב-flag
# שהוא בעצם "נחמד-להיות", לא קריטי.
ONLY_FILES = None
if args.only_files:
    try:
        parsed_only_files = json.loads(args.only_files)
        if isinstance(parsed_only_files, list) and all(isinstance(f, str) for f in parsed_only_files):
            ONLY_FILES = parsed_only_files
        else:
            print("[WARNING] --only-files חייב להיות מערך JSON של מחרוזות - מתעלם, מעבד את כל הקבצים.")
            sys.stdout.flush()
    except (ValueError, TypeError):
        print("[WARNING] --only-files אינו JSON תקין - מתעלם, מעבד את כל הקבצים.")
        sys.stdout.flush()

# item: ממשק batch לדריסת דגלים פר-קובץ - נטען פעם אחת כאן (לא בכל איטרציה
# בלולאה), קובץ חסר/פגום נופל בשקט לברירת המחדל (שום דריסה) באותו עיקרון
# בדיוק כמו --only-files. מוגבל בכוונה לשדות watermark/trim (הדוגמה
# המפורשת מהבקשה) - לא כל ~50 השדות האפשריים, כדי לא להפוך תכונה-קטנה
# למנגנון-דריסה גנרי-לגמרי עם משטח-סיכון גדול הרבה יותר.
BATCH_OVERRIDE_ALLOWED_FIELDS = set(SHARED_BATCH_OVERRIDE_ALLOWED_FIELDS)
BATCH_OVERRIDES: dict = {}
if args.batch_overrides:
    try:
        with open(args.batch_overrides, "r", encoding="utf-8") as f:
            parsed_batch_overrides = json.load(f)
        if isinstance(parsed_batch_overrides, dict) and all(isinstance(v, dict) for v in parsed_batch_overrides.values()):
            for _bo_fname, _bo_overrides in parsed_batch_overrides.items():
                unknown_fields = set(_bo_overrides) - BATCH_OVERRIDE_ALLOWED_FIELDS
                if unknown_fields:
                    print(f"[WARNING] --batch-overrides: {_bo_fname!r} כולל שדות לא-נתמכים ({', '.join(sorted(unknown_fields))}) - מתעלם מהם, שאר השדות עדיין יחולו.")
                    sys.stdout.flush()
            BATCH_OVERRIDES = {
                fname: {k: v for k, v in overrides.items() if k in BATCH_OVERRIDE_ALLOWED_FIELDS}
                for fname, overrides in parsed_batch_overrides.items()
            }
        else:
            print("[WARNING] --batch-overrides חייב להיות אובייקט JSON של {שם-קובץ: {שדה: ערך}} - מתעלם, כל הקבצים ישתמשו בדגלים הגלובליים.")
            sys.stdout.flush()
    except (OSError, ValueError, TypeError):
        print("[WARNING] --batch-overrides: לא ניתן לקרוא/לפענח את הקובץ - מתעלם, כל הקבצים ישתמשו בדגלים הגלובליים.")
        sys.stdout.flush()

# item: מעברים בין כמה קטעים - בניגוד ל---only-files/--remove-ranges (דגלים
# "נחמדים-להיות" שנופלים בשקט לברירת מחדל תקינה על קלט פגום), JSON לא-תקין
# כאן הוא שגיאה חוסמת ([ERROR] + exit()) - --concat-files מבקש *מצב-ריצה*
# שלם אחר, נפילה שקטה חזרה למצב הרגיל הייתה עלולה להריץ עריכה-רגילה על כל
# הקבצים בתיקייה בלי שהמשתמש התכוון לזה בכלל.
CONCAT_FILES = None
if args.concat_files:
    try:
        parsed_concat_files = json.loads(args.concat_files)
        if not (isinstance(parsed_concat_files, list) and len(parsed_concat_files) >= 2 and all(isinstance(f, str) for f in parsed_concat_files)):
            print("[ERROR] --concat-files חייב להיות מערך JSON של לפחות שני שמות-קבצים/נתיבים.")
            sys.stdout.flush()
            exit()
        CONCAT_FILES = parsed_concat_files
    except (ValueError, TypeError):
        print("[ERROR] --concat-files אינו JSON תקין.")
        sys.stdout.flush()
        exit()
CONCAT_TRANSITION = args.concat_transition
CONCAT_TRANSITION_DURATION = max(0.0, args.concat_transition_duration)
CONCAT_OUTPUT_NAME = (args.concat_output_name or "concat_result").strip() or "concat_result"

WATERMARK_PATH = args.watermark_path
WATERMARK_POSITION = args.watermark_position
WATERMARK_SCALE = args.watermark_scale
WATERMARK_OPACITY = args.watermark_opacity
# item: גרירת watermark חופשית - שני הארגומנטים נדרשים ביחד (לא מספיק רק
# אחד מהם כדי לקבוע מיקום דו-מימדי) - חלקי (רק x או רק y) מתעלם משניהם
# ונופל בחזרה ל---watermark_position, בלי להיכשל על קלט לא-שלם.
WATERMARK_CUSTOM_CENTER = (
    (args.watermark_x, args.watermark_y) if args.watermark_x is not None and args.watermark_y is not None else None
)
REMOVE_WATERMARK_POSITION = args.remove_watermark_position
REMOVE_WATERMARK_WIDTH_FRACTION = args.remove_watermark_width_fraction
REMOVE_WATERMARK_HEIGHT_FRACTION = args.remove_watermark_height_fraction
REMOVE_WATERMARK_REGION = parse_region_fractions(args.remove_watermark_region) if args.remove_watermark_region else None
if args.remove_watermark_region and REMOVE_WATERMARK_REGION is None:
    print("[WARNING] --remove-watermark-region חייב להיות \"x,y,w,h\" בשברים 0-1 - מתעלם.")
    sys.stdout.flush()

# item: תצוגה מקדימה מלאה - מצב פריים-בודד (ראו --preview-frame).
PREVIEW_FRAME_SECONDS = max(0.0, args.preview_frame) if args.preview_frame is not None else None
PREVIEW_FRAME_OUT = args.preview_frame_out.strip() if args.preview_frame_out else ""
PREVIEW_FRAME_BEFORE_OUT = args.preview_frame_before_out.strip() if args.preview_frame_before_out else ""
if PREVIEW_FRAME_SECONDS is not None and not PREVIEW_FRAME_OUT:
    print("[ERROR] --preview-frame דורש --preview-frame-out.")
    sys.stdout.flush()
    exit()
# גל 10: קטע תצוגה מקדימה (וידאו+שמע) במקום פריים בודד - 0 = פריים רגיל.
PREVIEW_CLIP_SECONDS = min(10.0, max(1.0, args.preview_clip_seconds)) if (args.preview_clip_seconds or 0) > 0 else 0.0

# item: סף שקט מותאם (waveform בעורך-העל מציג את הקו הזה בדיוק).
SILENCE_THRESHOLD_DB = min(0.0, args.silence_threshold_db)
SILENCE_MIN_DURATION = max(0.05, args.silence_min_duration)
SILENCE_DETECT_FILTER = f"silencedetect=noise={SILENCE_THRESHOLD_DB:g}dB:d={SILENCE_MIN_DURATION:g}"
PIP_PATH = args.pip_path
PIP_POSITION = args.pip_position
PIP_CUSTOM_CENTER = (
    (min(1.0, max(0.0, args.pip_x)), min(1.0, max(0.0, args.pip_y))) if args.pip_x is not None and args.pip_y is not None else None
)
PIP_SCALE = args.pip_scale
PIP_OPACITY = args.pip_opacity
VERTICAL = args.vertical
PRESERVE_RESOLUTION = args.preserve_resolution
NO_SUFFIX = args.no_suffix
TARGET_SECONDS = args.target_seconds
# --fps (item: שימור FPS מקורי) - ריק (None) אומר "שמור את קצב הפריימים
# המקורי של כל קובץ בנפרד", נפתר בפועל per-file בתוך process_video (ראו
# resolve_output_fps) כי בריצת batch על תיקייה שלמה קבצים שונים יכולים
# להיות בקצבים מקוריים שונים. --fps מפורש נבדק כאן פעם אחת (fail-fast על
# קלט לא תקין), במקום להיכשל מאוחר יותר באמצע רינדור.
OUTPUT_FPS_OVERRIDE = args.fps.strip() if args.fps else None
if OUTPUT_FPS_OVERRIDE:
    try:
        parse_fps_value(OUTPUT_FPS_OVERRIDE)
    except ValueError as e:
        print(f"[ERROR] --fps לא תקין: {e}")
        sys.stdout.flush()
        exit()
# item: החלפת פס קול חלופי - נתיב ריק=כבוי; כשמוגדר, האודיו החלופי הוא הסיבה
# שהמשתמש בכלל צריך אודיו בפלט, אז --replace-audio מפעיל KEEP_AUDIO אוטומטית
# (בלי לדרוש גם --keep-audio מפורש בנוסף) - בלי audio_filters. --replace-audio
# בלי אודיו בפלט הוא no-op תמוה, לא באמת מה שהמשתמש רצה.
REPLACE_AUDIO_PATH = args.replace_audio.strip() if args.replace_audio else ""
KEEP_AUDIO = args.keep_audio or bool(REPLACE_AUDIO_PATH)
if REPLACE_AUDIO_PATH and not args.keep_audio:
    print("[INFO] --replace-audio הופעל בלי --keep-audio - מפעיל שמירת אודיו אוטומטית (אחרת לא יהיה אודיו בפלט להחליף).")
    sys.stdout.flush()
LOUDNORM = args.loudnorm
CODEC = args.codec
GENERATE_THUMBNAIL = args.thumbnail
FORCE = args.force
PREVIEW_ONLY = args.preview_only

CONTAINER = args.container
OUTPUT_TEMPLATE = args.output_template.strip() if args.output_template else ""
if OUTPUT_TEMPLATE:
    try:
        validate_output_template(OUTPUT_TEMPLATE)
    except ValueError as e:
        print(f"[ERROR] --output-template לא תקין: {e}")
        sys.stdout.flush()
        exit()
    if NO_SUFFIX:
        print("[INFO] --no-suffix מתעלם - --output-template גובר עליו.")
        sys.stdout.flush()

# --number-videos (item: מספור סרטונים) - שכבת-עדיפות בין --no-suffix
# ל---output-template: "<prefix> #<N>" הוא ברירת המחדל של --number-videos
# בלבד, אבל --output-template מפורש (עם/בלי {number} בפועל) גובר עליו -
# EFFECTIVE_OUTPUT_TEMPLATE הוא מה שבאמת מגיע ל-resolve_output_filename.
NUMBER_VIDEOS = args.number_videos
NUMBER_PREFIX = args.number_prefix.strip() or "Clip"
NUMBER_START = args.number_start
EFFECTIVE_OUTPUT_TEMPLATE = OUTPUT_TEMPLATE or (f"{NUMBER_PREFIX} #{{number}}" if NUMBER_VIDEOS else "")
if NUMBER_VIDEOS and OUTPUT_TEMPLATE:
    print("[INFO] --number-videos: --output-template המפורש גובר על שם ברירת-המחדל של המספור, אבל המונה עדיין פעיל - השתמש ב-{number} בתבנית כדי לכלול אותו.")
    sys.stdout.flush()
elif NUMBER_VIDEOS and NO_SUFFIX:
    print("[INFO] --no-suffix מתעלם - --number-videos גובר עליו.")
    sys.stdout.flush()

VALIDATE_ONLY = args.validate_only
NOTIFY_PER_FILE = args.notify_per_file

# --export-report (item: ייצוא דוח קידוד) - מתעלם עם --validate-only, אין
# קבצים שנוצרו בפועל לדווח עליהם (רק בדיקת filtergraph, לא רינדור אמיתי).
EXPORT_REPORT = args.export_report
if args.export_report and VALIDATE_ONLY:
    print("[INFO] --export-report מתעלם - לא רלוונטי יחד עם --validate-only.")
    sys.stdout.flush()
    EXPORT_REPORT = None

# --parallel (item: קידוד כמה סרטונים בו-זמנית) - קלאמפ ל-1 לפחות, בלי להיכשל
# על קלט שגוי (0/שלילי) שכבר ברור מה הכוונה שלו ("בלי מקביליות").
PARALLEL = max(1, args.parallel)
if args.parallel != PARALLEL:
    print(f"[INFO] --parallel {args.parallel} לא תקין - משתמש ב-{PARALLEL}.")
    sys.stdout.flush()

# --max-concurrent-nvenc (item: מגבלת-מקביליות אמיתית ל-NVENC) - רלוונטי רק כש-NVENC
# בכלל יכול להתנגש עם עצמו: --parallel>1 וקודק NVENC (hevc/av1). בלי זה, --parallel
# גבוה עם NVENC גורם לכל הקבצים לנסות לפתוח סשן קידוד באותה שנייה בדיוק ולהתנגש
# במגבלת הכרטיס/דרייבר בפועל - מנגנון הניסיון-החוזר הקיים (run_ffmpeg_with_progress_
# and_nvenc_retry) אז "סופג" את זה שוב ושוב על כמעט כל קובץ, במקום שנמנע מראש.
# NVENC_SEMAPHORE נשאר None (בלי הגבלה נוספת, זהה להתנהגות הקודמת) עם --parallel 1,
# עם --codec h264, או אם הבדיקה לא זיהתה אף סשן NVENC פעיל (למשל אין GPU של NVIDIA) -
# במקרה כזה הקידוד האמיתי ייכשל בעצמו על כל קובץ באותה סיבה, לא קשור להגבלה הזו.
NVENC_SEMAPHORE = None
if PARALLEL > 1 and CODEC in ("hevc", "av1"):
    if args.max_concurrent_nvenc is not None:
        nvenc_limit = max(1, args.max_concurrent_nvenc)
        print(f"[INFO] מגבלת NVENC מקבילים: {nvenc_limit} (הוגדר ידנית עם --max-concurrent-nvenc).")
    else:
        probe_count = min(PARALLEL, NVENC_PROBE_MAX_TO_TRY)
        print(f"[INFO] בודק מגבלת NVENC בפועל (עד {probe_count} קידודים זעירים בו-זמנית)...")
        sys.stdout.flush()
        nvenc_limit = probe_max_concurrent_nvenc_sessions(
            FFMPEG_EXE, codec=f"{CODEC}_nvenc", max_to_try=probe_count, creationflags=NO_WINDOW_FLAGS
        )
        if nvenc_limit <= 0:
            print("[WARNING] לא זוהה אף סשן NVENC פעיל בבדיקה - ממשיך בלי הגבלת-מקביליות נוספת (מנגנון הניסיון-החוזר עדיין פעיל).")
        else:
            print(f"[INFO] מגבלת NVENC בפועל שזוהתה: {nvenc_limit} קידודים מקבילים לכל היותר (מתוך --parallel {PARALLEL}).")
    if nvenc_limit > 0:
        NVENC_SEMAPHORE = threading.Semaphore(nvenc_limit)
    sys.stdout.flush()

# --effort (item: דרגות מאמץ קידוד/משאבי-מחשב) - "auto" (item: זיהוי עומס-מחשב
# אוטומטי) לא נפתר כאן פעם אחת גלובלית כמו low/medium/high - הוא נפתר פר-קובץ
# בתוך process_video (resolve_file_effort_settings), כי המטרה שלו היא להגיב
# לעומס שמשתנה במהלך ריצה ארוכה, לא לקבוע ערך קבוע מראש לכל הריצה.
EFFORT = args.effort

# --hwaccel דורש NVENC (hevc/av1) - הפריימים המפוענחים/מסוננים נשארים בפורמט
# CUDA עד לקידוד עצמו, ו-libx264 (h264) לא יודע לקבל את זה. מתעלמים בשקט
# (לא נכשלים) עם --codec h264, כמו כל דגל לא-רלוונטי אחר בפרויקט הזה.
USE_HWACCEL = args.hwaccel and CODEC in ("hevc", "av1")
if args.hwaccel and not USE_HWACCEL:
    print(f"[INFO] --hwaccel מתעלם - דורש --codec hevc/av1 (NVENC), לא {CODEC!r}.")
    sys.stdout.flush()

# item: פענוח מואץ-GPU בלי NVENC - נדחה הדדית מול --hwaccel (שכבר כולל פענוח
# מואץ כחלק מהצינור המלא שלו). בדיקת HDR האמיתית (per-file, תלויה בקובץ
# עצמו) קורית בהמשך בתוך process_video, אותו עיקרון בדיוק כמו USE_HWACCEL.
HWACCEL_DECODE = args.hwaccel_decode and not USE_HWACCEL
# גל 10: פייפליין היברידי (deinterlace/סיבוב/הקטנה על ה-GPU לפני הירידה ל-CPU)
GPU_HYBRID = not args.no_gpu_hybrid
_CUDA_FILTERS_CACHE = None


def available_cuda_filters():
    """פילטרי ה-CUDA שה-ffmpeg הזה בפועל כולל (נבדק פעם אחת לריצה) - בנייה בלי
    אחד מהם פשוט משאירה את השלב הזה ב-CPU, במקום להיכשל."""
    global _CUDA_FILTERS_CACHE
    if _CUDA_FILTERS_CACHE is None:
        try:
            listing = subprocess.run([FFMPEG_EXE, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=20, creationflags=NO_WINDOW_FLAGS).stdout
            _CUDA_FILTERS_CACHE = parse_cuda_filters(listing)
        except (OSError, subprocess.SubprocessError):
            _CUDA_FILTERS_CACHE = []
    return _CUDA_FILTERS_CACHE
if args.hwaccel_decode and not HWACCEL_DECODE:
    print("[INFO] --hwaccel-decode מתעלם - --hwaccel כבר פעיל וכולל פענוח מואץ כחלק מהצינור המלא שלו.")
    sys.stdout.flush()

# PiP (item: תמונה-בתוך-תמונה) - לא נתמך עם --hwaccel, אותו דפוס בדיוק כמו
# blur_background/chromakey למטה (אין מקבילת CUDA מוכחת בפרויקט הזה).
PIP_ENABLED = bool(PIP_PATH) and not USE_HWACCEL
if PIP_PATH and not PIP_ENABLED:
    print("[INFO] --pip מתעלם - לא נתמך עם --hwaccel (אין מקבילת CUDA מוכחת בפרויקט הזה).")
    sys.stdout.flush()

# blur_background כבר לא תלוי ב-VERTICAL (item: הכנסת סרטון אופקי לתוך מסגרת
# אנכית בלי לחתוך ממנו - ראו --blur-background למעלה) - מחושב לפני SMART_CROP
# כדי שההודעה שם תדע אם blur_background כבר בתוקף (ואז אין קרופ כלל להזיז).
BLUR_BACKGROUND = args.blur_background and not USE_HWACCEL
if args.blur_background and not BLUR_BACKGROUND:
    print("[INFO] --blur-background מתעלם - לא נתמך עם --hwaccel (אין ל-gblur מקבילת CUDA מוכחת בפרויקט הזה).")
    sys.stdout.flush()

# כרומה קי (item) - סותר את blur_background (שני אופנים שונים לבניית ה"בסיס"
# של הפריים לפני scale/watermark) אז מדורג אחריו ומתעלם אם שניהם ניתנו.
CHROMAKEY = args.chromakey and not USE_HWACCEL and not BLUR_BACKGROUND
if args.chromakey and not CHROMAKEY:
    if USE_HWACCEL:
        print("[INFO] --chromakey מתעלם - לא נתמך עם --hwaccel.")
    else:
        print("[INFO] --chromakey מתעלם - לא רלוונטי יחד עם --blur-background (שני אופנים סותרים לבניית הבסיס).")
    sys.stdout.flush()
CHROMAKEY_COLOR = args.chromakey_color
CHROMAKEY_SIMILARITY = args.chromakey_similarity
CHROMAKEY_BLEND = args.chromakey_blend
CHROMAKEY_BG_COLOR = args.chromakey_bg_color

_ANY_CROP_VARIANT = args.vertical or args.dual_output or args.aspect in ("9:16", "1:1", "4:5") or (args.aspect == "custom" and (args.custom_height or 0) >= (args.custom_width or 0)) or args.fit == "crop"
SMART_CROP = args.smart_crop and _ANY_CROP_VARIANT and not BLUR_BACKGROUND and args.rotate in (0, 180)
if args.smart_crop and not SMART_CROP:
    if args.rotate in (90, 270):
        print("[INFO] --smart-crop מתעלם - לא נתמך יחד עם סיבוב 90/270 (ניתוח התנועה נעשה על המקור הלא-מסובב).")
    elif not _ANY_CROP_VARIANT:
        print("[INFO] --smart-crop מתעלם - רלוונטי רק עם --vertical (אין crop כלל בפלט אופקי).")
    else:
        print("[INFO] --smart-crop מתעלם - לא רלוונטי יחד עם --blur-background (הפלט לא נחתך כלל, אין חלון קרופ להזיז).")
    sys.stdout.flush()

SMART_CROP_FACE = args.smart_crop_face and SMART_CROP
if args.smart_crop_face and not SMART_CROP_FACE:
    print("[INFO] --smart-crop-face מתעלם - רלוונטי רק עם --smart-crop פעיל בפועל.")
    sys.stdout.flush()

CAPTIONS = args.captions and args.keep_audio
if args.captions and not CAPTIONS:
    print("[INFO] --captions מתעלם - דורש --keep-audio (בלי זה אין אודיו בפלט לתמלל).")
    sys.stdout.flush()

CAPTIONS_TRANSLATE = args.captions_translate and CAPTIONS
if args.captions_translate and not CAPTIONS_TRANSLATE:
    print("[INFO] --captions-translate מתעלם - רלוונטי רק עם --captions פעיל בפועל.")
    sys.stdout.flush()

CAPTION_STYLE = args.caption_style
CAPTIONS_LANGUAGE = (args.captions_language or "").strip() or None
CAPTIONS_MODEL = args.captions_model
CAPTIONS_EXPORT = args.captions_export or ""
CAPTIONS_NO_BURN = args.captions_no_burn and bool(CAPTIONS_EXPORT)
CAPTIONS_SRT_DIR = (args.captions_srt_dir or "").strip()

# --- גל 7ב: שכבות / קישוטים / עיבוד-אחרי ---
LAYERS = []
if args.layers_json:
    try:
        with open(args.layers_json, encoding="utf-8") as _layers_f:
            LAYERS = sanitize_layers(json.load(_layers_f))
    except (OSError, ValueError) as e:
        print(f"[WARNING] לא הצלחתי לקרוא את קובץ השכבות ({e}) - ממשיך בלי שכבות.")
        sys.stdout.flush()
if args.timestamp_overlay:
    LAYERS.append({"type": "timestamp", "start": 0.0, "end": None, "position": args.timestamp_overlay, "opacity": 1.0,
                   "font": "Arial", "font_size": 36, "color": "#FFFFFF", "box": True, "animation": "none", "epoch": None})
PROGRESS_BAR = {
    "color": args.progress_bar_color, "position": args.progress_bar_position, "height": max(2, min(80, args.progress_bar_height)),
} if args.progress_bar else None
FRAME_BORDER = (args.frame_color, max(0, min(200, args.frame_thickness))) if args.frame_thickness > 0 else None
FRAME_RADIUS = max(0, min(200, args.frame_radius)) if FRAME_BORDER else 0
VIGNETTE_FILTER = build_vignette_filter(args.vignette)
KEN_BURNS = max(0.0, min(0.5, args.ken_burns or 0.0))
WATERMARK_MOVE_SECONDS = max(0.0, args.watermark_move_seconds or 0.0)
PIP_AUDIO = args.pip_audio and PIP_ENABLED and KEEP_AUDIO
if args.pip_audio and not PIP_AUDIO:
    print("[INFO] --pip-audio מתעלם - דורש --pip פעיל ו---keep-audio.")
    sys.stdout.flush()
PIP_DUCK = args.pip_duck and PIP_AUDIO


def _existing_or_warn(path, label):
    path = (path or "").strip()
    if path and not os.path.isfile(path):
        print(f"[WARNING] קובץ ה-{label} לא נמצא: {path} - ממשיך בלעדיו.")
        sys.stdout.flush()
        return ""
    return path


INTRO_PATH = _existing_or_warn(args.intro_path, "intro")
OUTRO_PATH = _existing_or_warn(args.outro_path, "outro")
BOOMERANG = args.boomerang
LOOP_COUNT = max(1, min(post_steps.MAX_LOOP_COUNT, args.loop_count or 1))
META_TITLE = (args.meta_title or "").strip()
META_COMMENT = (args.meta_comment or "").strip()
CHAPTERS = post_steps.parse_chapters(args.chapters)
EXPORT_GIF = args.export_gif or ""
GIF_WIDTH = max(64, min(1920, args.gif_width or 480))
GIF_FPS = max(1, min(30, args.gif_fps or 12))
EXPORT_AUDIO = args.export_audio or ""
# --- גל 8: שליטה בריצה תוך כדי (השהיה/ביטול קובץ בודד, שינוי סדר) ---
RUN_CONTROL = RunControl(args.control_file) if args.control_file else None


def _file_control(filename):
    """פונקציית-בקרה לקובץ (לרינדור עצמו) או None כשאין קובץ-בקרה."""
    if RUN_CONTROL is None:
        return None
    return lambda: RUN_CONTROL.action_for(filename)
CAPTION_FONT = args.caption_font
CAPTION_FONT_SIZE = args.caption_font_size
CAPTION_COLOR = args.caption_color
CAPTION_POSITION = args.caption_position
CAPTION_MAX_CHARS = max(0, min(80, args.caption_max_chars))

FADE_IN_SECONDS = max(0.0, args.fade_in_seconds)
FADE_OUT_SECONDS = max(0.0, args.fade_out_seconds)
TEXT = args.text.strip() if args.text else ""
TEXT_POSITION = args.text_position
TEXT_FONT = args.text_font
TEXT_FONT_SIZE = args.text_font_size
TEXT_COLOR = args.text_color
# item: כיתוב טקסט קבוע - נכתב לקובץ זמני *פעם אחת* כאן (לא inline בתוך
# מחרוזת ה-filter_complex) - ראו utils/video/video_editor.py's build_drawtext_filter
# לסיבה המלאה (escaping מהימן, לא ניחוש-וטעות עם quoting/backslash-escaping
# שנכשל בפועל על שילובי-תווים אמיתיים כמו "%"/"'"/":"" יחד). אותו טקסט בדיוק
# לכל קובץ בריצה - נכתב פעם אחת, לא בכל איטרציה בלולאה. atexit מנקה גם
# בנתיבי-יציאה מוקדמים (שגיאת ולידציה וכו'), לא רק בסיום תקין.
TEXT_FILE_PATH = None
if TEXT:
    import atexit

    def _cleanup_text_file(path):
        try:
            os.remove(path)  # safe: temp טקסט-כיתוב שהריצה הזו כתבה לעצמה (tempfile.mkstemp למעלה), לא קלט משתמש
        except OSError:
            pass

    _text_fd, TEXT_FILE_PATH = tempfile.mkstemp(suffix=".txt", prefix="video_editor_text_")
    with os.fdopen(_text_fd, "w", encoding="utf-8") as _text_f:
        _text_f.write(TEXT)
    atexit.register(_cleanup_text_file, TEXT_FILE_PATH)

TRIM_START = max(0.0, args.trim_start)
TRIM_DURATION = args.trim_duration
TRIM_SILENCE = args.trim_silence and TRIM_START <= 0.0 and TRIM_DURATION is None
if args.trim_silence and not TRIM_SILENCE:
    print("[INFO] --trim-silence מתעלם - ניתן יחד עם --trim-start/--trim-duration, עדיפות לחיתוך המפורש.")
    sys.stdout.flush()

# הסרת שקט באמצע הקובץ (item) - סותרת את שלושת אופני-החיתוך הקיימים (טווח
# מפורש/שקט-בקצוות) כי אלה כולם "בחר תת-טווח אחד רציף", וזה "הסר כמה טווחי-
# שקט פזורים" - שילוב שניהם על אותו קובץ לא מוגדר-היטב, אז עדיפות לחיתוך
# המפורש/שקט-בקצוות (אותו דפוס בדיוק כמו TRIM_SILENCE מול TRIM_START למעלה).
REMOVE_MID_SILENCE = (
    args.remove_mid_silence and KEEP_AUDIO
    and TRIM_START <= 0.0 and TRIM_DURATION is None and not args.trim_silence
)
if args.remove_mid_silence and not REMOVE_MID_SILENCE:
    if not KEEP_AUDIO:
        print("[INFO] --remove-mid-silence מתעלם - דורש --keep-audio (אין אודיו לזהות ממנו שקט בלעדיו).")
    else:
        print("[INFO] --remove-mid-silence מתעלם - ניתן יחד עם --trim-start/--trim-duration/--trim-silence, עדיפות לחיתוך המפורש.")
    sys.stdout.flush()

# item: חיתוך כמה טווחים - טווחים מפורשים-ע"י-משתמש להסרה; באותה קטגוריה
# בדיוק כמו REMOVE_MID_SILENCE ("הסר כמה טווחים פזורים", לא "בחר תת-טווח
# רציף אחד") - מתלכד עם טווחי-השקט האוטומטיים (לא מתחרה) אם שניהם ניתנו,
# אבל עדיין נדחה הדדית מול TRIM_START/TRIM_DURATION/TRIM_SILENCE, אותה
# סיבה בדיוק. לא דורש KEEP_AUDIO (בניגוד ל-REMOVE_MID_SILENCE) - הטווחים
# כאן מגיעים מהמשתמש עצמו, לא מזיהוי-שקט שדורש אודיו קיים לנתח.
REMOVE_RANGES: list = []
if args.remove_ranges:
    if TRIM_START > 0.0 or TRIM_DURATION is not None or args.trim_silence:
        print("[INFO] --remove-ranges מתעלם - ניתן יחד עם --trim-start/--trim-duration/--trim-silence, עדיפות לחיתוך המפורש.")
        sys.stdout.flush()
    else:
        try:
            parsed_remove_ranges = json.loads(args.remove_ranges)
            if (
                isinstance(parsed_remove_ranges, list)
                and all(isinstance(r, list) and len(r) == 2 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in r) for r in parsed_remove_ranges)
                and all(r[1] > r[0] >= 0 for r in parsed_remove_ranges)
            ):
                REMOVE_RANGES = [(float(r[0]), float(r[1])) for r in parsed_remove_ranges]
            else:
                print("[WARNING] --remove-ranges חייב להיות מערך JSON של [start,end] תקינים (end>start>=0) - מתעלם.")
                sys.stdout.flush()
        except (ValueError, TypeError):
            print("[WARNING] --remove-ranges אינו JSON תקין - מתעלם.")
            sys.stdout.flush()

STABILIZE = args.stabilize and not USE_HWACCEL
if args.stabilize and not STABILIZE:
    print("[INFO] --stabilize מתעלם - לא נתמך עם --hwaccel.")
    sys.stdout.flush()

LUT_PATH = args.lut.strip() if args.lut else ""
if LUT_PATH and not os.path.isfile(LUT_PATH):
    print(f"[WARNING] קובץ ה-LUT לא נמצא: {LUT_PATH} - ממשיך בלי LUT.")
    sys.stdout.flush()
    LUT_PATH = ""

AUTO_LEVELS = args.auto_levels

SMOOTH_FPS = args.smooth_fps and not USE_HWACCEL
if args.smooth_fps and not SMOOTH_FPS:
    print("[INFO] --smooth-fps מתעלם - לא נתמך עם --hwaccel.")
    sys.stdout.flush()

NOISE_GATE = args.noise_gate and KEEP_AUDIO
if args.noise_gate and not NOISE_GATE:
    print("[INFO] --noise-gate מתעלם - רלוונטי רק עם --keep-audio.")
    sys.stdout.flush()

# גל 25: חיתוך נמוכים / הפחתת רעש / EQ / קומפרסור
AUDIO_DENOISE_MODEL = (args.audio_denoise_model or "").strip().strip('"')
if AUDIO_DENOISE_MODEL and not os.path.isfile(AUDIO_DENOISE_MODEL):
    print(f"[WARNING] מודל הפחתת הרעש לא נמצא: {AUDIO_DENOISE_MODEL} - משתמש בהפחתה המובנית (afftdn).")
    sys.stdout.flush()
    AUDIO_DENOISE_MODEL = ""
try:
    AUDIO_FX_FILTERS = build_audio_fx_chain(
        args.audio_highpass, args.audio_eq_low, args.audio_eq_mid, args.audio_eq_mid_freq, args.audio_eq_high,
        args.audio_compressor, args.audio_denoise, AUDIO_DENOISE_MODEL,
    )
except ValueError as e:
    print(f"[ERROR] {e}")
    sys.stdout.flush()
    exit()
if AUDIO_FX_FILTERS and not KEEP_AUDIO:
    print("[INFO] EQ/קומפרסור/הפחתת רעש בשמע מתעלמים - רלוונטיים רק עם --keep-audio.")
    sys.stdout.flush()
    AUDIO_FX_FILTERS = []

DENOISE = args.denoise and not USE_HWACCEL
if args.denoise and not DENOISE:
    print("[INFO] --denoise מתעלם - לא נתמך עם --hwaccel.")
    sys.stdout.flush()

SHARPEN = args.sharpen and not USE_HWACCEL
if args.sharpen and not SHARPEN:
    print("[INFO] --sharpen מתעלם - לא נתמך עם --hwaccel.")
    sys.stdout.flush()

LOUDNORM_TARGET = args.loudnorm_target
LOUDNORM_FILTER_OVERRIDE = f"loudnorm=I={LOUDNORM_TARGET}:LRA=11:TP=-1.5" if LOUDNORM_TARGET is not None else None
if LOUDNORM_TARGET is not None and not (KEEP_AUDIO and LOUDNORM):
    print("[INFO] --loudnorm-target מתעלם - רלוונטי רק עם --keep-audio --loudnorm יחד.")
    sys.stdout.flush()

_NVENC_OVERRIDE_REQUESTED = args.nvenc_preset is not None or args.nvenc_cq is not None
# NVENC_PRESET_EXPLICIT - רק דריסה מפורשת ב---nvenc-preset (או None) - עדיפות
# מוחלטת על פני --effort (כולל "auto"), שנפתר פר-קובץ ב-resolve_file_effort_settings
# למטה. לא כולל את דריסת ה-effort - זו מחושבת מאוחר יותר, פר-קובץ.
NVENC_PRESET_EXPLICIT = args.nvenc_preset if CODEC in ("hevc", "av1") else None
NVENC_CQ = args.nvenc_cq if CODEC in ("hevc", "av1") else None
if _NVENC_OVERRIDE_REQUESTED and CODEC not in ("hevc", "av1"):
    print(f"[INFO] --nvenc-preset/--nvenc-cq מתעלמים - רלוונטי רק עם --codec hevc/av1, לא {CODEC!r}.")
    sys.stdout.flush()

TARGET_SIZE_MB = args.target_size_mb
if TARGET_SIZE_MB is not None and args.nvenc_cq is not None:
    print("[INFO] --nvenc-cq מתעלם - --target-size-mb עובר למצב VBR עם יעד ביטרייט, לא CQ.")
    sys.stdout.flush()

# --- גל 7: יחסי-רוחב / פלט כפול / רזולוציה / מהירות / צבע / סיבוב ---
try:
    ASPECT_DIMS = resolve_aspect_dimensions(args.aspect, args.custom_width, args.custom_height)
except ValueError as e:
    print(f"[ERROR] {e}")
    sys.stdout.flush()
    exit()
FIT = args.fit
RESOLUTION_PRESET = args.resolution
SCALE_ALGO = args.scale_algo
PAD_COLOR = (args.pad_color or "black").strip()
if PAD_COLOR.startswith("#"):
    PAD_COLOR = "0x" + PAD_COLOR[1:]
WATERMARK_POSITION_VERTICAL = args.watermark_position_vertical or ""
ROTATE = args.rotate
FLIP = args.flip
ORIENTATION_FILTERS = build_orientation_filters(ROTATE, FLIP)
DEINTERLACE = args.deinterlace
AUDIO_TRACK = args.audio_track if args.audio_track is not None and args.audio_track >= 0 else None
EQ_FILTER = build_eq_filter(
    max(-1.0, min(1.0, args.eq_brightness)), max(0.0, min(3.0, args.eq_contrast)),
    max(0.0, min(3.0, args.eq_saturation)), max(0.1, min(10.0, args.eq_gamma)),
)
# גל 25: גלגלי lift/gamma/gain ועקומות - אחרי ה-eq, באותו שלב של השרשרת (פילטרי CPU,
# כך שעם --hwaccel מלא הסינון עובר ל-CPU כמו eq - ראו cpu_only_filters)
try:
    GRADE_FILTER = build_color_grade_filter(
        args.grade_shadows, args.grade_midtones, args.grade_highlights,
        args.curves_preset, args.curves_master, args.curves_red, args.curves_green, args.curves_blue,
    )
except ValueError as e:
    print(f"[ERROR] תיקון צבע: {e}")
    sys.stdout.flush()
    exit()
EQ_FILTER = ",".join(f for f in (EQ_FILTER, GRADE_FILTER) if f)
LUT_INTENSITY = max(0.0, min(1.0, args.lut_intensity))
DENOISE_FILTER_OVERRIDE = DENOISE_LEVELS[args.denoise_level]
SHARPEN_FILTER_OVERRIDE = SHARPEN_LEVELS[args.sharpen_level]
TONEMAP_FILTER_OVERRIDE = build_tonemap_filter(args.tonemap)
SPEED = max(0.25, min(4.0, args.speed or 1.0))
if abs(SPEED - 1.0) > 1e-6 and TARGET_SECONDS > 0:
    print("[INFO] --speed מתעלם - --target-seconds (טיימלאפס) קובע את המהירות בעצמו.")
    sys.stdout.flush()
    SPEED = 1.0
CRF = max(0, min(51, args.crf)) if args.crf is not None else None
# איכות לקודק הנבחר: CQ ל-NVENC, CRF ל-H.264 (get_codec_args מחיל cq על -cq או -crf, לפי הקודק)
CODEC_QUALITY = NVENC_CQ if CODEC in ("hevc", "av1") else CRF


OUTPUT_SUBDIR = args.output_subdir.strip() if re.fullmatch(r"[A-Za-z0-9_-]{1,40}", (args.output_subdir or "").strip()) else ""
if args.output_subdir and not OUTPUT_SUBDIR:
    print("[WARNING] --output-subdir לא תקין (רק אותיות/ספרות/_/-) - מתעלם.")
    sys.stdout.flush()


def _variant(vertical, dims=None):
    orientation = orientation_for_dimensions(*dims) if dims else ("vertical" if vertical else "horizontal")
    root = export_output_dir(STUDIO, orientation)  # <תיקיית הסטודיו>/<כיוון>, או <תיקיית הייצוא / workspace>/studio/<כיוון> (עד 19.10.2026: <כיוון>/edited_videos)
    return {
        "vertical": orientation == "vertical", "dims": dims, "orientation": orientation,
        "output_root": os.path.join(root, OUTPUT_SUBDIR) if OUTPUT_SUBDIR else root,
    }


# item: פלט כפול - כל קובץ עובר פעמיים (אופקי+אנכי). item: יחסי-רוחב - 16:9/9:16
# ממופים לנתיבים הרגילים (כולל תמיכת CUDA), כל השאר ל-scale "fit" כללי.
if args.dual_output:
    if args.aspect:
        print("[INFO] --aspect מתעלם - --dual-output מפיק תמיד 16:9 וגם 9:16.")
        sys.stdout.flush()
    VARIANTS = [_variant(False), _variant(True)]
elif args.aspect in ("16:9", "9:16"):
    VARIANTS = [_variant(args.aspect == "9:16")]
elif ASPECT_DIMS:
    VARIANTS = [_variant(False, ASPECT_DIMS)]
else:
    VARIANTS = [_variant(VERTICAL)]
VERTICAL = VARIANTS[0]["vertical"]  # קוד שלא יודע על variants (concat/contact-sheet) רואה את הראשון

OUTPUT_DIR = VARIANTS[0]["output_root"]
os.makedirs(OUTPUT_DIR, exist_ok=True)

# item: ייצוא דוח קידוד - תת-תיקייה משותפת ל-vertical/horizontal (לא מקוננת
# תחת אף אחד מהם) כי דוח ריצה בודד יכול לכלול קבצים משניהם (למשל אם INPUT_DIR
# מכיל תת-תיקיות עם --vertical)... בפועל VERTICAL הוא דגל גלובלי לכל הריצה
# (לא פר-קובץ), אז זה תמיד עקבי בפועל - אבל workspace/reports/ (לא workspace/
# vertical|horizontal/reports/) נשאר נכון-בכל-מקרה ופשוט יותר למצוא.
REPORTS_DIR = os.path.join(WORKSPACE_ROOT, "reports")

if not INPUT_DIR:
    print("[ERROR] לא נבחרה תיקייה. ביטול פעולה.")
    sys.stdout.flush()
    exit()


# get_video_duration_seconds/get_video_resolution הוחלפו ב-probe_video()
# (utils/media/ffprobe_cache.py, item 20) - שתי הפונקציות קראו ל-ffprobe בנפרד על
# אותו video_path בדיוק בתוך אותה קריאה ל-process_video (משך + רזולוציה),
# עכשיו זו קריאת ffprobe אחת ממוטמנת במקום שתיים.


def resolve_removal_region(input_width, input_height):
    """מחזיר (x, y, w, h) או None אם לא התבקשה מחיקת watermark ישן. אזור שסומן
    ידנית (--remove-watermark-region) גובר על מיקום-פינה+שברי-גודל."""
    if REMOVE_WATERMARK_REGION is not None:
        return compute_custom_removal_region(input_width, input_height, REMOVE_WATERMARK_REGION)
    if not REMOVE_WATERMARK_POSITION:
        return None
    return compute_removal_region(
        input_width, input_height, REMOVE_WATERMARK_POSITION,
        width_fraction=REMOVE_WATERMARK_WIDTH_FRACTION, height_fraction=REMOVE_WATERMARK_HEIGHT_FRACTION,
    )


def resolve_watermark_geometry(output_width, output_height, watermark_path=None, watermark_position=None, watermark_scale=None,
                               custom_center=None):
    """מחזיר (target_w, target_h, x, y) או None אם אין watermark/הקובץ לא תקין -
    כשל בקריאת תמונת ה-watermark לא אמור להפיל את כל הריצה, רק לדלג עליה.
    הפרמטרים האחרונים None (ברירת מחדל) = נופלים ל-WATERMARK_PATH/
    POSITION/SCALE/CUSTOM_CENTER הגלובליים - הקורא הרגיל (בלי --batch-overrides) לא צריך
    להעביר כלום; process_video מעביר overrides מפורשים כשיש (item: ממשק batch).
    custom_center=False = בלי מרכז גרירה (מיקום פינה מפורש לקובץ הזה, גל 30)."""
    watermark_path = WATERMARK_PATH if watermark_path is None else watermark_path
    watermark_position = WATERMARK_POSITION if watermark_position is None else watermark_position
    watermark_scale = WATERMARK_SCALE if watermark_scale is None else watermark_scale
    if not watermark_path:
        return None
    if not os.path.isfile(watermark_path):
        print(f"[WARNING] קובץ ה-watermark לא נמצא: {watermark_path} - ממשיך בלי watermark.")
        sys.stdout.flush()
        return None
    try:
        with Image.open(watermark_path) as img:
            wm_width, wm_height = img.size
    except Exception as e:
        print(f"[WARNING] לא הצלחתי לקרוא את קובץ ה-watermark ({e}) - ממשיך בלי watermark.")
        sys.stdout.flush()
        return None
    return compute_watermark_geometry(
        output_width, output_height, wm_width, wm_height, watermark_position,
        scale_fraction=watermark_scale,
        custom_center_fraction=WATERMARK_CUSTOM_CENTER if custom_center is None else (custom_center or None),
    )


def resolve_pip_geometry(output_width, output_height):
    """כמו resolve_watermark_geometry, אבל לקובץ וידאו (item: PiP) - מידות
    נקראות ב-ffprobe (probe_video, אותה פונקציה/מטמון כמו לקובץ הראשי) במקום
    PIL.Image, כי ל-PiP אין frame יחיד קבוע כמו תמונת watermark סטטית.
    כשל בקריאת הקובץ לא אמור להפיל את כל הריצה, רק לדלג על PiP."""
    if not PIP_ENABLED:
        return None
    if not os.path.isfile(PIP_PATH):
        print(f"[WARNING] קובץ ה-PiP לא נמצא: {PIP_PATH} - ממשיך בלי PiP.")
        sys.stdout.flush()
        return None
    pip_probe = probe_video(PIP_PATH)
    if not pip_probe.get("width") or not pip_probe.get("height"):
        print("[WARNING] לא הצלחתי לקרוא את רזולוציית קובץ ה-PiP - ממשיך בלי PiP.")
        sys.stdout.flush()
        return None
    return compute_watermark_geometry(
        output_width, output_height, pip_probe["width"], pip_probe["height"], PIP_POSITION,
        scale_fraction=PIP_SCALE, custom_center_fraction=PIP_CUSTOM_CENTER,
    )


def maybe_generate_thumbnail(video_output_path, tonemap_hdr=False):
    """זהה בעיקרון ל-rocket_shorts_publisher.py - אופציונלי (--thumbnail),
    כשל לא אמור לעצור את שאר הפייפליין. tonemap_hdr (item: שימור הגדרות HDR -
    תמונה ממוזערת תמיד ב-SDR) - כש-video_output_path עצמו נשמר HDR (hdr_passthrough
    ב-process_video), התמונה הממוזערת עדיין עוברת tone-mapping ל-SDR רגיל -
    היא נצפית כתמונה סטטית בגלריה/רשימה, לא במסך HDR, אז HDR-metadata שם
    היה רק גורם לה להיראות שטופה/דהויה בלי שום יתרון."""
    if not GENERATE_THUMBNAIL:
        return
    try:
        from utils.media.thumbnail_generator import generate_thumbnail
        thumb_path = os.path.splitext(video_output_path)[0] + "_thumb.jpg"
        generate_thumbnail(video_output_path, thumb_path, ffmpeg_exe=FFMPEG_EXE, ffprobe_exe=FFPROBE_EXE, tonemap_hdr=tonemap_hdr)
        print(f"  🖼️  תמונה ממוזערת נוצרה: {os.path.basename(thumb_path)}")
    except Exception as e:
        print(f"  ⚠️ יצירת תמונה ממוזערת נכשלה (לא עוצר את הפייפליין): {e}")


def maybe_burn_captions(video_output_path, hdr_output_args=None, nvenc_preset=None, source_path=None):
    """זהה בעיקרון ל-rocket_shorts_publisher.py's maybe_burn_captions - אופציונלי
    (--captions, דורש --keep-audio - ראו הבדיקה ב-CAPTIONS למעלה), כשל (למשל
    אין דיבור מזוהה לתמלל) לא אמור לעצור את שאר הפייפליין.

    video_codec_args=get_codec_args(...) ו-hdr_output_args (item: שימור
    הגדרות HDR - תיקון) - בלי אלה, שריפת הכתוביות (re-encode נפרד) הייתה
    דורסת בשקט את קודק/HDR הפלט שכבר נבחרו ברינדור המקורי (ffmpeg בוחר
    ברירת מחדל, בד"כ libx264/SDR) - נמצא כשהוספנו עיצוב כתוביות ובדקנו את
    הפונקציה הקיימת מקרוב לראשונה."""
    if not CAPTIONS:
        return
    try:
        from utils.media.captions import burn_captions
        from utils.media.captions import edited_captions_path
        edited = edited_captions_path(CAPTIONS_SRT_DIR, source_path) if (CAPTIONS_SRT_DIR and source_path) else None
        burn_captions(
            video_output_path, ffmpeg_exe=FFMPEG_EXE, translate_to_english=CAPTIONS_TRANSLATE,
            font_name=CAPTION_FONT, font_size=CAPTION_FONT_SIZE, font_color=CAPTION_COLOR, position=CAPTION_POSITION,
            video_codec_args=get_codec_args(CODEC, preset=nvenc_preset, cq=CODEC_QUALITY), hdr_output_args=hdr_output_args,
            style=CAPTION_STYLE, language=CAPTIONS_LANGUAGE, model_size=CAPTIONS_MODEL,
            export_formats=CAPTIONS_EXPORT, burn=not CAPTIONS_NO_BURN,
            srt_override_path=edited if (edited and os.path.exists(edited)) else None,
            max_chars=CAPTION_MAX_CHARS,
        )
        if edited and os.path.exists(edited):
            print(f"  📝 שימוש בתמלול ערוך: {os.path.basename(edited)}")
        if CAPTIONS_NO_BURN:
            print(f"  📄 קובץ כתוביות יוצא (בלי שריפה): {os.path.basename(video_output_path)}")
        else:
            print(f"  💬 כתוביות נשרפו{' (מתורגם לאנגלית)' if CAPTIONS_TRANSLATE else ''}: {os.path.basename(video_output_path)}")
    except Exception as e:
        print(f"  ⚠️ שריפת כתוביות נכשלה (לא עוצר את הפייפליין): {e}")


def _run_post_step(cmd, label, temp_path, output_path):
    """מריץ שלב עיבוד-אחרי לקובץ זמני ליד הפלט ומחליף את הפלט רק בהצלחה - כשל לא
    עוצר את הפייפליין (אותו עיקרון כמו שריפת הכתוביות)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW_FLAGS)
        ok = result.returncode == 0 and os.path.exists(temp_path) and os.path.getsize(temp_path) > 0
        error_tail = (result.stderr or "").strip()[-300:]
    except Exception as e:
        ok, error_tail = False, str(e)
    if not ok:
        if os.path.exists(temp_path):
            os.remove(temp_path)  # safe: temp post-step output this run wrote itself (post_temp_path), not user input
        print(f"  ⚠️ {label} נכשל (לא עוצר את הפייפליין): {error_tail}")
        sys.stdout.flush()
        return False
    if temp_path != output_path:
        os.replace(temp_path, output_path)  # safe: this run's own temp next to its own output (same drive)
    return True


def maybe_post_process(output_path, output_width, output_height, output_fps, nvenc_preset, hdr_output_args):
    """גל 7ב: intro/outro -> boomerang -> loop -> מטא-דאטה/פרקים -> ייצוא נוסף (GIF/WebP/אודיו).
    כל שלב על הפלט הגמור (אחרי הכתוביות), כל אחד אופציונלי ולא-קריטי."""
    has_steps = INTRO_PATH or OUTRO_PATH or BOOMERANG or LOOP_COUNT > 1 or META_TITLE or META_COMMENT or CHAPTERS or EXPORT_GIF or EXPORT_AUDIO
    if not has_steps:
        return
    codec_args = get_codec_args(CODEC, preset=nvenc_preset, cq=CODEC_QUALITY) + list(hdr_output_args or [])
    name = os.path.basename(output_path)
    intro_offset = 0.0
    if INTRO_PATH or OUTRO_PATH:
        clips = []
        for path in (INTRO_PATH, output_path, OUTRO_PATH):
            if path:
                info = probe_video(path)
                clips.append((path, float(info.get("duration") or 0.0), bool(info.get("has_audio"))))
        include_audio = clips[1 if INTRO_PATH else 0][2]
        temp = post_steps.post_temp_path(output_path, "bumpers")
        cmd = post_steps.build_bumper_concat_command(FFMPEG_EXE, clips, output_width, output_height, output_fps, include_audio, codec_args, temp)
        if _run_post_step(cmd, "הוספת intro/outro", temp, output_path):
            intro_offset = clips[0][1] if INTRO_PATH else 0.0
            print(f"  🎬 נוספו {' + '.join(label for label, path in (('intro', INTRO_PATH), ('outro', OUTRO_PATH)) if path)}: {name}")
    if BOOMERANG:
        info = probe_video(output_path)
        duration = float(info.get("duration") or 0.0)
        if duration > post_steps.BOOMERANG_MAX_SECONDS:
            print(f"  [INFO] boomerang מתעלם - {duration:.0f}s ארוך מ-{post_steps.BOOMERANG_MAX_SECONDS:.0f}s (reverse מחזיק את כל הקליפ בזיכרון).")
        else:
            temp = post_steps.post_temp_path(output_path, "boomerang")
            cmd = post_steps.build_boomerang_command(FFMPEG_EXE, output_path, bool(info.get("has_audio")), codec_args, temp)
            if _run_post_step(cmd, "boomerang", temp, output_path):
                print(f"  🔁 boomerang: {name}")
    if LOOP_COUNT > 1:
        temp = post_steps.post_temp_path(output_path, "loop")
        if _run_post_step(post_steps.build_loop_command(FFMPEG_EXE, output_path, LOOP_COUNT, temp), "חזרה (loop)", temp, output_path):
            print(f"  🔂 x{LOOP_COUNT}: {name}")
    if META_TITLE or META_COMMENT or CHAPTERS:
        total = float(probe_video(output_path).get("duration") or 0.0)
        meta_path = post_steps.post_temp_path(output_path, "ffmeta") + ".txt"
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write(post_steps.build_ffmetadata(META_TITLE, META_COMMENT, CHAPTERS, total, offset=intro_offset))
        temp = post_steps.post_temp_path(output_path, "meta")
        try:
            if _run_post_step(post_steps.build_metadata_command(FFMPEG_EXE, output_path, meta_path, temp), "מטא-דאטה/פרקים", temp, output_path):
                print(f"  🏷️ מטא-דאטה{f' + {len(CHAPTERS)} פרקים' if CHAPTERS else ''}: {name}")
        finally:
            os.remove(meta_path)  # safe: temp ffmetadata file this run wrote itself
    for kind, target in post_steps.extra_export_paths(output_path, EXPORT_GIF, EXPORT_AUDIO).items():
        if kind == "gif":
            cmd = post_steps.build_gif_command(FFMPEG_EXE, output_path, target, GIF_WIDTH, GIF_FPS)
        elif kind == "webp":
            cmd = post_steps.build_webp_command(FFMPEG_EXE, output_path, target, GIF_WIDTH, GIF_FPS)
        else:
            if not probe_video(output_path).get("has_audio"):
                print(f"  [INFO] ייצוא {kind} מתעלם - לפלט אין פס-קול.")
                continue
            cmd = post_steps.build_audio_export_command(FFMPEG_EXE, output_path, target, kind)
        if _run_post_step(cmd, f"ייצוא {kind.upper()}", target, target):
            print(f"  📦 יוצא {kind.upper()}: {os.path.basename(target)}")
    sys.stdout.flush()


def resolve_smart_crop_offset(video_path):
    """מחזיר את היסט חלון הקרופ האנכי (-1.0..1.0, utils/media/smart_crop.py) או None
    אם לא התבקש - כשל בניתוח תנועה לא אמור לעצור רינדור, רק לחזור לקרופ-
    במרכז הרגיל (compute_horizontal_crop_offset עצמה כבר מחזירה 0.0 על כשל,
    לא זורקת - ה-try/except כאן מכסה תקלות בלתי-צפויות ברמת ה-import/cv2 עצמו)."""
    if not SMART_CROP:
        return None
    try:
        if SMART_CROP_FACE:
            from utils.media.smart_crop import compute_horizontal_crop_offset_face
            return compute_horizontal_crop_offset_face(video_path)
        from utils.media.smart_crop import compute_horizontal_crop_offset
        return compute_horizontal_crop_offset(video_path)
    except Exception as e:
        print(f"  ⚠️ ניתוח smart-crop נכשל (ממשיך עם קרופ במרכז): {e}")
        return None


def detect_silence_trim_bounds(video_path, duration):
    """מריץ ffmpeg עם silencedetect בלבד (-vn, בלי לקודד וידאו כלל, פלט ל-null)
    כדי לזהות שקט בתחילת/סוף הקובץ (item: auto-trim silence). כשל (או אין
    ערוץ אודיו בכלל בקובץ) מוחזר כ-(0.0, None) - "בלי חיתוך" - לא עוצר רינדור."""
    if not TRIM_SILENCE or PREVIEW_FRAME_SECONDS is not None:  # תצוגה מקדימה: בלי ניתוח-שקט על כל הקובץ (איטי)
        return 0.0, None
    try:
        cmd = [FFMPEG_EXE, "-i", video_path, "-vn", "-af", SILENCE_DETECT_FILTER, "-f", "null", os.devnull]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, creationflags=NO_WINDOW_FLAGS)
        intervals = parse_silence_intervals(result.stderr, duration=duration)
        return compute_silence_trim_bounds(duration, intervals, min_silence_seconds=SILENCE_MIN_DURATION)
    except Exception as e:
        print(f"  ⚠️ זיהוי שקט אוטומטי נכשל (ממשיך בלי חיתוך): {e}")
        return 0.0, None


def detect_all_silence_intervals(video_path, duration):
    """כמו detect_silence_trim_bounds, אבל מחזיר את *כל* טווחי-השקט שזוהו
    (לא רק בקצוות) - item: הסרת שקט באמצע הקובץ. [] (בלי חיתוך) על כשל/אין
    ערוץ אודיו - לא עוצר רינדור."""
    if not REMOVE_MID_SILENCE or PREVIEW_FRAME_SECONDS is not None:
        return []
    try:
        cmd = [FFMPEG_EXE, "-i", video_path, "-vn", "-af", SILENCE_DETECT_FILTER, "-f", "null", os.devnull]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, creationflags=NO_WINDOW_FLAGS)
        return parse_silence_intervals(result.stderr, duration=duration)
    except Exception as e:
        print(f"  ⚠️ זיהוי שקט למחיקה-באמצע נכשל (ממשיך בלי הסרה): {e}")
        return []


def detect_stabilization_transform(video_path):
    """מעבר 1/2 של ייצוב וידאו (item) - מריץ vidstabdetect (ניתוח בלבד, בלי
    לקודד וידאו) וכותב את התוצאה לקובץ transforms זמני, שנתיבו מוחזר. הקורא
    (process_video) אחראי למחוק את הקובץ אחרי השימוש (גם על כשל הרינדור
    עצמו). None על כשל - לא עוצר רינדור, ממשיך בלי ייצוב."""
    if not STABILIZE or PREVIEW_FRAME_SECONDS is not None:  # תצוגה מקדימה: מעבר-ניתוח מלא איטי מדי לפריים בודד
        return None
    fd, transforms_path = tempfile.mkstemp(suffix=".trf", prefix="vidstab_")
    os.close(fd)
    try:
        cmd = [FFMPEG_EXE, "-y", "-i", video_path, "-vf", get_vidstabdetect_filter(transforms_path), "-f", "null", os.devnull]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, creationflags=NO_WINDOW_FLAGS)
        if result.returncode != 0 or not os.path.exists(transforms_path) or os.path.getsize(transforms_path) == 0:
            raise RuntimeError((result.stderr or "").strip()[-300:] or "vidstabdetect לא הפיק קובץ transforms תקין")
        return transforms_path
    except Exception as e:
        print(f"  ⚠️ ניתוח ייצוב וידאו נכשל (ממשיך בלי ייצוב): {e}")
        try:
            os.remove(transforms_path)  # safe: temp vidstab transforms file this run created itself (tempfile.mkstemp above), not user input
        except OSError:
            pass
        return None


def snapshot_previous_output_if_forcing(output_path):
    """item: versioning - לפני --force שעומד לדרוס פלט קיים, מעביר את הגרסה
    הקודמת (+ .sig.json/thumbnail אם קיימים) לתת-תיקיית _previous עם חותמת-
    זמן, במקום לדרוס אותה בשקט לצמיתות. שומר רק את הגרסה האחרונה-שנדרסה
    בפועל (לא היסטוריה מלאה) - מספיק כדי לא לאבד רינדור קודם בטעות, בלי
    לצבור עותקים ללא-הגבלה על פני חודשים של --force חוזר. לא עושה כלום אם
    אין בכלל פלט קודם קיים לשמר."""
    if not FORCE or not os.path.exists(output_path):
        return
    output_dir = os.path.dirname(output_path)
    previous_dir = os.path.join(output_dir, "_previous")
    os.makedirs(previous_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    stem = os.path.splitext(output_path)[0]
    candidates = [output_path, resolve_sig_path(output_path), stem + "_thumb.jpg"]
    moved_any = False
    for path in candidates:
        if not os.path.exists(path):
            continue
        dest = os.path.join(previous_dir, f"{timestamp}_{os.path.basename(path)}")
        try:
            os.replace(path, dest)  # safe: moves this script's own previously-rendered output within its own output_dir (never touches INPUT_DIR/user source files)
            moved_any = True
        except OSError as e:
            print(f"  ⚠️ שמירת גרסה קודמת ({os.path.basename(path)}) נכשלה: {e}")
    if moved_any:
        print(f"  🗂️  גרסה קודמת של {os.path.basename(output_path)} נשמרה תחת _previous/ לפני הרינדור-מחדש.")
        sys.stdout.flush()


def resolve_file_effort_settings():
    """--effort (item: דרגות מאמץ, כולל "auto" - item: זיהוי עומס-מחשב אוטומטי) -
    נפתר פר-קובץ, לא פעם אחת גלובלית: EFFORT=="auto" קורא עומס CPU/GPU בפועל
    ברגע הזה (utils.shared.hardware, שני הקריאות זולות - get_gpu_stats קוראת מ-cache
    שמתעדכן ברקע, לא מריצה nvidia-smi חדש בכל קריאה) ובוחר low/medium/high
    לפי resolve_auto_effort - כדי שדרגת המאמץ תגיב לעומס שמשתנה במהלך ריצה
    ארוכה, לא תיקבע פעם אחת מראש לכל הבאצ'. מחזיר (effective_effort,
    nvenc_preset, thread_count) - nvenc_preset מכבד --nvenc-preset המפורש
    (NVENC_PRESET_EXPLICIT) קודם, effort רק אם הוא לא ניתן."""
    effective_effort = EFFORT
    if EFFORT == "auto":
        cpu_percent, _ram_percent = get_system_stats()
        gpu_percent, _vram_percent, _encoder_percent = get_gpu_stats()
        effective_effort = resolve_auto_effort(cpu_percent, gpu_percent)
    nvenc_preset = NVENC_PRESET_EXPLICIT
    if nvenc_preset is None and CODEC in ("hevc", "av1") and EFFORT_NVENC_PRESET.get(effective_effort):
        nvenc_preset = EFFORT_NVENC_PRESET[effective_effort]
    thread_count = resolve_effort_thread_count(effective_effort, os.cpu_count())
    return effective_effort, nvenc_preset, thread_count


def maybe_notify_per_file(filename, success, detail=""):
    """--notify-per-file (item) - Toast + Webhook (אם state.discord_webhook_url
    מוגדר) על כל קובץ בנפרד, לא רק סיכום-batch אחד בסוף. כשל בשליחה (למשל
    winotify/requests לא מותקנים, או שאין webhook מוגדר) לא עוצר את הרינדור -
    שתי הפונקציות הקיימות (utils/shared/notifications.py) כבר no-op בשקט על כשל,
    אבל עטופות כאן ב-try/except בכל זאת כהגנה נוספת סביב קריאה לא-קריטית."""
    if not NOTIFY_PER_FILE:
        return
    icon = "✅" if success else "❌"
    message = f"{icon} {filename}{f' - {detail}' if detail else ''}"
    try:
        from utils.shared import ui_language   # 30.10.2026: הכותרת בשפת ההתקנה, כמו תפריט המגש
        send_toast_notification("Studio (video_editor.py)" if ui_language.current() == "en" else "עורך-העל (video_editor.py)",
                                message)
        webhook_url = getattr(state, "discord_webhook_url", "")
        if webhook_url:
            send_webhook_notification(webhook_url, message)
    except Exception as e:
        print(f"  ⚠️ שליחת התראה פר-קובץ נכשלה (לא עוצר את הפייפליין): {e}")


def _compute_current_signature(video_path):
    """חתימת "smart re-encode skip" (item) - כוללת *רק* את זהות קובץ המקור
    עצמו (mtime+size מהדיסק), לא אף הגדרה של הריצה הנוכחית (watermark/קידוד/
    חיתוך/וכו'). שינוי הגדרות בין ריצה לריצה כבר לא גורם רינדור-מחדש של קובץ
    שכבר עובד בעבר - כל עוד יש לו .sig.json ופלט קיימים, הוא ידולג בלי קשר
    למה שהשתנה בהגדרות הריצה הזו (השתמש ב---force כדי לכפות רינדור-מחדש בכל
    זאת, למשל אחרי שינוי הגדרות שכן רוצים להחיל מחדש). רק אם תוכן קובץ-המקור
    עצמו השתנה בפועל (אותו שם קובץ, mtime/גודל שונים - למשל הוקלט מחדש) הדילוג
    "נשבר" - נשאר בכוונה, כדי לא להגיש תוצר מיושן בשקט על תוכן שכבר הוחלף.
    None אם לא הצלחנו אפילו לקרוא את קובץ המקור (אז אין מה להשוות, וממשיכים
    לרנדר כרגיל בלי סיכון לדלג בטעות).

    היסטוריה: לפני זה החתימה כללה גם את כל הגדרות הריצה - כל שינוי הגדרות,
    אפילו כזה שלא נוגע לקובץ הזה בכלל (למשל הפעלת --thumbnail לקבצים חדשים
    בתיקייה), גרם לרינדור-מחדש שגוי של כל קובץ אחר שכבר עובד קודם. בגלל
    ששינוי הפורמט הזה בעצמו משנה גם את החתימה, הריצה הראשונה על כל קובץ אחרי
    העדכון הזה עדיין תרנדר-מחדש פעם אחת (חתימה ישנה לא תואמת לחדשה) -
    מהריצה הבאה על אותו קובץ, הדילוג כבר לא תלוי בהגדרות בכלל."""
    try:
        stat = os.stat(video_path)
        source_fingerprint = f"{stat.st_mtime_ns}:{stat.st_size}"
    except OSError:
        return None
    return compute_render_signature(source_fingerprint, {})


# יעדים זהים (הרצה מקצה לקצה, 16.10): Shorts, TikTok ו-Reels הם ריצות נפרדות עם אותן הגדרות בדיוק - רק תת-תיקיית הפלט
# שונה - וכל אחת רינדרה מחדש את אותו סרטון. "מפתח רינדור" = כל הארגומנטים שמשפיעים על הפלט (בלי תת-התיקייה, קובץ
# השליטה, --force וכדומה; קובצי שכבות/דריסות לפי התוכן שלהם, וכל קובץ אחר - לוגו, LUT, שמע - לפי גודל וזמן שינוי)
# + טביעת קובץ המקור + הדריסות שלו. פלט של יעד אחר באותו כיוון עם אותו מפתח מקושר (hard link, או עותק) במקום רינדור.
_RENDER_KEY_VALUE_FLAGS_IGNORED = {"--output-subdir", "--control-file", "--parallel", "--export-report", "--max-concurrent-nvenc"}
_RENDER_KEY_BOOL_FLAGS_IGNORED = {"--force", "--notify-per-file"}
_RENDER_KEY_CONTENT_FLAGS = {"--layers-json", "--batch-overrides"}


def _render_key(video_path, overrides, argv=None):
    parts = []
    args = list(sys.argv[1:] if argv is None else argv)
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in _RENDER_KEY_BOOL_FLAGS_IGNORED:
            i += 1
            continue
        if arg in _RENDER_KEY_VALUE_FLAGS_IGNORED:
            i += 2
            continue
        if arg in _RENDER_KEY_CONTENT_FLAGS and i + 1 < len(args):
            try:
                with open(args[i + 1], encoding="utf-8") as f:
                    parts += [arg, f.read()]
            except OSError:
                return None
            i += 2
            continue
        if os.path.isfile(arg):
            stat = os.stat(arg)
            arg = f"{os.path.normcase(os.path.abspath(arg))}|{stat.st_mtime_ns}|{stat.st_size}"
        parts.append(arg)
        i += 1
    try:
        stat = os.stat(video_path)
    except OSError:
        return None
    parts += [f"{stat.st_mtime_ns}:{stat.st_size}", json.dumps(overrides or {}, sort_keys=True, ensure_ascii=False)]
    return compute_render_signature(json.dumps(parts, ensure_ascii=False), {})


def _render_key_path(output_path):
    return os.path.join(os.path.dirname(resolve_sig_path(output_path)), os.path.basename(output_path) + ".render.json")


def _remember_render_key(output_path, key):
    if not OUTPUT_SUBDIR or not key:
        return
    try:
        os.makedirs(os.path.dirname(_render_key_path(output_path)), exist_ok=True)   # _sig/ עוד לא קיימת בתיקיית פלט חדשה
        with open(_render_key_path(output_path), "w", encoding="utf-8") as f:
            json.dump({"key": key}, f)
    except OSError:
        pass  # לא קריטי - רק יעד אחר לא יוכל להשתמש בפלט הזה


def _reuse_identical_target_render(output_path, output_dir, variant, key):
    """נתיב הפלט שקושר מיעד אחר (תת-תיקייה אחות באותו כיוון), או None - ואז מרנדרים כרגיל."""
    if not OUTPUT_SUBDIR or not key or args.export_gif or args.export_audio or os.path.exists(output_path):
        return None
    root = variant["output_root"]
    rel = os.path.relpath(output_dir, root)
    parent = os.path.dirname(root)
    try:
        siblings = sorted(name for name in os.listdir(parent) if name != OUTPUT_SUBDIR and os.path.isdir(os.path.join(parent, name)))
    except OSError:
        return None
    for name in siblings:
        source = os.path.normpath(os.path.join(parent, name, rel, os.path.basename(output_path)))
        try:
            with open(_render_key_path(source), encoding="utf-8") as f:
                if json.load(f).get("key") != key or not os.path.isfile(source):
                    continue
        except (OSError, ValueError, AttributeError):
            continue
        os.makedirs(output_dir, exist_ok=True)
        stem_src, stem_dst = os.path.splitext(source)[0], os.path.splitext(output_path)[0]
        for src, dst in ((source, output_path), (stem_src + "_thumb.jpg", stem_dst + "_thumb.jpg")):
            if not os.path.isfile(src) or os.path.exists(dst):
                continue
            try:
                os.link(src, dst)
            except OSError:
                try:
                    shutil.copy2(src, dst)
                except OSError:
                    if dst == output_path:
                        return None
        _remember_render_key(output_path, key)
        return source
    return None


def _check_smart_skip_signature(sig_path, filename, video_path, no_sig_message):
    """item: smart re-encode skip - הלוגיקה המשותפת של "יש sig_path מתאים
    לבדוק, מה עושים" (process_video קורא לזה משני מקומות - מסלול רגיל דרך
    output_path, ומסלול --number-videos דרך זהות יציבה, ראו שם). no_sig_message
    מאפשר לקורא לנסח בדיוק את המקרה "אין sig_path בכלל" לפי ההקשר שלו (למשל
    'יש פלט קודם אבל בלי sig' לעומת 'אין חתימה שמורה בכלל' עם מספור). True אם
    יש לדלג, False אם צריך רינדור מלא - מדפיס בעצמו את הודעת ה-[INFO]/[SKIP]
    המתאימה בכל מקרה, הקורא לא צריך."""
    if not os.path.exists(sig_path):
        print(no_sig_message)
        sys.stdout.flush()
        return False
    current_signature = _compute_current_signature(video_path)
    stored_signature = None
    if current_signature is not None:
        try:
            with open(sig_path, "r", encoding="utf-8") as f:
                stored_signature = json.load(f).get("signature")
        except (OSError, ValueError):
            stored_signature = None
    if current_signature is not None and current_signature == stored_signature:
        print(f"[SKIP] {filename}: כבר קיים פלט מריצה קודמת לאותו קובץ מקור (בלי קשר להגדרות הריצה הנוכחית) - מדלג. השתמש בדגל --force כדי לרנדר מחדש עם ההגדרות הנוכחיות בכל זאת.")
        sys.stdout.flush()
        return True
    if current_signature is None:
        print(f"[INFO] {filename}: לא הצלחתי לקרוא את קובץ המקור כדי לחשב חתימה - מריץ רינדור מלא (לא לוקח סיכון של דילוג שגוי).")
    else:
        print(f"[INFO] {filename}: קובץ המקור השתנה מאז הרינדור האחרון (mtime/גודל שונים מהחתימה השמורה) - לא מדלג, מריץ רינדור מלא.")
    sys.stdout.flush()
    return False


# item: --parallel - process_video יכול לרוץ מכמה threads בבת-אחת (כל אחד עם
# תת-תהליך ffmpeg משלו), אז עדכוני results (dict משותף) חייבים lock מפורש -
# "+=" על dict אינו אטומי מובטח בפייתון (load+add+store, כמה bytecodes).
RESULTS_LOCK = threading.Lock()


def _bump(results, key):
    with RESULTS_LOCK:
        results[key] += 1


# item: פאנל תוצאות בסוף ריצה (עורך-העל בווב, גל 4 של 102-ההצעות) - "run manifest"
# לכל ריצה: כל קובץ עם הסטטוס שלו (נוצר/דולג/נכשל + סיבה/זמן/גודל/נתיב-פלט),
# נכתב כקובץ JSON תחת workspace/.cache/run_manifests/ ונתיבו מצורף ל-RESULT - בניגוד
# ל-results["files"] (רק עם --export-report ורק לקבצים שנוצרו), זה תמיד פעיל
# וכולל גם כשלים/דילוגים - בדיוק מה שצריך כדי "להריץ שוב רק את הנכשלים".
RUN_MANIFESTS_DIR = os.path.join(WORKSPACE_ROOT, ".cache", "run_manifests")  # = web_app.RUN_MANIFESTS_DIR
MAX_RUN_MANIFESTS = 300
_RUN_MANIFEST_FILES = []


def _manifest_record(filename, status, **extra):
    record = {"source": filename, "status": status}
    record.update({k: v for k, v in extra.items() if v is not None})
    with RESULTS_LOCK:
        _RUN_MANIFEST_FILES.append(record)


def _file_failed(filename, detail):
    """כשל בקובץ: התראה פר-קובץ (אם הופעלה) + רשומה ב-run manifest."""
    _manifest_record(filename, "error", reason=detail)
    maybe_notify_per_file(filename, success=False, detail=detail)


def write_run_manifest(mode, results, started_at_iso, output_path=None):
    """כותב את ה-manifest של הריצה ומחזיר את נתיבו (או None על כשל - לא קריטי,
    הרינדור עצמו כבר הסתיים). שומר רק את MAX_RUN_MANIFESTS האחרונים."""
    try:
        os.makedirs(RUN_MANIFESTS_DIR, exist_ok=True)
        existing = sorted(n for n in os.listdir(RUN_MANIFESTS_DIR) if n.endswith(".json"))
        for old in existing[:max(0, len(existing) - MAX_RUN_MANIFESTS + 1)]:
            try:
                os.remove(os.path.join(RUN_MANIFESTS_DIR, old))  # safe: this script's own old run manifests under workspace/.cache/run_manifests/, never user data
            except OSError:
                pass
        path = os.path.join(RUN_MANIFESTS_DIR, f"{time.strftime('%Y%m%d_%H%M%S')}_{os.getpid()}.json")
        counts = {k: results.get(k, 0) for k in ("files_created", "skipped", "errors", "valid", "invalid")}
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "input_dir": INPUT_DIR, "output_dir": os.path.dirname(output_path) if output_path else OUTPUT_DIR,
                "mode": mode, "started_at": started_at_iso, "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "codec": CODEC, "vertical": VERTICAL, "args": sys.argv[1:], "counts": counts,
                "elapsed_seconds": results.get("elapsed_seconds"), "files": list(_RUN_MANIFEST_FILES),
            }, f, ensure_ascii=False, indent=2)
        return path
    except OSError as e:
        print(f"[WARNING] כתיבת קובץ תוצאות הריצה נכשלה (לא משפיע על הפלט): {e}")
        return None


def _record_file(results, record):
    """item: ייצוא דוח קידוד - מוסיף רשומת-קובץ ל-results["files"] (אותו lock
    כמו _bump, מריצה מקבילה עם --parallel). לא-קריטי אם המפתח "files" בכלל
    לא קיים ב-results (למשל --preview-only) - no-op בשקט, כדי שלא נכשל על
    דיווח סטטיסטיקה כשהריצה עצמה בכלל לא ביקשה דוח."""
    with RESULTS_LOCK:
        if "files" in results:
            results["files"].append(record)


# item: מספור סרטונים - lock נפרד מ-RESULTS_LOCK (לא קשור לתוצאות-ריצה,
# תיאום גישה לקובץ המונה עצמו) - _current_number מאותחל lazily (None) כדי
# שהקריאה הראשונה בלבד תפנה בפועל ל-get_next_number (I/O), לא כל קריאה.
# _run_start_number/_max_success_number קיימים כדי ש-persist_final_counter_value
# (בסוף main()) יוכל "להחזיר למחזור" מספרים שהוקצו בריצה הזו אבל לא נוצלו
# בפועל בקובץ-פלט אמיתי (כשל/דילוג) - ראו שם את התיעוד המלא.
_NUMBER_LOCK = threading.Lock()
_current_number = {"value": None}
_run_start_number = {"value": None}
_max_success_number = {"value": None}


def _reserve_next_number():
    """מקצה ומשמר (utils/video/video_editor_counter.py) את המספר הבא באופן אטומי -
    קריטי עם --parallel (כמה threads יכולים לקרוא לפונקציה הזו בו-זמנית):
    בלי הנעילה, שני threads יכולים לקבל את אותו מספר. נשמר לדיסק *מיד* אחרי
    ההקצאה (לא רק בהצלחת רינדור) - זו עדיין רק רשת-ביטחון למקרה של קריסה/
    הריגה-חיצונית *באמצע* הבאצ' (לא מגיעה כלל לסוף main()), כדי שריצה כזו
    לעולם לא תגרום להקצאה כפולה של אותו מספר בריצה הבאה. בסיום תקין (אפילו
    עם כשלים חלקיים) persist_final_counter_value() מתקן את הערך שנשמר כאן
    כך שישקף רק מספרים שבאמת נוצלו בהצלחה - לא משאיר את זה כאן לצמיתות."""
    with _NUMBER_LOCK:
        if _current_number["value"] is None:
            _current_number["value"] = get_next_number(start=NUMBER_START or 1)
            _run_start_number["value"] = _current_number["value"]
        number = _current_number["value"]
        _current_number["value"] = number + 1
        save_number(_current_number["value"])
    return number


def _mark_number_used_successfully(number):
    """נקרא מ-process_video אחרי הצלחה מוכחת (item: מספור סרטונים - לא לבזבז
    מספרים על כשלים) - עוקב אחרי המספר הגבוה ביותר שבאמת יש לו קובץ-פלט,
    כדי ש-persist_final_counter_value יוכל להתעלם ממספרים שהוקצו לקבצים
    שנכשלו (בלי קשר לסדר הסיום בפועל תחת --parallel)."""
    with _NUMBER_LOCK:
        if _max_success_number["value"] is None or number > _max_success_number["value"]:
            _max_success_number["value"] = number


def persist_final_counter_value():
    """item: מספור סרטונים - נקרא פעם אחת מ-main(), בסוף הבאצ' (גם אם עם
    כשלים חלקיים, דרך finally - ראו main()): מתקן את המונה שנשמר בדיסק כך
    שישקף רק מספרים שבאמת נוצל עליהם קובץ-פלט בהצלחה, במקום כל מספר שהוקצה
    (ראו _reserve_next_number לגבי רשת-הביטחון למקרה של קריסה/הריגה-חיצונית
    שלא מגיעה לכאן בכלל - שם הערך הגולמי-שהוקצה נשאר, במחיר לא-נמנע). קובץ
    שנכשל "מוחזר למחזור" - הריצה הבאה תמשיך מהמספר שבאמת נוצל, לא תדלג עליו.
    אם אף מספר לא נוצל בהצלחה כלל, חוזר לנקודת ההתחלה של הריצה הזו עצמה
    (לא של כל הזמנים - ריצות קודמות שהצליחו כבר לא נוגעות). לא עושה כלום
    (מחזיר None) אם לא הוקצה שום מספר בריצה הזו. מחזיר את הערך שנשמר בפועל
    אם תוקן (הוקטן), אחרת None."""
    with _NUMBER_LOCK:
        if _current_number["value"] is None:
            return None
        target = (_max_success_number["value"] + 1) if _max_success_number["value"] is not None else _run_start_number["value"]
        if target < _current_number["value"]:
            save_number(target)
            return target
        return None


# ---------- גל 48: process_video על אובייקט הגדרות ----------
# כל מה ש-process_video קורא מהגלובלים של הריצה (הערכים אחרי ניתוח הדגלים וההמרות שלמעלה) - באובייקט אחד,
# RENDER_CONFIG, שנבנה כאן אחרי שכל הגלובלים כבר נקבעו (שום דבר מהם לא משתנה בזמן ריצה). process_video מקבל
# cfg (ברירת מחדל: RENDER_CONFIG) וקורא רק ממנו - קובץ אחד יכול לקבל הגדרות אחרות (cfg.replace(...)) בלי לגעת
# בגלובלים המשותפים. המעבר נבדק מול "פקודות זהב" (tests/studio/test_video_editor_golden.py): פקודות ffmpeg זהות
# בייט-בבייט ל-48 צירופי דגלים, מה שמבטיח סרטונים זהים - בלי לרנדר.
RENDER_CONFIG_NAMES = (
    "AUDIO_FX_FILTERS", "AUDIO_TRACK", "AUTO_LEVELS", "BLUR_BACKGROUND", "CAPTIONS", "CAPTION_COLOR",
    "CAPTION_FONT", "CAPTION_FONT_SIZE", "CAPTION_MAX_CHARS", "CAPTION_POSITION", "CHROMAKEY", "CHROMAKEY_BG_COLOR", "CHROMAKEY_BLEND",
    "CHROMAKEY_COLOR", "CHROMAKEY_SIMILARITY", "CODEC", "CODEC_QUALITY", "CONTAINER", "DEINTERLACE", "DENOISE",
    "DENOISE_FILTER_OVERRIDE", "EFFECTIVE_OUTPUT_TEMPLATE", "EFFORT", "EQ_FILTER", "FADE_IN_SECONDS",
    "FADE_OUT_SECONDS", "FFMPEG_EXE", "FIT", "FORCE", "FRAME_BORDER", "FRAME_RADIUS", "GPU_HYBRID", "HWACCEL_DECODE", "KEEP_AUDIO",
    "KEN_BURNS", "LAYERS", "LOUDNORM", "LOUDNORM_FILTER_OVERRIDE", "LUT_INTENSITY", "LUT_PATH", "NOISE_GATE",
    "NO_SUFFIX", "NUMBER_VIDEOS", "NVENC_SEMAPHORE", "ORIENTATION_FILTERS", "OUTPUT_FPS_OVERRIDE", "PAD_COLOR",
    "PIP_AUDIO", "PIP_DUCK", "PIP_OPACITY", "PIP_PATH", "PRESERVE_RESOLUTION", "PREVIEW_CLIP_SECONDS",
    "PREVIEW_FRAME_SECONDS", "PROGRESS_BAR", "REMOVE_RANGES", "REMOVE_WATERMARK_POSITION",
    "REMOVE_WATERMARK_REGION", "REPLACE_AUDIO_PATH", "RESOLUTION_PRESET", "ROTATE", "SCALE_ALGO", "SHARPEN",
    "SHARPEN_FILTER_OVERRIDE", "SMOOTH_FPS", "SPEED", "TARGET_SECONDS", "TARGET_SIZE_MB", "TEXT_COLOR",
    "TEXT_FILE_PATH", "TEXT_FONT", "TEXT_FONT_SIZE", "TEXT_POSITION", "TONEMAP_FILTER_OVERRIDE", "TRIM_DURATION",
    "TRIM_SILENCE", "TRIM_START", "USE_HWACCEL", "VALIDATE_ONLY", "VARIANTS", "VIGNETTE_FILTER",
    "WATERMARK_MOVE_SECONDS", "WATERMARK_OPACITY", "WATERMARK_PATH", "WATERMARK_POSITION",
    "WATERMARK_POSITION_VERTICAL", "WATERMARK_SCALE",
)


class RenderConfig(SimpleNamespace):
    """ההגדרות של רינדור - בשמות הגלובלים (CODEC, WATERMARK_PATH...), ועוד HWACCEL_REQUESTED (הדגל --hwaccel
    כמו שנכתב) ו-SETTINGS (הדגלים הגולמיים, utils/video/video_editor_settings.py)."""

    def replace(self, **changes):
        """עותק עם שינויים - לקובץ אחד, בלי לגעת בהגדרות של שאר הקבצים."""
        unknown = sorted(set(changes) - set(vars(self)))
        if unknown:
            raise AttributeError(f"הגדרות לא מוכרות: {unknown}")
        return RenderConfig(**{**vars(self), **changes})


RENDER_CONFIG = RenderConfig(**{name: globals()[name] for name in RENDER_CONFIG_NAMES}, HWACCEL_REQUESTED=args.hwaccel, SETTINGS=SETTINGS)


def process_video(video_path, results, output_dir, overrides=None, variant=None, cfg=None):
    # item: ממשק batch לדריסת דגלים פר-קובץ - overrides (מ-BATCH_OVERRIDES,
    # לפי שם-הקובץ) נפתר למשתנים מקומיים *כאן*, לא כדריסה זמנית של ה-global-ים
    # (WATERMARK_PATH וכו') - process_video רץ גם על threads נפרדים ממש
    # (--parallel, run_tasks למטה), אז דריסת global משותף הייתה
    # גורמת למירוץ-נתונים אמיתי בין קבצים שרצים בו-זמנית (קובץ א' רואה את
    # הדריסה של קובץ ב', תלוי בתזמון) - משתנים מקומיים בטוחים-ל-thread מטבעם.
    # גל 48: כל ההגדרות של הרינדור מגיעות מ-cfg (RenderConfig) ולא מהגלובלים - ברירת המחדל היא
    # RENDER_CONFIG של הריצה; אפשר להעביר אחר לקובץ אחד בלי לגעת בגלובלים (בטוח גם תחת --parallel).
    cfg = cfg or RENDER_CONFIG
    overrides = overrides or {}
    # item: פלט כפול/יחסי-רוחב (גל 7) - כיוון ומידות לכל משימה (מקומי, thread-safe
    # תחת --parallel), לא ה-VERTICAL הגלובלי.
    variant = variant or cfg.VARIANTS[0]
    vertical = variant["vertical"]
    effective_watermark_path = overrides.get("watermark_path", cfg.WATERMARK_PATH)
    effective_watermark_position = overrides.get("watermark_position", cfg.WATERMARK_POSITION)
    if variant["orientation"] == "vertical" and cfg.WATERMARK_POSITION_VERTICAL and "watermark_position" not in overrides:
        effective_watermark_position = cfg.WATERMARK_POSITION_VERTICAL  # item: מיקום watermark שונה לאנכי
    effective_watermark_opacity = overrides.get("watermark_opacity", cfg.WATERMARK_OPACITY)
    effective_watermark_scale = overrides.get("watermark_scale", cfg.WATERMARK_SCALE)
    # גל 30 (עריכת קליפ): לוגו שנגרר בנגן רק לקובץ הזה - מרכז משלו; מיקום פינה מפורש לקובץ
    # מבטל את מרכז הגרירה של כל הקבצים
    effective_watermark_center = None
    if "watermark_x" in overrides and "watermark_y" in overrides:
        effective_watermark_center = (float(overrides["watermark_x"]), float(overrides["watermark_y"]))
    elif "watermark_position" in overrides:
        effective_watermark_center = False
    effective_trim_start = max(0.0, overrides.get("trim_start", cfg.TRIM_START))
    effective_trim_duration = overrides.get("trim_duration", cfg.TRIM_DURATION)
    # גל 12 (עריכת קליפ): טווחים לקובץ הזה קובעים את כל הזמן שלו - בלי החיתוך/זיהוי-השקט
    # בקצוות של המתכון (הטווחים כבר כוללים את ההתחלה/הסוף, בזמני המקור).
    clip_time_edit = any(key in overrides for key in ("trim_start", "trim_duration", "remove_ranges"))
    effective_remove_ranges = cfg.REMOVE_RANGES
    if "remove_ranges" in overrides:
        effective_remove_ranges = [(float(start), float(end)) for start, end in overrides["remove_ranges"]]
        if "trim_start" not in overrides:
            effective_trim_start = 0.0
        if "trim_duration" not in overrides:
            effective_trim_duration = None
    elif clip_time_edit:
        effective_remove_ranges = []  # חיתוך-קליפ בלי טווחים: טווחי המתכון (בזמני המקור) לא מתיישבים עם ה-ss שלו

    # item: ייצוא דוח קידוד - נקודת ההתחלה לחישוב render_seconds פר-קובץ
    # (RESULT: {"files": [...]}) - כוללת בכוונה גם את בדיקת הדילוג-החכם/probe
    # שקודמים לרינדור עצמו, לא רק את שורת ה-ffmpeg, כדי לא לצטרך להעביר עוד
    # stopwatch נפרד לאורך הפונקציה - הקובץ הזה יגיע לדוח רק אם הוא באמת נוצר,
    # ואז רוב הזמן הזה הוא בכל מקרה זמן הרינדור האמיתי.
    file_start_time = time.monotonic()
    filename = os.path.basename(video_path)
    base_name = os.path.splitext(filename)[0]
    # item: מספור סרטונים - עם מספור, שם-קובץ הפלט משתנה בכל ריצה (המונה
    # מתקדם) - אי אפשר להשתמש בקיום output_path כדי לזהות "כבר קיים פלט קודם
    # לקובץ-המקור הזה" (output_path החדש לעולם לא זהה לריצה קודמת). בלי
    # ההבחנה הזו, restart על תיקייה שכבר עובדה בהצלחה בעבר היה מרנדר ומספר
    # מחדש את כל הקבצים מאפס בכל הפעלה נוספת - זו הייתה הסיבה האמיתית שהמונה
    # "טס" הרבה מעל למספר ההתחלתי שהוגדר בפרופיל אחרי כמה הפעלות/הפסקות,
    # לא רק כשלים. לכן, כשמספור פעיל (ולא --validate-only, שלא מרנדר בכלל),
    # בודקים דילוג-חכם *לפני* הקצאת מספר - לפי .sig.json במיקום יציב, מבוסס
    # רק על base_name/orientation/container (בלי מספר, בלי NO_SUFFIX/תבנית-
    # הפלט - אלה יכולים להשתנות בין ריצות בלי "לשבור" את הזיהוי של קובץ-המקור,
    # אותו עיקרון בדיוק כמו _compute_current_signature). דילוג לא שורף מספר
    # בכלל - רק קובץ שבאמת עומד לרונדר מקבל אחד.
    preview_mode = cfg.PREVIEW_FRAME_SECONDS is not None
    numbering_active = cfg.NUMBER_VIDEOS and not cfg.VALIDATE_ONLY and not preview_mode
    if numbering_active:
        stable_identity_filename = resolve_output_filename(base_name, vertical, container=cfg.CONTAINER, orientation=variant["orientation"])
        sig_path = resolve_sig_path(os.path.join(output_dir, stable_identity_filename))
        if not cfg.FORCE and _check_smart_skip_signature(
            sig_path, filename, video_path,
            no_sig_message=f"[INFO] {filename}: אין חתימה שמורה מריצה קודמת (item: מספור סרטונים) - מריץ רינדור מלא.",
        ):
            _bump(results, "skipped")
            _manifest_record(filename, "skipped", reason="כבר קיים פלט מריצה קודמת (--force כדי לרנדר מחדש)")
            return
        reserved_number = _reserve_next_number()
    else:
        reserved_number = 0 if cfg.NUMBER_VIDEOS else None  # NUMBER_VIDEOS כאן נכון רק יחד עם VALIDATE_ONLY

    output_filename = resolve_output_filename(
        base_name, vertical, no_suffix=cfg.NO_SUFFIX, container=cfg.CONTAINER, template=cfg.EFFECTIVE_OUTPUT_TEMPLATE or None,
        codec=cfg.CODEC, number=reserved_number, orientation=variant["orientation"],
    )
    output_path = os.path.join(output_dir, output_filename)
    if not numbering_active:
        # .sig.json - סייד-קאר קטן (item: smart re-encode skip) - לא קובץ מרכזי/
        # DB, כדי שיישאר תקף גם אם מעתיקים/מעבירים את תיקיית הפלט כמות שהיא.
        # תת-תיקיית SIG_SUBDIR נפרדת (item: תיקיית SIG נפרדת) - לא ליד הפלט
        # עצמו - כדי שתיקיית הסרטונים תישאר נקייה, רק וידאו (ותמונות ממוזערות).
        sig_path = resolve_sig_path(output_path)
    # קובץ ביניים (item: פלט אטומי - resume batch שנקטע) - ffmpeg כותב לכאן,
    # לא ל-output_path הסופי - os.replace() (אטומי על אותה מערכת קבצים) מעביר
    # אותו ל-output_path רק אחרי הצלחה מוכחת. כך קריסה/הריגה באמצע רינדור לא
    # משאירה קובץ חצי-כתוב במקום שבו תוצר גמור אמור להיות - ריצה חוזרת רואה
    # "אין פלט קודם" (לא קובץ שבור שנראה כמו פלט תקין) ומרנדרת מחדש בביטחון.
    partial_output_path = output_path + ".partial" + os.path.splitext(output_path)[1]

    if not cfg.VALIDATE_ONLY and not preview_mode and os.path.exists(partial_output_path):
        try:
            os.remove(partial_output_path)  # safe: stray leftover from a previous crashed/interrupted render of this exact file (this script's own naming convention), not user data
        except OSError:
            pass

    if cfg.VALIDATE_ONLY or preview_mode:
        pass  # --validate-only/--preview-frame בודקים כל קובץ בכל מקרה - הדילוג-החכם לא רלוונטי כאן.
    # לוגים מפורטים (item: "why didn't it skip") - בלי זה, לחקור מקרה של "זה
    # אמור היה לדלג ולא דילג" דורש לחפור בזמני-שינוי של קבצים בדיסק בדיעבד. עם
    # זה, הסיבה המדויקת (--force / אין פלט קודם / אין sig / קובץ המקור השתנה)
    # מודפסת מיד בלוג הריצה עצמה.
    elif cfg.FORCE:
        print(f"[INFO] {filename}: הופעל --force - מדלג על בדיקת הדילוג-החכם ומרנדר מחדש.")
        sys.stdout.flush()
        snapshot_previous_output_if_forcing(output_path)
    elif numbering_active:
        pass  # דילוג-חכם כבר הוכרע מעל (לפני הקצאת המספר, לפי חתימה יציבה) - אין טעם/צורך לבדוק שוב לפי output_path (תמיד "חדש" עם מספור).
    elif not os.path.exists(output_path):
        print(f"[INFO] {filename}: אין פלט קודם ({os.path.basename(output_path)}) - מריץ רינדור מלא.")
        sys.stdout.flush()
    elif _check_smart_skip_signature(
        sig_path, filename, video_path,
        no_sig_message=f"[INFO] {filename}: יש פלט קודם אבל בלי קובץ .sig.json שלו (item: smart re-encode skip) - אי אפשר להשוות, מריץ רינדור מלא.",
    ):
        _bump(results, "skipped")
        _manifest_record(filename, "skipped", reason="כבר קיים פלט מריצה קודמת (--force כדי לרנדר מחדש)", output=output_path)
        return

    if not cfg.VALIDATE_ONLY and not preview_mode:
        required_bytes = estimate_required_bytes(video_path)
        if not has_enough_disk_space(output_dir, required_bytes):
            print(f"[ERROR] שטח פנוי לא מספיק ב-{output_dir} עבור {filename} - מדלג (במקום להיכשל באמצע רינדור).")
            _bump(results, "errors")
            _file_failed(filename, "שטח דיסק לא מספיק")
            return

    render_key = None if (numbering_active or cfg.VALIDATE_ONLY or preview_mode) else _render_key(video_path, overrides)
    reused_from = _reuse_identical_target_render(output_path, output_dir, variant, render_key)
    if reused_from:
        print(f"[APPROVED] נוצר: {os.path.basename(output_path)} - מקושר מ-{os.path.basename(os.path.dirname(reused_from))}/ (אותן הגדרות בדיוק, בלי רינדור נוסף)")
        _bump(results, "files_created")
        current_signature = _compute_current_signature(video_path)
        if current_signature is not None:
            try:
                os.makedirs(os.path.dirname(sig_path), exist_ok=True)
                with open(sig_path, "w", encoding="utf-8") as f:
                    json.dump({"signature": current_signature}, f)
            except OSError:
                pass
        _manifest_record(filename, "created", output=output_path, output_size_mb=round(os.path.getsize(output_path) / (1024 ** 2), 2),
                         variant=variant["orientation"], render_seconds=round(time.monotonic() - file_start_time, 1), reused_from=reused_from)
        maybe_notify_per_file(filename, success=True)
        return

    probe_info = probe_video(video_path)
    duration = probe_info["duration"]
    if not duration:
        print(f"[ERROR] לא הצלחתי לקרוא את אורך {filename} - מדלג.")
        _bump(results, "errors")
        _file_failed(filename, "לא הצלחתי לקרוא את אורך הקובץ")
        return

    # שימור FPS מקורי (item) - per-file, לא גלובלי לכל הריצה: קבצים שונים
    # באותה תיקיית batch יכולים להגיע בקצבים מקוריים שונים.
    output_fps_str, output_fps_value = resolve_output_fps(cfg.OUTPUT_FPS_OVERRIDE, probe_info.get("fps"))
    if not cfg.OUTPUT_FPS_OVERRIDE and not probe_info.get("fps"):
        print(f"[WARNING] {filename}: לא הצלחתי לזהות את קצב הפריימים המקורי - נופל חזרה ל-{output_fps_str}fps.")
        sys.stdout.flush()

    # שימור הגדרות HDR (item) - HDR מלא (10-bit + מטא-דאטת צבע) רק עם
    # --codec hevc/av1 (NVENC תומך ב-10-bit; h264/libx264 בפרויקט הזה לא).
    # מקור HDR עם --codec h264 (ברירת המחדל) עובר tone-mapping אמיתי ל-SDR
    # במקום להיכנס בשקט לקידוד SDR רגיל (שמפיק תמונה שטופה/דהויה - הבאג
    # שהתגלית הזו נועדה למנוע).
    is_hdr = is_hdr_source(probe_info.get("color_transfer"))
    hdr_passthrough = False
    tonemap_to_sdr = False
    use_hwaccel_for_file = cfg.USE_HWACCEL
    # item: פענוח מואץ-GPU בלי NVENC - גם הוא מתעלם ממקור HDR, אותה סיבה
    # בדיוק כמו use_hwaccel_for_file (נתיב ה-CUDA תומך רק ב-8-bit) - וגם כי
    # tone-mapping נכון (הענף else למטה) צריך לרוץ על הפריים המפוענח המלא
    # (bit-depth/מטא-דאטת HDR אמיתיים), לא על גרסה שכבר ירדה ל-nv12 8-bit
    # דרך hwdownload.
    use_hwaccel_decode_for_file = cfg.HWACCEL_DECODE
    if is_hdr:
        if use_hwaccel_decode_for_file:
            use_hwaccel_decode_for_file = False
            print(f"[INFO] {filename}: מקור HDR מזוהה - מתעלם מ---hwaccel-decode לקובץ הזה (נתיב ה-CUDA תומך רק ב-8-bit, היה משבש שימור HDR/tone-mapping).")
        if cfg.CODEC in ("hevc", "av1"):
            hdr_passthrough = True
            if use_hwaccel_for_file:
                use_hwaccel_for_file = False
                print(f"[INFO] {filename}: מקור HDR מזוהה - מתעלם מ---hwaccel לקובץ הזה כדי לשמר HDR מלא (נתיב ה-CUDA הקיים תומך רק ב-8-bit).")
            print(f"[INFO] {filename}: מקור HDR מזוהה ({probe_info.get('color_transfer')}) - שומר HDR מלא בפלט (10-bit + מטא-דאטת צבע).")
        else:
            tonemap_to_sdr = True
            print(f"[INFO] {filename}: מקור HDR מזוהה אבל --codec {cfg.CODEC} לא תומך בשימור HDR (דורש hevc/av1) - ממיר ל-SDR עם tone-mapping נכון במקום תמונה שטופה.")
        sys.stdout.flush()
    elif is_high_bit_depth(probe_info.get("pix_fmt")) and (use_hwaccel_for_file or use_hwaccel_decode_for_file):
        # 10/12 ביט גם בלי HDR - אותה סיבה: נתיב ה-CUDA 8 ביט בלבד, ו-hwdownload ל-nv12 נכשל מיד (הקובץ לא רונדר בכלל)
        use_hwaccel_for_file = use_hwaccel_decode_for_file = False
        print(f"[INFO] {filename}: מקור {probe_info.get('pix_fmt')} (יותר מ-8 ביט) - מפענח ב-CPU (נתיב ה-CUDA תומך רק ב-8-bit).")
        sys.stdout.flush()
    if preview_mode:
        # תצוגה מקדימה: תמיד CPU (פריים PNG, לא קידוד NVENC), ותמיד SDR - היא
        # מוצגת על מסך רגיל בדפדפן, HDR גולמי היה נראה שטוף/דהוי.
        use_hwaccel_for_file = False
        use_hwaccel_decode_for_file = False
        if is_hdr:
            hdr_passthrough = False
            tonemap_to_sdr = True

    # trim range / auto-trim silence (items) - שני המקורות (חיתוך מפורש או
    # שקט שזוהה אוטומטית) מתנרמלים דרך אותה resolve_trim_bounds אחת, כדי
    # שההצמדה (clamp) לגבולות הקובץ בפועל תהיה זהה בשני המסלולים.
    raw_trim_start = 0.0
    raw_trim_duration = None
    if cfg.TRIM_SILENCE and not clip_time_edit:
        raw_trim_start, raw_trim_duration = detect_silence_trim_bounds(video_path, duration)
    elif effective_trim_start > 0.0 or effective_trim_duration is not None:
        raw_trim_start, raw_trim_duration = effective_trim_start, effective_trim_duration

    trim_start_seconds, duration = resolve_trim_bounds(duration, raw_trim_start, raw_trim_duration)
    if trim_start_seconds > 0.0 or raw_trim_duration is not None:
        if duration <= 0:
            print(f"[ERROR] טווח החיתוך עבור {filename} לא משאיר תוכן לעיבוד - מדלג.")
            _bump(results, "errors")
            _file_failed(filename, "טווח החיתוך לא משאיר תוכן")
            return
        print(f"[INFO] {filename}: חיתוך {trim_start_seconds:.1f}s מההתחלה, אורך מעובד: {duration:.1f}s.")
        sys.stdout.flush()

    # הסרת שקט באמצע הקובץ (item) - מזהה על הקובץ *כמות שהוא* (לפני חיתוך;
    # REMOVE_MID_SILENCE וחיתוך מפורש/שקט-בקצוות כבר נדחים הדדית למעלה, אז
    # אין כאן התנגשות טווחי-זמן בין השניים). item: חיתוך כמה טווחים -
    # REMOVE_RANGES (מפורש-ע"י-משתמש) מתלכד לאותה רשימה בדיוק - build_silence_removal_filters
    # לא יודע/צריך לדעת מאיפה הגיע כל טווח, רק מסיר את כולם יחד מסונכרן.
    auto_silence_intervals = detect_all_silence_intervals(video_path, duration)
    silence_removal_intervals = auto_silence_intervals + list(effective_remove_ranges)
    removed_silence_seconds = 0.0
    if silence_removal_intervals:
        removed_silence_seconds = sum(max(0.0, min(end, duration) - max(start, 0.0)) for start, end in silence_removal_intervals)
        removed_silence_seconds = max(0.0, min(removed_silence_seconds, duration))
        if effective_remove_ranges:
            print(f"[INFO] {filename}: {len(silence_removal_intervals)} טווחים יוסרו ({len(auto_silence_intervals)} שקט שזוהה אוטומטית + {len(effective_remove_ranges)} מפורשים) לאורך {removed_silence_seconds:.1f}s - מהווידאו והאודיו יחד.")
        else:
            print(f"[INFO] {filename}: {len(silence_removal_intervals)} טווחי שקט זוהו לאורך {removed_silence_seconds:.1f}s - יוסרו מהווידאו והאודיו יחד.")
        sys.stdout.flush()

    removal_region = None
    if cfg.REMOVE_WATERMARK_POSITION or cfg.REMOVE_WATERMARK_REGION is not None:
        if probe_info["width"] is None or probe_info["height"] is None:
            print(f"[WARNING] לא הצלחתי לקרוא את רזולוציית {filename} - ממשיך בלי מחיקת watermark.")
            sys.stdout.flush()
        else:
            removal_region = resolve_removal_region(probe_info["width"], probe_info["height"])

    speed_factor = None
    setpts_expr = None
    if cfg.TARGET_SECONDS > 0:
        speed_factor = compute_speed_factor(duration, cfg.TARGET_SECONDS)
        if speed_factor is not None:
            setpts_expr = f"setpts=PTS/{speed_factor:.6f}"
            print(f"[INFO] {filename}: {duration:.0f}s -> {cfg.TARGET_SECONDS}s (מהירות פי {speed_factor:.1f})")
        else:
            print(f"[INFO] {filename} כבר קצר מ-{cfg.TARGET_SECONDS} שניות ({duration:.0f}s) - ללא שינוי מהירות.")
        sys.stdout.flush()
    timelapse_active = speed_factor is not None
    if not timelapse_active and abs(cfg.SPEED - 1.0) > 1e-6:
        # item: שינוי מהירות קבוע (0.25x-4x) - אותו מנגנון setpts+atempo כמו טיימלאפס.
        speed_factor = cfg.SPEED
        setpts_expr = f"setpts=PTS/{cfg.SPEED:.6f}"
        print(f"[INFO] {filename}: מהירות x{cfg.SPEED:g}.")
        sys.stdout.flush()

    # item: סיבוב 90/270 מחליף רוחב/גובה - כל מה שתלוי במידות *אחרי* הסיבוב
    # (שימור רזולוציה, דילוג-scale, רקע כרומה-קי) משתמש במידות המסובבות.
    source_width, source_height = probe_info.get("width"), probe_info.get("height")
    if cfg.ROTATE in (90, 270) and source_width and source_height:
        source_width, source_height = source_height, source_width

    if variant["dims"]:
        output_width, output_height = apply_resolution_preset(variant["dims"], cfg.RESOLUTION_PRESET)
    else:
        output_width, output_height = resolve_effective_output_dimensions(
            vertical, cfg.PRESERVE_RESOLUTION, source_width, source_height,
        )
        output_width, output_height = apply_resolution_preset((output_width, output_height), cfg.RESOLUTION_PRESET)
    if cfg.PRESERVE_RESOLUTION and probe_info.get("width") and probe_info.get("height"):
        print(f"[INFO] {filename}: --preserve-resolution - רזולוציית פלט {output_width}x{output_height} (לפי מקור, לא רזולוציה קבועה).")
        sys.stdout.flush()

    crop_variant = (cfg.FIT == "crop") or (cfg.FIT == "auto" and variant["orientation"] in ("vertical", "square"))
    smart_crop_offset = resolve_smart_crop_offset(video_path) if crop_variant else None
    if smart_crop_offset is not None:
        print(f"[INFO] {filename}: smart-crop - היסט קרופ {smart_crop_offset:+.2f} (מ-1.0 שמאלה עד 1.0 ימינה).")
        sys.stdout.flush()
    # item: skip-if-already-correct-orientation - רק בלי --hwaccel (הפריימים
    # שם כבר בפורמט CUDA, fps= בלבד עליהם בלי scale_cuda/hwdownload קודם הוא
    # שילוב לא-מאומת בפרויקט הזה, לא שווה את הסיכון בשביל אופטימיזציה קטנה).
    # יחס-רוחב מותאם / fit מפורש (item: יחסי-רוחב) - שרשרת scale כללית ב-CPU בלבד
    # (שרשראות ה-CUDA קיימות רק ל-16:9/9:16 בהתאמה המקורית).
    custom_geometry = bool(variant["dims"]) or cfg.FIT in ("crop", "pad")
    # סיבוב/מראה, deinterlace ו-eq קיימים רק כפילטרי CPU - עם פייפליין GPU מלא
    # הם היו נבלעים בשקט, אז הסינון עובר ל-CPU (הפענוח נשאר מואץ) במקום.
    # גל 7ב: גם טקסט/fade/שכבות/סרגל/מסגרת/וינייטה/Ken Burns/watermark נודד הם פילטרי
    # CPU בלבד - קודם טקסט/fade עם --hwaccel מלא נכשלו (פילטר תוכנה על פריימי CUDA).
    cpu_only_filters = (
        bool(cfg.ORIENTATION_FILTERS) or cfg.DEINTERLACE or bool(cfg.EQ_FILTER) or bool(cfg.TEXT_FILE_PATH)
        or cfg.FADE_IN_SECONDS > 0 or cfg.FADE_OUT_SECONDS > 0 or bool(cfg.LAYERS) or cfg.PROGRESS_BAR is not None
        or cfg.FRAME_BORDER is not None or bool(cfg.VIGNETTE_FILTER) or cfg.KEN_BURNS > 0 or cfg.WATERMARK_MOVE_SECONDS > 0
    )
    if (custom_geometry or cpu_only_filters) and use_hwaccel_for_file:
        use_hwaccel_for_file = False
        use_hwaccel_decode_for_file = (cfg.HWACCEL_DECODE or cfg.HWACCEL_REQUESTED) and not is_hdr  # HDR: נתיב ה-CUDA 8-bit בלבד
        reason = "יחס-רוחב/fit מותאם" if custom_geometry else "פילטרי CPU (סיבוב/צבע/טקסט/שכבות/fade)"
        print(f"[INFO] {filename}: {reason} - הסינון רץ ב-CPU (פענוח נשאר מואץ).")
        sys.stdout.flush()
    if not use_hwaccel_for_file and not cfg.ORIENTATION_FILTERS and should_skip_scale(source_width, source_height, vertical, target_dimensions=(output_width, output_height)):
        scale_chain = ""
        print(f"[INFO] {filename}: הקלט כבר ב-{output_width}x{output_height} בדיוק - מדלג על שינוי גודל מיותר.")
        sys.stdout.flush()
    elif custom_geometry:
        scale_chain = build_fit_scale_chain(output_width, output_height, cfg.FIT, crop_x_offset=smart_crop_offset, pad_color=cfg.PAD_COLOR)
    else:
        scale_chain = resolve_scale_chain(
            vertical, use_hwaccel=use_hwaccel_for_file, crop_x_offset=smart_crop_offset,
            target_width=output_width, target_height=output_height,
        )
    if not use_hwaccel_for_file:
        scale_chain = apply_pad_color(apply_scale_algorithm(scale_chain, cfg.SCALE_ALGO), cfg.PAD_COLOR)

    watermark_geometry = resolve_watermark_geometry(
        output_width, output_height,
        watermark_path=effective_watermark_path, watermark_position=effective_watermark_position, watermark_scale=effective_watermark_scale,
        custom_center=effective_watermark_center,
    )
    pip_geometry = resolve_pip_geometry(output_width, output_height)

    # ייצוב וידאו (item) - מעבר 1/2 (vidstabdetect) רץ כאן, לפני בניית ה-
    # filter_complex הראשי, כי הוא צריך לרוץ ולסיים ולכתוב את קובץ ה-
    # transforms *לפני* שמעבר 2/2 (vidstabtransform, בתוך filter_complex
    # הראשי) יכול לקרוא אותו.
    stabilize_transform_path = detect_stabilization_transform(video_path)
    if stabilize_transform_path:
        print(f"[INFO] {filename}: ניתוח ייצוב וידאו הושלם - מחיל תיקון בפועל בשלב הרינדור.")
        sys.stdout.flush()

    # item: החלפת פס קול חלופי - אינדקס ה--i בפועל שיוקצה לקובץ האודיו
    # החלופי, לפי אותו סדר קלטים בדיוק שנבנה למטה (video -> PiP -> watermark
    # -> replace-audio) - חייב להישאר מסונכרן עם סדר ה--i-ים שם.
    replace_audio_input_index = None
    if cfg.REPLACE_AUDIO_PATH:
        replace_audio_input_index = 1 + (1 if pip_geometry else 0) + (1 if watermark_geometry else 0)

    if timelapse_active:
        output_seconds = float(cfg.TARGET_SECONDS)
    else:
        output_seconds = max(0.0, (duration - removed_silence_seconds) / (speed_factor or 1.0))

    # גל 7ב: שכבות לקובץ הזה - קובצי-טקסט (טיימר תלוי באורך הפלט, חותמת-זמן בזמן
    # ההקלטה של הקובץ) בתיקייה זמנית, ותמונות כקלטי -i אחרי כל השאר.
    file_layers = [dict(layer) for layer in cfg.LAYERS]
    if overrides.get("layers"):  # גל 12: שכבות לקובץ הזה בלבד (עריכת קליפ), מעל שכבות המתכון
        file_layers += [dict(layer) for layer in sanitize_layers(overrides["layers"])]
    layer_text_files = {}
    layer_image_inputs = {}
    layer_input_args = []  # גל 26: לכל שכבת תמונה/וידאו - הארגומנטים של ה--i שלה, לפי הסדר
    if file_layers:
        fill_filename_layers(file_layers, video_path)
        for layer in file_layers:
            if layer["type"] == "timestamp" and layer.get("epoch") is None:
                try:
                    source_seconds = float(probe_info.get("duration") or 0.0)
                    layer["epoch"] = os.path.getmtime(video_path) - source_seconds + trim_start_seconds
                except OSError:
                    layer["epoch"] = time.time()
        layers_dir = tempfile.mkdtemp(prefix="ve_layers_")
        atexit.register(shutil.rmtree, layers_dir, True)
        layer_text_files = write_layer_text_files(file_layers, layers_dir, output_seconds)
        next_input = 1 + (1 if pip_geometry else 0) + (1 if watermark_geometry else 0) + (1 if cfg.REPLACE_AUDIO_PATH else 0)
        for index, layer in enumerate(file_layers):
            if layer["type"] == "image":
                layer_image_inputs[index] = next_input + len(layer_input_args)
                layer_input_args.append(["-i", layer["path"]])
            elif layer["type"] == "video":
                # גל 26: B-roll - הסוף בזמן הפלט (עד סוף הקליפ או הפלט), ושמע רק אם יש לקליפ
                clip_info = probe_video(layer["path"])
                layer["end"] = video_layer_end(layer, clip_info.get("duration"), output_seconds)
                layer["has_audio"] = bool(clip_info.get("has_audio"))
                if layer["end"] is None:
                    print(f"[WARNING] {filename}: שכבת הווידאו {os.path.basename(layer['path'])} מחוץ לאורך הפלט - מדלג עליה.")
                    sys.stdout.flush()
                    continue
                layer_image_inputs[index] = next_input + len(layer_input_args)
                layer_input_args.append(build_video_layer_input_args(layer))
    watermark_cycle_positions = None
    if cfg.WATERMARK_MOVE_SECONDS > 0 and watermark_geometry:
        corners = [
            resolve_watermark_geometry(output_width, output_height, watermark_path=effective_watermark_path,
                                       watermark_position=corner, watermark_scale=effective_watermark_scale)
            for corner in ("top-left", "top-right", "bottom-right", "bottom-left")
        ]
        watermark_cycle_positions = [(g[2], g[3]) for g in corners if g]
    ken_burns_filter = build_ken_burns_filter(cfg.KEN_BURNS, output_width, output_height, output_fps_str, output_seconds) if cfg.KEN_BURNS > 0 else ""
    pip_audio_input_index = None
    if cfg.PIP_AUDIO and pip_geometry and not preview_mode:
        main_has_audio = bool(cfg.REPLACE_AUDIO_PATH) or probe_info.get("has_audio")
        if main_has_audio and probe_video(cfg.PIP_PATH).get("has_audio"):
            pip_audio_input_index = 1
        else:
            print(f"[INFO] {filename}: --pip-audio מתעלם - לאחד הקבצים (ראשי/PiP) אין פס-קול.")
            sys.stdout.flush()

    # item: תצוגה מקדימה מלאה - כתובית-לדוגמה בעיצוב שנבחר (אותו force_style בדיוק
    # כמו השריפה האמיתית, utils/media/captions.py) במקום תמלול Whisper מלא.
    preview_subtitle_filter = None
    preview_srt_path = None
    if preview_mode and cfg.CAPTIONS:
        from utils.media.captions import build_caption_force_style, escape_subtitles_path, wrap_caption_text, write_sample_srt
        srt_fd, preview_srt_path = tempfile.mkstemp(suffix=".srt", prefix="ve_preview_caption_")
        os.close(srt_fd)
        write_sample_srt(preview_srt_path, wrap_caption_text("כתובית לדוגמה\nSample caption", cfg.CAPTION_MAX_CHARS), output_seconds + 5)
        style = build_caption_force_style(cfg.CAPTION_FONT, cfg.CAPTION_FONT_SIZE, cfg.CAPTION_COLOR, cfg.CAPTION_POSITION)
        preview_subtitle_filter = f"subtitles='{escape_subtitles_path(preview_srt_path)}':force_style='{style}'"

    gpu_prefix, orientation_on_gpu, deinterlace_on_gpu = [], False, False
    if use_hwaccel_decode_for_file and cfg.GPU_HYBRID and not preview_mode:
        gpu_prefix, orientation_on_gpu, deinterlace_on_gpu = build_hybrid_gpu_prefix(
            cfg.ORIENTATION_FILTERS, cfg.DEINTERLACE, source_width, source_height, output_width, output_height,
            allow_prescale=bool(scale_chain) and not (removal_region or stabilize_transform_path or cfg.CHROMAKEY or cfg.BLUR_BACKGROUND),
            available_filters=available_cuda_filters(),
        )
        if gpu_prefix:
            print(f"[INFO] {filename}: GPU היברידי - {', '.join(f.split('=')[0] for f in gpu_prefix)} על ה-GPU לפני הסינון ב-CPU.")
            sys.stdout.flush()
    filter_complex, maps = build_edit_filter_complex(
        scale_chain, output_fps_str, setpts_expr=setpts_expr, watermark_geometry=watermark_geometry,
        watermark_opacity=effective_watermark_opacity, removal_region=removal_region, speed_factor=speed_factor,
        keep_audio=cfg.KEEP_AUDIO and (not preview_mode or cfg.PREVIEW_CLIP_SECONDS > 0), loudnorm=cfg.LOUDNORM, loudnorm_filter=cfg.LOUDNORM_FILTER_OVERRIDE,
        use_hwaccel=use_hwaccel_for_file, output_width=output_width, output_height=output_height,
        blur_background=cfg.BLUR_BACKGROUND, denoise=cfg.DENOISE, sharpen=cfg.SHARPEN,
        tonemap_to_sdr=tonemap_to_sdr, lut_path=cfg.LUT_PATH, auto_levels=cfg.AUTO_LEVELS,
        smooth_fps=cfg.SMOOTH_FPS, noise_gate=cfg.NOISE_GATE, silence_removal_intervals=silence_removal_intervals,
        stabilize_transform_path=stabilize_transform_path,
        chromakey_color=cfg.CHROMAKEY_COLOR if cfg.CHROMAKEY else None, chromakey_similarity=cfg.CHROMAKEY_SIMILARITY,
        chromakey_blend=cfg.CHROMAKEY_BLEND, chromakey_bg_color=cfg.CHROMAKEY_BG_COLOR,
        input_width=source_width, input_height=source_height,
        pip_geometry=pip_geometry, pip_opacity=cfg.PIP_OPACITY, pip_input_index=1 if pip_geometry else None,
        fade_in_seconds=cfg.FADE_IN_SECONDS, fade_out_seconds=cfg.FADE_OUT_SECONDS, output_duration_seconds=output_seconds,
        text_file_path=cfg.TEXT_FILE_PATH, text_position=cfg.TEXT_POSITION, text_font=cfg.TEXT_FONT, text_font_size=cfg.TEXT_FONT_SIZE, text_color=cfg.TEXT_COLOR,
        replace_audio_input_index=replace_audio_input_index, hwaccel_decode_only=use_hwaccel_decode_for_file,
        subtitle_filter=preview_subtitle_filter,
        deinterlace=cfg.DEINTERLACE and not deinterlace_on_gpu, orientation_filters=[] if orientation_on_gpu else cfg.ORIENTATION_FILTERS,
        gpu_prefix=gpu_prefix,
        denoise_filter=cfg.DENOISE_FILTER_OVERRIDE, sharpen_filter=cfg.SHARPEN_FILTER_OVERRIDE, tonemap_filter=cfg.TONEMAP_FILTER_OVERRIDE,
        eq_filter=cfg.EQ_FILTER, lut_intensity=cfg.LUT_INTENSITY, audio_stream_index=cfg.AUDIO_TRACK, audio_fx_filters=cfg.AUDIO_FX_FILTERS,
        layers=file_layers, layer_text_files=layer_text_files, layer_image_inputs=layer_image_inputs,
        broll_audio_sources=build_broll_audio_sources(file_layers, layer_image_inputs) if cfg.KEEP_AUDIO else None,
        progress_bar=cfg.PROGRESS_BAR, frame_border=cfg.FRAME_BORDER, frame_radius=cfg.FRAME_RADIUS,
        vignette_filter=cfg.VIGNETTE_FILTER, ken_burns_filter=ken_burns_filter,
        watermark_cycle_positions=watermark_cycle_positions, watermark_cycle_seconds=cfg.WATERMARK_MOVE_SECONDS,
        pip_audio_input_index=pip_audio_input_index, pip_duck=cfg.PIP_DUCK,
    )

    total_frames = max(1, int(output_seconds * output_fps_value))
    hdr_output_args = get_hdr_output_args(probe_info.get("color_primaries"), probe_info.get("color_transfer"), probe_info.get("color_space")) if hdr_passthrough else []

    # --effort (item: דרגות מאמץ קידוד/משאבי-מחשב, כולל "auto") - נפתר פר-קובץ
    # (ראו resolve_file_effort_settings). filter_threads (גלובלי, משפיע על
    # שרשרת הפילטרים - scale/pad/watermark/וכו', שרצה על CPU בכל מקרה) ו-threads
    # (על הקודק עצמו, ליד -c:v). [] (effective_effort="high") = בלי הגבלה
    # כלל, זהה בדיוק להתנהגות הקודמת.
    effective_effort, file_nvenc_preset, effort_threads = resolve_file_effort_settings()
    if cfg.EFFORT == "auto":
        print(f"[INFO] {filename}: --effort auto בחר '{effective_effort}'.")
        sys.stdout.flush()
    effort_filter_args = ["-filter_threads", str(effort_threads)] if effort_threads else []
    effort_codec_args = ["-threads", str(effort_threads)] if effort_threads else []

    cmd_prefix = [cfg.FFMPEG_EXE, "-y"] + effort_filter_args
    # -ss/-t (item: trim range / auto-trim silence) חייבים לבוא *לפני* ה--i
    # שהם חלים עליו - חלים רק על ה-video_path הראשי, לא על קלט ה-watermark
    # (PNG) שמגיע אחריו בנפרד, בלי -ss/-t משלו.
    if trim_start_seconds > 0.0:
        cmd_prefix += ["-ss", f"{trim_start_seconds:.3f}"]
    if trim_start_seconds > 0.0 or raw_trim_duration is not None:
        cmd_prefix += ["-t", f"{duration:.3f}"]
    if use_hwaccel_for_file or use_hwaccel_decode_for_file:
        # -hwaccel/-hwaccel_output_format חלים רק על ה--i הבא מיד אחריהם - קלט
        # ה-watermark (PNG) בהמשך נשאר פענוח CPU רגיל בכוונה, לא צריך NVDEC
        # לתמונה בודדת קטנה, וממילא עובר format=nv12/hwupload_cuda בפילטר עצמו.
        # אותם דגלי --i בדיוק לשני המצבים - ההבדל היחיד הוא מה קורה *אחרי*
        # הפענוח (build_edit_filter_complex's hwaccel_decode_only למטה).
        cmd_prefix += ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]
    cmd_prefix += ["-i", video_path]
    # PiP (item) נכנס *לפני* watermark - אותו סדר שבו build_edit_filter_complex
    # מחשב את watermark_input_index (pip_input_index+1 כש-PiP קיים) - חייבים
    # להישאר מסונכרנים, שינוי סדר כאן בלי לעדכן שם ישבור את האינדוקס.
    if pip_geometry:
        cmd_prefix += ["-i", cfg.PIP_PATH]
    if watermark_geometry:
        cmd_prefix += ["-i", effective_watermark_path]
    if cfg.REPLACE_AUDIO_PATH:
        cmd_prefix += ["-i", cfg.REPLACE_AUDIO_PATH]
    for input_args in layer_input_args:  # גל 7ב/26: שכבות תמונה ווידאו - אחרי כל הקלטים הקודמים (layer_image_inputs)
        cmd_prefix += input_args
    cmd_prefix += ["-filter_complex", filter_complex, *maps]
    audio_args = ["-c:a", "aac", "-b:a", "128k"] if cfg.KEEP_AUDIO else ["-an"]

    if preview_mode:
        try:
            render_preview_frame(
                video_path, filename, cmd_prefix, output_seconds, output_fps_value, output_width, output_height,
                trim_start_seconds, speed_factor, bool(silence_removal_intervals),
            )
        finally:
            if preview_srt_path:
                try:
                    os.remove(preview_srt_path)  # safe: temp sample-caption SRT this run wrote itself (tempfile.mkstemp above)
                except OSError:
                    pass
        return

    # --validate-only (item: אימות מוקדם של שרשרת הפילטרים) - מריץ את הפקודה
    # האמיתית (filter_complex/watermark/HDR/וכו') על 0.3 שניות בלבד ולפלט null,
    # במקום רינדור מלא - כדי לתפוס שילוב דגלים לא-תקין (LUT פגום, ביטוי crop
    # לא-תקין וכו') לפני שמתחילים באמת לרנדר באצ' שלם. לא רלוונטי ל---target-size-mb
    # (מצב two-pass) - זה בודק תקינות פילטרים, לא ביטרייט, אז ממשיך עם קידוד
    # רגיל (get_codec_args) בכל מקרה.
    if cfg.VALIDATE_ONLY:
        validate_cmd = cmd_prefix + audio_args + get_codec_args(cfg.CODEC, preset=file_nvenc_preset, cq=cfg.CODEC_QUALITY) + hdr_output_args + ["-t", "0.3", "-f", "null", os.devnull]
        if stabilize_transform_path is not None:
            try:
                os.remove(stabilize_transform_path)  # safe: temp vidstab transforms this run wrote itself, not user input
            except OSError:
                pass
        try:
            result = subprocess.run(validate_cmd, capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS)
            valid = result.returncode == 0
            error_tail = (result.stderr or "").strip()[-500:]
        except Exception as e:
            valid = False
            error_tail = str(e)
        if valid:
            print(f"[VALID] {filename}: שרשרת הפילטרים ופקודת ffmpeg תקינות.")
            _bump(results, "valid")
            _manifest_record(filename, "valid")
        else:
            print(f"[INVALID] {filename}: {error_tail}")
            _bump(results, "invalid")
            _manifest_record(filename, "invalid", reason=error_tail[-300:])
        sys.stdout.flush()
        return

    # --target-size-mb (item: two-pass VBR quality mode) - h264 (libx264) צריך
    # שתי קריאות ffmpeg נפרדות (pass 1 כותב סטטיסטיקה בלבד ל-passlog, נזרק
    # ל-devnull; pass 2 קורא אותה ומפיק את הקידוד האמיתי). hevc/av1 (NVENC)
    # מקבלים את אותה איכות ב-"-multipass fullres" בקריאה בודדת אחת (NVENC לא
    # תומך בקבצי pass-log כמו libx264) - ראו get_two_pass_codec_args().
    passlog_path = None
    if cfg.TARGET_SIZE_MB is not None:
        audio_kbps = 128 if cfg.KEEP_AUDIO else 0
        bitrate_kbps = compute_target_bitrate_kbps(cfg.TARGET_SIZE_MB, output_seconds, audio_kbps=audio_kbps)
        if cfg.CODEC == "h264":
            passlog_path = os.path.join(output_dir, f"{base_name}_2pass")
            pass1_cmd = cmd_prefix + audio_args + effort_codec_args + get_two_pass_codec_args(cfg.CODEC, bitrate_kbps, 1, passlog_path, preset=file_nvenc_preset) + ["-f", "null", os.devnull]
            print(f"[INFO] {filename}: יעד {cfg.TARGET_SIZE_MB:.1f}MB (~{bitrate_kbps}kbps) - מריץ pass 1/2...")
            sys.stdout.flush()
            try:
                pass1_ok = run_ffmpeg_with_progress(pass1_cmd, total_frames, f"{filename} (pass 1/2)", control=_file_control(filename))
            except FfmpegCancelled:
                print(f"[CANCELLED] {filename}: בוטל באמצע pass 1/2.")
                sys.stdout.flush()
                _bump(results, "cancelled")
                _manifest_record(filename, "cancelled", reason="בוטל מהממשק")
                return
            if not pass1_ok:
                print(f"[ERROR] עריכת {filename} נכשלה (pass 1/2).")
                _bump(results, "errors")
                _file_failed(filename, "pass 1/2 נכשל")
                return
            cmd = cmd_prefix + audio_args + effort_codec_args + get_two_pass_codec_args(cfg.CODEC, bitrate_kbps, 2, passlog_path, preset=file_nvenc_preset) + [partial_output_path]
            progress_label = f"{filename} (pass 2/2)"
        else:
            cmd = cmd_prefix + audio_args + effort_codec_args + get_two_pass_codec_args(cfg.CODEC, bitrate_kbps, 2, "", preset=file_nvenc_preset) + hdr_output_args + [partial_output_path]
            progress_label = filename
    else:
        cmd = cmd_prefix + audio_args + effort_codec_args + get_codec_args(cfg.CODEC, preset=file_nvenc_preset, cq=cfg.CODEC_QUALITY) + hdr_output_args + [partial_output_path]
        progress_label = filename

    # item: המתנה/ניסיון-חוזר כש-NVENC session-limited, במקום להיכשל מיד -
    # רלוונטי רק ל-hevc/av1 (NVENC), h264 (libx264, CPU) אף פעם לא נכשל
    # מהסיבה הזו אז is_nvenc=False שם פשוט מדלג על כל ניסיון-חוזר.
    # item: מגבלת-מקביליות אמיתית ל-NVENC - מחזיק את ה-semaphore (אם פעיל, ראו
    # NVENC_SEMAPHORE למעלה) לאורך כל הקריאה כולל ניסיונות-חוזרים, כדי שבאמת
    # לא ירוצו יותר קידודי NVENC בו-זמנית ממה שזוהה/הוגדר - לא רק "ינסו לרוץ"
    # ואז ייתקלו בכשל session-limit שהניסיון-החוזר הקיים צריך לספוג בדיעבד.
    nvenc_guard = cfg.NVENC_SEMAPHORE if cfg.NVENC_SEMAPHORE is not None else contextlib.nullcontext()
    encode_stderr = []   # 24.10.2026: הסוף של ה-stderr של הקידוד - הסיכום של loudnorm (LUFS על הפלט, בלי מעבר נוסף)
    try:
        with nvenc_guard:
            ok = run_ffmpeg_with_progress_and_nvenc_retry(cmd, total_frames, progress_label, is_nvenc=cfg.CODEC in ("hevc", "av1"), control=_file_control(filename),
                                                          on_stderr=encode_stderr.append)
    except FfmpegCancelled:
        # item 95: בוטל מהווב באמצע הקידוד - מנקים את הפלט החלקי, ממשיכים לקבצים הבאים
        ok = None
    if passlog_path is not None:
        for ext in (".log", ".log.mbtree"):
            try:
                os.remove(passlog_path + "-0" + ext)  # safe: temp two-pass passlog this run wrote itself, not user input
            except OSError:
                pass  # לא קריטי - שאריות passlog לא משפיעות על שום ריצה עתידית
    if stabilize_transform_path is not None:
        try:
            os.remove(stabilize_transform_path)  # safe: temp vidstab transforms this run wrote itself, not user input
        except OSError:
            pass  # לא קריטי - שאריות transforms לא משפיעות על שום ריצה עתידית
    if ok is None:
        try:
            os.remove(partial_output_path)  # safe: this run's own partial render (partial_output_path), cancelled mid-encode
        except OSError:
            pass
        print(f"[CANCELLED] {filename}: בוטל באמצע הקידוד.")
        sys.stdout.flush()
        _bump(results, "cancelled")
        _manifest_record(filename, "cancelled", reason="בוטל מהממשק")
        return
    if ok:
        # item: פלט אטומי (resume batch שנקטע) - מעביר את הקובץ הגמור מהנתיב
        # הזמני לנתיב הסופי רק כאן, אחרי הצלחה מוכחת - אטומי על אותה מערכת
        # קבצים (os.replace), אז output_path לעולם לא נראה קיים בזמן שהוא
        # עדיין חצי-כתוב.
        try:
            os.replace(partial_output_path, output_path)  # safe: moves this run's own temp render (partial_output_path convention above) to its final output_path, both inside output_dir, never touches INPUT_DIR/user source files
        except OSError as e:
            print(f"[ERROR] העברת {os.path.basename(partial_output_path)} לפלט הסופי נכשלה: {e}")
            _bump(results, "errors")
            _file_failed(filename, "העברת הפלט הזמני לסופי נכשלה")
            return
        print(f"[APPROVED] נוצר: {os.path.basename(output_path)}")
        _bump(results, "files_created")
        _remember_render_key(output_path, render_key)
        if numbering_active:
            _mark_number_used_successfully(reserved_number)
        current_signature = _compute_current_signature(video_path)
        if current_signature is not None:
            try:
                os.makedirs(os.path.dirname(sig_path), exist_ok=True)
                with open(sig_path, "w", encoding="utf-8") as f:
                    json.dump({"signature": current_signature}, f)
            except OSError:
                pass  # לא קריטי - רק מונע דילוג חכם בריצה הבאה, לא משפיע על הפלט הזה
        maybe_generate_thumbnail(output_path, tonemap_hdr=hdr_passthrough)
        maybe_burn_captions(output_path, hdr_output_args=hdr_output_args, nvenc_preset=file_nvenc_preset, source_path=video_path)
        maybe_post_process(output_path, output_width, output_height, output_fps_str, file_nvenc_preset, hdr_output_args)
        # item: ייצוא דוח קידוד - נמדד כאן (לא לפני), אחרי שריפת הכתוביות -
        # זו re-encode שנייה שמחליפה את output_path במקום, אז גודל-הקובץ
        # שנמדד קודם היה מיושן/שגוי בריצות עם --captions.
        try:
            output_size_mb = round(os.path.getsize(output_path) / (1024 ** 2), 2)
        except OSError:
            output_size_mb = None
        _record_file(results, {
            "source_filename": filename, "output_filename": os.path.basename(output_path),
            "codec": cfg.CODEC, "container": cfg.CONTAINER, "resolution": f"{output_width}x{output_height}",
            "fps": output_fps_str, "duration_seconds": round(output_seconds, 1),
            "output_size_mb": output_size_mb, "render_seconds": round(time.monotonic() - file_start_time, 1),
            "hdr": hdr_passthrough,
        })
        output_lufs = loudnorm_output_lufs(encode_stderr[-1]) if cfg.KEEP_AUDIO and cfg.LOUDNORM and encode_stderr else None
        _manifest_record(
            filename, "created", output=output_path, output_size_mb=output_size_mb, variant=variant["orientation"],
            render_seconds=round(time.monotonic() - file_start_time, 1), duration_seconds=round(output_seconds, 1),
            resolution=f"{output_width}x{output_height}", output_lufs=output_lufs,
            lufs_target=loudnorm_target_lufs(cfg.LOUDNORM_FILTER_OVERRIDE) if output_lufs is not None else None,
        )
        maybe_notify_per_file(filename, success=True)
    else:
        print(f"[ERROR] עריכת {filename} נכשלה.")
        _bump(results, "errors")
        try:
            os.remove(partial_output_path)  # safe: this run's own temp/partial render output (see partial_output_path above) after a failed encode - never touches INPUT_DIR/user source files
        except OSError:
            pass  # לא קריטי - ffmpeg לפעמים לא משאיר קובץ חלקי בכלל בכשל מוקדם
        _file_failed(filename, "הרינדור נכשל")


def preview_clip_video_args():
    """קידוד מהיר ב-CPU לקטע התצוגה המקדימה (גל 10) - H.264 שכל דפדפן מנגן,
    faststart כדי שה-<video> יתחיל לנגן בלי להוריד את כל הקובץ."""
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]


def render_preview_frame(video_path, filename, cmd_prefix, output_seconds, output_fps_value, output_width, output_height,
                         trim_start_seconds, speed_factor, has_removed_ranges):
    """item: תצוגה מקדימה מלאה (--preview-frame) - פריים PNG יחיד מהשרשרת המלאה
    (cmd_prefix = אותה פקודה בדיוק כמו ברינדור, עד ה-filter_complex והמיפוי),
    בנקודה PREVIEW_FRAME_SECONDS בציר-הזמן של הפלט (-ss *אחרי* ה--i = חיפוש
    בפלט המסונן, אחרי חיתוך/טיימלאפס/טווחים). אופציונלית גם פריים המקור הגולמי
    באותה נקודה, מוקטן לאותן מידות עם שוליים (item: לפני/אחרי). מדפיס שורת
    PREVIEW_FRAME: {...} שה-web app קורא; כשל -> SystemExit(1) עם זנב ה-stderr.
    גל 10: עם PREVIEW_CLIP_SECONDS > 0 - קטע MP4 קצר (עם שמע) במקום PNG."""
    clip_seconds = PREVIEW_CLIP_SECONDS
    if clip_seconds > 0:
        frame_time = min(PREVIEW_FRAME_SECONDS, max(0.0, output_seconds - clip_seconds))
        clip_seconds = min(clip_seconds, max(0.1, output_seconds - frame_time))
        audio_args = ["-c:a", "aac", "-b:a", "128k"] if KEEP_AUDIO else ["-an"]
        cmd = cmd_prefix + ["-ss", f"{frame_time:.3f}", "-t", f"{clip_seconds:.3f}", *audio_args, *preview_clip_video_args(), PREVIEW_FRAME_OUT]
        timeout = 240
    else:
        frame_time = min(PREVIEW_FRAME_SECONDS, max(0.0, output_seconds - 1.0 / max(1.0, output_fps_value)))
        cmd = cmd_prefix + ["-ss", f"{frame_time:.3f}", "-frames:v", "1", "-update", "1", PREVIEW_FRAME_OUT]
        timeout = 150
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=NO_WINDOW_FLAGS)
    if result.returncode != 0 or not os.path.exists(PREVIEW_FRAME_OUT):
        print(f"[ERROR] יצירת {'קטע' if clip_seconds > 0 else 'פריים'} התצוגה המקדימה נכשלה עבור {filename}:")
        print((result.stderr or "").strip()[-800:])
        sys.stdout.flush()
        raise SystemExit(1)
    speed = speed_factor or 1.0
    source_time = trim_start_seconds + frame_time * speed
    if PREVIEW_FRAME_BEFORE_OUT:
        pad_chain = f"scale={output_width}:{output_height}:force_original_aspect_ratio=decrease,pad={output_width}:{output_height}:(ow-iw)/2:(oh-ih)/2"
        if clip_seconds > 0:
            # אותו קצב כמו הפלט (setpts) - כדי שהמחיצה "לפני/אחרי" תראה את אותו רגע בשני הצדדים
            before_chain = (f"setpts=PTS/{speed:g}," if abs(speed - 1.0) > 1e-6 else "") + pad_chain + ",format=yuv420p"
            before_cmd = [
                FFMPEG_EXE, "-y", "-ss", f"{source_time:.3f}", "-t", f"{clip_seconds * speed:.3f}", "-i", video_path,
                "-vf", before_chain, "-an", *preview_clip_video_args(), PREVIEW_FRAME_BEFORE_OUT,
            ]
            subprocess.run(before_cmd, capture_output=True, timeout=180, creationflags=NO_WINDOW_FLAGS)
        else:
            before_cmd = [FFMPEG_EXE, "-y", "-ss", f"{source_time:.3f}", "-i", video_path, "-frames:v", "1", "-vf", pad_chain, "-update", "1", PREVIEW_FRAME_BEFORE_OUT]
            subprocess.run(before_cmd, capture_output=True, timeout=60, creationflags=NO_WINDOW_FLAGS)
    notes = []
    if args.hwaccel or args.hwaccel_decode:
        notes.append("התצוגה המקדימה רצה ב-CPU - הרינדור עצמו ישתמש ב-GPU כפי שהוגדר.")
    if STABILIZE:
        notes.append("ייצוב וידאו לא מוחל בתצוגה המקדימה (דורש ניתוח של כל הקובץ).")
    if TRIM_SILENCE or REMOVE_MID_SILENCE:
        notes.append("זיהוי שקט אוטומטי לא מוחל בתצוגה המקדימה - הזמן הוא לפני הסרת השקט.")
    if clip_seconds > 0 and PIP_AUDIO and PIP_PATH:
        notes.append("השמע מה-PiP לא מעורבב בקטע התצוגה המקדימה - רק ברינדור עצמו.")
    if clip_seconds > 0 and not KEEP_AUDIO:
        notes.append('הקטע בלי שמע - "שמירת אודיו" כבויה.')
    if CAPTIONS:
        notes.append("הכתובית היא דוגמה לעיצוב בלבד - התמלול האמיתי נעשה בזמן הרינדור.")
    if has_removed_ranges:
        notes.append("פריים ה'לפני' לא מתחשב בטווחים שהוסרו - הוא מהמקור בזמן המקביל לפני ההסרה.")
    print("PREVIEW_FRAME: " + json.dumps({
        "time": round(frame_time, 3), "source_time": round(source_time, 3), "output_seconds": round(output_seconds, 3),
        "output_width": output_width, "output_height": output_height, "notes": notes,
        "clip_seconds": round(clip_seconds, 3) if clip_seconds > 0 else None,
    }, ensure_ascii=False))
    sys.stdout.flush()


def run_concat_mode():
    """item: מעברים בין כמה קטעים - מצב-ריצה נפרד לגמרי (לא עובר דרך
    process_video בכלל) - started_at_iso למטה עבור ה-run manifest: מאחה את CONCAT_FILES לתוצר יחיד עם מעבר-חלק
    (--concat-transition fade) או חיתוך-קשה (none) ביניהם. מכוון בכוונה
    ל"איחוד קטעים גולמיים" - watermark/LUT/trim/כל שאר הדגלים הרגילים לא
    רלוונטיים כאן (ראו --concat-files's help), רק scale למידות-פלט משותפות
    (VERTICAL קובע), קידוד (CODEC/CONTAINER), ואם KEEP_AUDIO - כל עוד לכל
    הקטעים באמת יש אודיו (אחרת נופל בחזרה בלי אודיו במקום להיכשל)."""
    started_at_iso = time.strftime("%Y-%m-%dT%H:%M:%S")
    resolved_paths = []
    for name_or_path in CONCAT_FILES:
        candidate = name_or_path if os.path.isabs(name_or_path) else os.path.join(INPUT_DIR, name_or_path)
        if not os.path.isfile(candidate):
            print(f"[ERROR] --concat-files: קובץ לא נמצא: {candidate}")
            sys.stdout.flush()
            return
        resolved_paths.append(candidate)

    probes = [probe_video(p) for p in resolved_paths]
    durations = [p["duration"] for p in probes]
    if any(not d for d in durations):
        print("[ERROR] --concat-files: לא הצלחתי לקרוא את האורך של אחד (או יותר) מהקבצים.")
        sys.stdout.flush()
        return
    if CONCAT_TRANSITION == "fade" and CONCAT_TRANSITION_DURATION >= min(durations):
        print(
            f"[ERROR] --concat-transition-duration ({CONCAT_TRANSITION_DURATION:.1f}s) ארוך מדי - "
            f"חייב להיות קצר מהקטע הקצר ביותר ({min(durations):.1f}s)."
        )
        sys.stdout.flush()
        return

    include_audio = KEEP_AUDIO
    if include_audio and not all(p["has_audio"] for p in probes):
        print("[INFO] --concat-files: לא לכל הקטעים יש אודיו - הפלט ייווצר בלי אודיו (--keep-audio מתעלם).")
        sys.stdout.flush()
        include_audio = False

    output_width, output_height = resolve_output_dimensions(VERTICAL)
    scale_chain = resolve_scale_chain(VERTICAL, target_width=output_width, target_height=output_height)
    output_fps_str, output_fps_value = resolve_output_fps(OUTPUT_FPS_OVERRIDE, probes[0].get("fps"))

    filter_complex, maps = build_concat_transitions_filter_complex(
        durations, scale_chain, transition=CONCAT_TRANSITION, transition_duration=CONCAT_TRANSITION_DURATION,
        include_audio=include_audio,
    )
    # fps= לא חלק מ-build_concat_transitions_filter_complex (זה לא concern
    # שלה - היא רק מאחה) - מוסיפים אותו כאן כשלב אחרון על [outv], כמו
    # build_edit_filter_complex עושה, כדי שקצב-הפריימים הסופי יהיה אחיד
    # (קטעים שונים יכולים להגיע בקצבים מקוריים שונים).
    filter_complex = filter_complex.replace("[outv]", "[outv_pre]", 1) + f";[outv_pre]fps={output_fps_str}[outv]"

    output_filename = resolve_output_filename(CONCAT_OUTPUT_NAME, VERTICAL, container=CONTAINER, codec=CODEC)
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    cmd = [FFMPEG_EXE, "-y"]
    for p in resolved_paths:
        cmd += ["-i", p]
    cmd += ["-filter_complex", filter_complex, *maps]
    cmd += ["-c:a", "aac", "-b:a", "128k"] if include_audio else ["-an"]
    cmd += get_codec_args(CODEC, preset=NVENC_PRESET_EXPLICIT, cq=CODEC_QUALITY)
    cmd += [output_path]

    total_output_seconds = max(0.0, sum(durations) - CONCAT_TRANSITION_DURATION * (len(durations) - 1) if CONCAT_TRANSITION == "fade" else sum(durations))
    total_frames = max(1, int(total_output_seconds * output_fps_value))

    print(f"[INFO] מאחה {len(resolved_paths)} קטעים ({CONCAT_TRANSITION}, {CONCAT_TRANSITION_DURATION:.1f}s) לתוך {output_filename} - אורך משוער: {total_output_seconds:.1f}s.")
    sys.stdout.flush()

    def _log_waiting(_seconds_waited):
        print("⏳ ממתין לסיום רינדור אחר שרץ כרגע (GUI/דפדפן/בוט)...")
        sys.stdout.flush()

    with render_lock_if_needed(on_wait=_log_waiting):
        success = run_ffmpeg_with_progress(cmd, total_frames, output_filename)

    concat_label = " + ".join(os.path.basename(p) for p in resolved_paths)
    if success and os.path.exists(output_path):
        print(f"[SUCCESS] האיחוד הסתיים: {output_path}")
        _manifest_record(concat_label, "created", output=output_path, duration_seconds=round(total_output_seconds, 1),
                         output_size_mb=round(os.path.getsize(output_path) / (1024 ** 2), 2))
        result = {"files_created": 1, "errors": 0, "clips_merged": len(resolved_paths),
                  "output_path": output_path, "duration_seconds": round(total_output_seconds, 1)}
    else:
        print(f"[ERROR] האיחוד נכשל: {output_filename}")
        _manifest_record(concat_label, "error", reason="האיחוד נכשל")
        result = {"files_created": 0, "errors": 1, "clips_merged": len(resolved_paths)}
    manifest_path = write_run_manifest("concat", result, started_at_iso, output_path=output_path)
    if manifest_path:
        result["manifest_path"] = manifest_path
    print("RESULT: " + json.dumps(result, ensure_ascii=False))


def main():
    if CONCAT_FILES:
        run_concat_mode()
        return

    # find_video_files_by_folder הולך רקורסיבית תיקיה-תיקיה (לא רק בתיקיית השורש
    # של INPUT_DIR) - כך שתיקיית-על עם תת-תיקייה נפרדת לכל הקלטה מקודדת בבת אחת,
    # בלי להריץ את הסקריפט בנפרד על כל תת-תיקייה.
    folder_groups = find_video_files_by_folder(INPUT_DIR)
    if args.no_subfolders:
        root = os.path.normpath(INPUT_DIR)
        folder_groups = [(folder_path, files) for folder_path, files in folder_groups if os.path.normpath(folder_path) == root]
    if ONLY_FILES is not None:
        # item: תור-אצווה ניתן-לעריכה - חל רק על תיקיית השורש עצמה (folder_path
        # == INPUT_DIR), לא על תתי-תיקיות - אלה ממשיכות במלואן, בדיוק כמו
        # שה-UI (שרק מציג/עורך את השורש) מעולם לא הציע לערוך אותן. סדר
        # הרשימה נשמר במדויק (לא ה-sorted() של find_video_files) - זו כל
        # הנקודה של "ניתן-לעריכה/לסידור".
        normalized_input_dir = os.path.normpath(INPUT_DIR)
        filtered_groups = []
        for folder_path, files in folder_groups:
            if os.path.normpath(folder_path) == normalized_input_dir:
                by_basename = {os.path.basename(f): f for f in files}
                selected = [by_basename[name] for name in ONLY_FILES if name in by_basename]
                if selected:
                    filtered_groups.append((folder_path, selected))
            else:
                filtered_groups.append((folder_path, files))
        folder_groups = filtered_groups
    if not folder_groups:
        print(f"[ERROR] לא נמצאו קובצי וידאו בתיקייה: {INPUT_DIR}")
        sys.stdout.flush()
        return

    total_files = sum(len(files) for _, files in folder_groups)

    if PREVIEW_FRAME_SECONDS is not None:
        # item: תצוגה מקדימה מלאה - הקובץ הראשון בלבד, בלי נעילת-רינדור (פריים
        # בודד, לא רינדור GPU כבד) ובלי manifest/RESULT של ריצה רגילה.
        _first_folder, first_files = folder_groups[0]
        process_video(first_files[0], {"files_created": 0, "errors": 0, "skipped": 0, "valid": 0, "invalid": 0}, OUTPUT_DIR)
        return

    if PREVIEW_ONLY:
        # תצוגה מקדימה בלבד (item: preview thumbnail contact-sheet) - לא נועלת
        # את render_lock בכלל, זה לא רינדור GPU כבד, רק חילוץ פריימים מהיר.
        all_video_paths = [path for _, files in folder_groups for path in files]
        preview_path = os.path.join(OUTPUT_DIR, "_preview_contact_sheet.png")
        generate_contact_sheet(all_video_paths, preview_path, ffmpeg_exe=FFMPEG_EXE, ffprobe_exe=FFPROBE_EXE)
        print(f"[INFO] נמצאו {total_files} סרטונים ב-{len(folder_groups)} תיקיות - contact-sheet לתצוגה מקדימה נוצר.")
        print(f"[SUCCESS] תצוגה מקדימה מוכנה: {preview_path}")
        print("RESULT: " + json.dumps({"preview_path": preview_path, "videos_found": total_files}, ensure_ascii=False))
        return

    print(f"[INFO] נמצאו {total_files} סרטונים ב-{len(folder_groups)} תיקיות לעריכה.")
    sys.stdout.flush()

    def _log_waiting(_seconds_waited):
        print("⏳ ממתין לסיום רינדור אחר שרץ כרגע (GUI/דפדפן/בוט)...")
        sys.stdout.flush()

    # hwaccel/codec ב-RESULT (item: "time saved with --hwaccel" metric) - כדי
    # ש-utils/shared/job_history.py's get_hwaccel_time_comparison() יוכל להשוות זמן
    # רינדור ממוצע-לקובץ בין ריצות עם/בלי --hwaccel, בלי צורך בעמודת DB חדשה
    # (result_json כבר קיים ונשמר בכל מקרה).
    results = {
        "files_created": 0, "errors": 0, "skipped": 0, "valid": 0, "invalid": 0,
        "hwaccel": USE_HWACCEL, "codec": CODEC, "parallel": PARALLEL, "effort": EFFORT,
    }
    # item: ייצוא דוח קידוד - "files" (רשימת רשומה-לכל-קובץ-שנוצר, ראו
    # _record_file) רק כש-EXPORT_REPORT בכלל התבקש - אחרת לא נצבר כלום (וגם
    # לא מנופח שורת RESULT: הרגילה בבאצ'ים גדולים שלא ביקשו דוח בכלל).
    if EXPORT_REPORT:
        results["files"] = []
    if RUN_CONTROL is not None:
        results["cancelled"] = 0  # item 95: רק כשיש קובץ-בקרה (אחרת אין איך לבטל) - RESULT נשאר זהה לשאר המקרים
    # item: דוח סיכום ריצה - זמן-קיר כולל, לא רק ספירת קבצים. monotonic (לא
    # time.time()) כי לא אכפת לנו מהשעה בפועל, רק מהפרש - חסין לשינויי שעון
    # מערכת (DST/NTP) שיכולים לקרות באמצע ריצה ארוכה.
    start_time = time.monotonic()
    started_at_iso = time.strftime("%Y-%m-%dT%H:%M:%S")
    # render_lock_if_needed - מגן על עצמו גם כשמופעל ישירות (טרמינל), לא רק
    # דרך worker.py/remote_execution.py (שכבר תופסים את אותו מנעול ומעבירים
    # RENDER_LOCK_HELD_BY_CALLER כדי שהתפיסה כאן תדלג ולא תינעל על עצמה).
    # עוטף את כל האצווה (לא קובץ-קובץ) - זהה בגרנולריות ל-worker.py's lock_ctx.
    # item: --parallel - בונים רשימת (video_path, folder_output_dir) שטוחה
    # מראש (כולל יצירת כל תיקיות הפלט/הדפסת כותרות תיקייה), כדי שהריצה
    # בפועל בהמשך (ברצף או במקביל ב-run_tasks) תהיה בלוגיקה אחת
    # משותפת בלי כפילות קוד בין שני המסלולים.
    tasks = []
    for folder_path, video_files in folder_groups:
        rel = os.path.relpath(folder_path, INPUT_DIR)
        if rel != ".":
            print(f"[INFO] 📁 תיקייה: {rel} ({len(video_files)} סרטונים)")
            sys.stdout.flush()
        for variant in VARIANTS:
            # קבצים ישירות ב-INPUT_DIR נשארים שטוחים בתיקיית הפלט (כמו קודם); תתי-
            # תיקיות ממופות לאותו מבנה, כדי שקבצים באותו שם לא ידרסו זה את זה.
            # item: פלט כפול - לכל variant תיקיית-שורש משלו (horizontal/vertical/square).
            folder_output_dir = variant["output_root"] if rel == "." else os.path.join(variant["output_root"], rel)
            os.makedirs(folder_output_dir, exist_ok=True)
            for video_path in video_files:
                tasks.append((video_path, folder_output_dir, variant))

    processed = 0
    progress_lock = threading.Lock()

    total_tasks = len(tasks)
    # כמה מתוך כמה (utils/shared/worker.py) - מההתחלה, כדי שהפס הראשי ישקלל את הקובץ שבעבודה (בקובץ אחד היה 0% עד הסוף)
    print(f"PROGRESS:0/{total_tasks}")
    sys.stdout.flush()

    def _run_one(video_path, folder_output_dir, variant):
        nonlocal processed
        name = os.path.basename(video_path)
        # item 95: קובץ שבוטל/הושהה מהווב *לפני* שהתחיל - ממתין בהשהיה, מדלג בביטול
        action = RUN_CONTROL.wait_while_paused(name, on_pause=lambda: (print(f"[PAUSED] {name}: ממתין להמשך לפני תחילת העיבוד."), sys.stdout.flush())) if RUN_CONTROL else "run"
        if action == "cancel":
            print(f"[CANCELLED] {name}: בוטל לפני תחילת העיבוד.")
            sys.stdout.flush()
            _bump(results, "cancelled")
            _manifest_record(name, "cancelled", reason="בוטל מהממשק")
        else:
            # item: ממשק batch לדריסת דגלים פר-קובץ - לפי שם-קובץ מדויק (לא נתיב
            # מלא, --batch-overrides נכתב מנקודת-המבט של המשתמש שרק רואה שמות).
            process_video(video_path, results, folder_output_dir, overrides=BATCH_OVERRIDES.get(name), variant=variant)
        with progress_lock:
            processed += 1
            print(f"PROGRESS:{processed}/{total_tasks}")
            sys.stdout.flush()

    try:
        with render_lock_if_needed(on_wait=_log_waiting):
            if PARALLEL > 1:
                print(f"[INFO] מקודד עד {PARALLEL} סרטונים בו-זמנית (--parallel).")
                sys.stdout.flush()
            # item 96: כל worker בוחר את הקובץ הבא רק כשהוא מתפנה - לפי רשימת העדיפות
            # מקובץ-הבקרה (אם יש), כך ש"⬆ הבא בתור" בווב משפיע על מה שעוד לא התחיל.
            # חריגה בלתי-צפויה ב-worker עולה כאן ומפילה את הריצה בגלוי (כמו future.result()).
            pick = (lambda pending: next_task_index([os.path.basename(t[0]) for t in pending], RUN_CONTROL.priority())) if RUN_CONTROL else None
            run_tasks(tasks, _run_one, PARALLEL, pick=pick)
    finally:
        # item: מספור סרטונים - רץ גם על חריגה/KeyboardInterrupt שיצאה מהלולאה
        # למעלה (לא רק בסיום תקין) - כך שעצירה יזומה (Ctrl+C) שבכל זאת רצה
        # בתוך התהליך הזה עדיין "מחזירה למחזור" מספרים שלא נוצלו. הריגה
        # חיצונית (למשל כפתור Stop ב-GUI) לא מגיעה לכאן כלל - ראו התיעוד
        # המלא ב-_reserve_next_number/persist_final_counter_value.
        rolled_back_to = persist_final_counter_value()
        if rolled_back_to is not None:
            print(f"[INFO] מספור סרטונים: המונה תוקן חזרה ל-{rolled_back_to} (מספרים שהוקצו בריצה הזו ולא נוצלו בפועל - קובץ שנכשל/דולג - הוחזרו למחזור). הריצה הבאה תמשיך משם.")
            sys.stdout.flush()

    # item: דוח סיכום ריצה - elapsed_seconds/avg_seconds_per_file מצטרפים ל-
    # RESULT: הקיים (כבר נצרך ע"י job_history.py's get_hwaccel_time_comparison
    # דרך result_json), ומודפסים גם כשורת [REPORT] קריאה-לבני-אדם בלוג עצמו -
    # עד עכשיו משך הריצה הכולל היה נגזר רק בדיעבד מ-worker.py's מדידת
    # זמן-תהליך חיצונית, לא נראה כלל בפלט הריצה עצמה.
    elapsed_seconds = time.monotonic() - start_time
    results["elapsed_seconds"] = round(elapsed_seconds, 1)
    avg_seconds_per_file = elapsed_seconds / results["files_created"] if results["files_created"] else None
    results["avg_seconds_per_file"] = round(avg_seconds_per_file, 1) if avg_seconds_per_file is not None else None

    print("\n[SUCCESS] העריכה הסתיימה.")
    if VALIDATE_ONLY:
        print(f"[REPORT] {results['valid']} תקינים, {results['invalid']} לא-תקינים - {elapsed_seconds:.0f}s סה\"כ.")
    else:
        avg_suffix = f", ~{avg_seconds_per_file:.1f}s לקובץ" if avg_seconds_per_file is not None else ""
        print(f"[REPORT] {results['files_created']} נוצרו, {results['skipped']} דולגו, {results['errors']} נכשלו - {elapsed_seconds:.0f}s סה\"כ{avg_suffix}.")

    # item: ייצוא דוח קידוד - "files" (שנאסף תוך-כדי-ריצה ל-results, ראו
    # _record_file) הופך כאן ל-CSV/Excel בפועל, ומוסר מ-results *לפני* שורת
    # RESULT: מודפסת - הקובץ המיוצא הוא הרשומה המפורטת-לכל-קובץ, לא צריך גם
    # לנפח את result_json שנשמר ב-job_history (כבר קיים DB) עם רשימה שיכולה
    # להגיע לאלפי רשומות בבאצ' גדול.
    files_for_report = results.pop("files", None)
    if EXPORT_REPORT and files_for_report is not None:
        os.makedirs(REPORTS_DIR, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        report = {
            "elapsed_seconds": results["elapsed_seconds"], "avg_seconds_per_file": results["avg_seconds_per_file"],
            "files_created": results["files_created"], "skipped": results["skipped"], "errors": results["errors"],
            "codec": CODEC, "container": CONTAINER, "hwaccel": USE_HWACCEL, "parallel": PARALLEL, "effort": EFFORT,
            "files": files_for_report,
        }
        if EXPORT_REPORT in ("csv", "both"):
            csv_path = os.path.join(REPORTS_DIR, f"video_editor_report_{timestamp}.csv")
            write_csv_report(report, csv_path)
            print(f"[INFO] דוח CSV נוצר: {csv_path}")
        if EXPORT_REPORT in ("xlsx", "both"):
            xlsx_path = os.path.join(REPORTS_DIR, f"video_editor_report_{timestamp}.xlsx")
            write_xlsx_report(report, xlsx_path)
            print(f"[INFO] דוח Excel נוצר: {xlsx_path}")
        sys.stdout.flush()

    manifest_path = write_run_manifest("validate" if VALIDATE_ONLY else "render", results, started_at_iso)
    if manifest_path:
        results["manifest_path"] = manifest_path
        print(f"RUN_MANIFEST: {manifest_path}")
    print("RESULT: " + json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
