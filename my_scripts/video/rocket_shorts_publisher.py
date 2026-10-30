# Name: 🎬 פרסום Shorts
# Name (EN): 🎬 Shorts Publisher
# Description: רינדור קליפים של משחקים לגרסאות YouTube ו-TikTok, ברזולוציית המקור או ב-4K, עם מנגנון communicate מבוקר למניעת תקיעות ב-100%.
# Description (EN): Renders gameplay clips into YouTube and TikTok versions, at the source resolution or 4K, with a controlled communicate() mechanism that prevents hangs at 100%.
# Safety: read-only

import os
import glob
import json
import shutil
import subprocess
import sys
import argparse
from concurrent.futures import ThreadPoolExecutor

# --- הגדרת Encoding ל-UTF-8 למניעת UnicodeEncodeError בווינדוס ---
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

# --- פרמטרים אופציונליים. parse_known_args כדי לא להתנגש עם --input_dir שה-GUI/worker.py
# עדיין מזין תמיד לכל סקריפט, גם אם הסקריפט הזה קורא נתיבים מ-rocket_settings.json ולא ממנו ---
arg_parser = argparse.ArgumentParser()
arg_parser.add_argument("--dry-run", action="store_true", help="מדמה את הריצה (מדפיס מה היה קורה) בלי להפעיל ffmpeg/העלאות בפועל")
arg_parser.add_argument("--no-square", action="store_true", help="מדלג על ייצוא הפורמט המרובע (1:1) גם אם מופעל בהגדרות")
arg_parser.add_argument("--no-loudnorm", action="store_true", help="מדלג על נרמול עוצמת השמע גם אם מופעל בהגדרות")
cli_args, _unknown = arg_parser.parse_known_args()
DRY_RUN = cli_args.dry_run

# מציאת תיקיית השורש של הפרויקט (שלוש רמות מעל my_scripts/video/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# מאפשר "from utils.X import Y" גם כשהסקריפט רץ כתת-תהליך עם cwd שונה
# (sys.path[0] כברירת מחדל הוא תיקיית my_scripts/video, לא BASE_DIR)
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from utils.shared.workspace_dir import WORKSPACE_DIR  # CLIPFORGE_WORKSPACE_DIR (טסטים, שרת בדיקה) - ברירת המחדל workspace/ כמו קודם
from utils.shared.workspace_dir import ROCKET_SHORTS, tool_output_dir
from utils.shared.export_dir import follow_global  # output_dir משלו גובר; ברירת המחדל (workspace) = תיקיית הייצוא
from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
from utils.shared.disk_space import estimate_required_bytes, has_enough_disk_space
from utils.media.ffmpeg_progress import run_ffmpeg_with_progress
from utils.shared.render_lock import render_lock_if_needed
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
from utils.shared.retry import call_with_retry
from utils.shared import data_paths
from utils.shared.atomic_write import atomic_write_json
from utils.media import shorts_naming
FFMPEG_EXE = get_ffmpeg_exe()
FFPROBE_EXE = get_ffprobe_exe()

SETTINGS_FILE = data_paths.path(data_paths.ROCKET_SETTINGS)

# הגדרות ברירת מחדל ראשוניות - input/output_dir מתחת ל-workspace/ (לא ישירות
# בשורש הפרויקט) כדי שהתקנה טרייה לא תתחיל מיד לבלגן את השורש לצד קוד המקור.
DEFAULT_SETTINGS = {
    "input_dir": os.path.join(WORKSPACE_DIR, "imports"),
    # workspace/ ישירות (לא workspace/exports) - הפיצול vertical/horizontal/square
    # למטה (YT_DIR/TT_DIR/SQ_DIR/IG_DIR) הוא עכשיו הקטגוריזציה, אז לא צריך גם
    # שכבת "exports" נוספת מסביבו (item: reorganize workspace by orientation).
    "output_dir": WORKSPACE_DIR,
    # ריק = בלי לוגו (מ-30.10.2026 מרנדרים גם בלעדיו; assets/overlay.png כבר לא בריפו מ-16.10.2026) - בוחרים בהגדרות Rocket Shorts
    "watermark_image_path": "",
    "counter_file_path": data_paths.path(data_paths.ROCKET_COUNTER),
    # 30.10.2026: מקודד CPU ("💻 CPU Fallback" ב-ROCKET_QUALITY_PRESETS) - עובד בכל מחשב. עם כרטיס NVIDIA בוחרים
    # פרופיל NVENC בהגדרות; קובץ הגדרות קיים שומר את המקודד שכבר נבחר בו
    "encoder": "libx264",
    "ffmpeg_preset": "medium",
    "quality_cq": 22,
    "watermark_opacity": 0.05,
    "enable_square_export": False,
    "enable_loudnorm": True,
    "max_concurrent_renders": 1,
    "enable_ai_titles": False,
    "enable_thumbnails": False,
    "enable_captions": False,
    "enable_captions_translate": False,
    "enable_smart_crop": False,
    "cleanup_retention_days": 0,
    "enable_weekly_recap": False,
    "weekly_recap_period": "week",
    "weekly_recap_day": 6,
    "enable_instagram_export": False,
    "clip_hotkey": "",
    # item: friend detection via Discord voice channel presence - ריק כברירת
    # מחדל (התכונה מושבתת עד שמוגדר ערוץ קול ספציפי). נקרא ב-cogs/
    # voice_presence_cog.py, לא בסקריפט הזה עצמו.
    "capture_voice_channel_id": "",
    # item: אינטגרציה עם תוכנת לכידה נוספת (Streamlabs/ShadowPlay) - ריק
    # כברירת מחדל (התכונה מושבתת עד שמוגדרת תיקייה). נקרא ב-my_scripts/
    # stream/capture_folder_watcher.py, לא בסקריפט הזה עצמו.
    "capture_watch_dir": "",
    # 30.10.2026: שם הקובץ "<title_prefix> #N", והמשחק לכותרות ה-AI (ריק = לפי שם הקליפ) - utils/media/shorts_naming
    **shorts_naming.NEW,
}

def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_SETTINGS, f, indent=4, ensure_ascii=False)
            print(f"⚠️ קובץ הגדרות חדש נוצר בכתובת: {SETTINGS_FILE}")
        except Exception as e:
            print(f"❌ שגיאה ביצירת קובץ ההגדרות: {e}")
        return DEFAULT_SETTINGS
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 30.10.2026: הגדרות השם והרזולוציה שחסרות בקובץ (utils/media/shorts_naming) - נכתבות אליו פעם אחת, כדי שיהיו גלויות
        naming = shorts_naming.missing_naming(data)
        if naming:
            data.update(naming)
            try:
                atomic_write_json(SETTINGS_FILE, data, indent=4, ensure_ascii=False)
            except OSError as e:
                print(f"⚠️ לא הצלחתי לשמור את קידומת שם הקובץ ב-{SETTINGS_FILE}: {e}")

        if "input_dir" not in data and "rocket_videos_directory" in data:
            data["input_dir"] = data["rocket_videos_directory"]
        elif "input_dir" not in data:
            data["input_dir"] = DEFAULT_SETTINGS["input_dir"]

        if "output_dir" not in data or not data["output_dir"]:
            data["output_dir"] = data["input_dir"]

        # השלמת מפתחות חדשים שלא קיימים בקבצי הגדרות ישנים
        for key, val in DEFAULT_SETTINGS.items():
            data.setdefault(key, val)

        return data
    except Exception:
        return DEFAULT_SETTINGS

settings = load_settings()

VIDEO_DIR = settings.get("input_dir", os.path.abspath(BASE_DIR))
OUTPUT_BASE_DIR = follow_global(settings.get("output_dir", VIDEO_DIR))
WATERMARK = settings.get("watermark_image_path", "")
COUNTER_FILE = settings.get("counter_file_path", data_paths.path(data_paths.ROCKET_COUNTER))
TITLE_PREFIX = shorts_naming.clean_prefix(settings.get("title_prefix"))
OUTPUT_RESOLUTION = shorts_naming.clean_resolution(settings.get("output_resolution"))
GAME_NAME = str(settings.get("game_name") or "").strip()
ENCODER = settings.get("encoder") or DEFAULT_SETTINGS["encoder"]
FFMPEG_PRESET = settings.get("ffmpeg_preset") or DEFAULT_SETTINGS["ffmpeg_preset"]
QUALITY_CQ = int(settings.get("quality_cq") or DEFAULT_SETTINGS["quality_cq"])
IS_NVENC_ENCODER = "nvenc" in ENCODER

def _quality_args(cq_value):
    """NVENC משתמש ב-rc vbr + cq; מקודדי CPU (libx264 וכו') לא מכירים את הדגלים
    האלה בכלל - צריך crf. בלי ההבחנה הזו, בחירת "CPU Fallback" הייתה שולחת
    ל-ffmpeg דגלים לא תואמים למקודד הנבחר בפועל."""
    if IS_NVENC_ENCODER:
        return ["-rc", "vbr", "-cq", str(cq_value)]
    return ["-crf", str(cq_value)]

OPACITY = settings.get("watermark_opacity", 0.05)
ENABLE_SQUARE = settings.get("enable_square_export", False) and not cli_args.no_square
ENABLE_LOUDNORM = settings.get("enable_loudnorm", True) and not cli_args.no_loudnorm
MAX_CONCURRENT_RENDERS = max(1, int(settings.get("max_concurrent_renders", 1) or 1))
ENABLE_AI_TITLES = settings.get("enable_ai_titles", False)
ENABLE_THUMBNAILS = settings.get("enable_thumbnails", False)
ENABLE_CAPTIONS = settings.get("enable_captions", False)
ENABLE_CAPTIONS_TRANSLATE = settings.get("enable_captions_translate", False) and ENABLE_CAPTIONS
ENABLE_SMART_CROP = settings.get("enable_smart_crop", False)
# Instagram Reels ו-TikTok חולקים אותה מפרט וידאו (9:16, אותו טווח משכי זמן) -
# במקום רינדור GPU נוסף (יקר) לתוצר כמעט זהה, פשוט מעתיקים את הפלט של TikTok
# (אחרי צריבת כתוביות, אם מופעלת) לתיקיית Instagram - ראו maybe_export_instagram().
ENABLE_INSTAGRAM = settings.get("enable_instagram_export", False)

# מקוננים תחת vertical/horizontal/square (item: reorganize workspace by
# orientation) - YouTube אופקי, TikTok אנכי; Instagram הוא רק עותק של TikTok
# (ראה maybe_export_instagram) אבל בתיקייה נפרדת כדי לא להתנגש בשם קובץ עם
# TikTok עצמו; Square (1:1) הוא לא-אנכי-ולא-אופקי אז מקבל קטגוריית-על משלו.
# <output_dir>/rocket_shorts/<יעד> (עד 19.10.2026: horizontal/YouTube, vertical/TikTok, vertical/Instagram, square)
YT_DIR = tool_output_dir(ROCKET_SHORTS, "YouTube", base=OUTPUT_BASE_DIR)
TT_DIR = tool_output_dir(ROCKET_SHORTS, "TikTok", base=OUTPUT_BASE_DIR)
SQ_DIR = tool_output_dir(ROCKET_SHORTS, "square", base=OUTPUT_BASE_DIR)
IG_DIR = tool_output_dir(ROCKET_SHORTS, "Instagram", base=OUTPUT_BASE_DIR)

os.makedirs(YT_DIR, exist_ok=True)
os.makedirs(TT_DIR, exist_ok=True)
if ENABLE_SQUARE:
    os.makedirs(SQ_DIR, exist_ok=True)
if ENABLE_INSTAGRAM:
    os.makedirs(IG_DIR, exist_ok=True)

def get_next_number():
    if not os.path.exists(COUNTER_FILE):
        with open(COUNTER_FILE, "w", encoding="utf-8") as f:
            f.write("1")
        return 1
    try:
        with open(COUNTER_FILE, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except ValueError:
        return 1

def save_current_number(num):
    with open(COUNTER_FILE, "w", encoding="utf-8") as f:
        f.write(str(num))

def get_video_info(video_path):
    cmd = [
        FFPROBE_EXE, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,nb_read_packets",
        "-of", "json", video_path
    ]

    info = {"width": 1920, "height": 1080, "fps": 60, "total_frames": 1000}
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=NO_WINDOW_FLAGS)
        data = json.loads(result.stdout)
        stream = data.get("streams", [{}])[0]

        info["width"] = int(stream.get("width", 1920))
        info["height"] = int(stream.get("height", 1080))

        fps_str = stream.get("r_frame_rate", "60/1")
        if "/" in fps_str:
            num, den = map(float, fps_str.split("/"))
            info["fps"] = round(num / den) if den != 0 else 60
        else:
            info["fps"] = int(float(fps_str))

        if "nb_read_packets" in stream:
            info["total_frames"] = int(stream["nb_read_packets"])
    except Exception:
        try:
            cmd_dur = [FFPROBE_EXE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video_path]
            duration = float(subprocess.run(cmd_dur, stdout=subprocess.PIPE, text=True, creationflags=NO_WINDOW_FLAGS).stdout.strip())
            info["total_frames"] = int(duration * info["fps"])
        except Exception:
            pass

    return info


def build_render_jobs(video, title_name, info):
    """בונה את רשימת יעדי הרינדור (YouTube / TikTok / ריבועי אופציונלי) לסרטון נתון."""
    # loudnorm מעבד ב-192kHz, ובלי חזרה ל-48kHz ה-AAC יצא ב-96kHz (נמצא בסטודיו בהרצה אמיתית, 16.10.2026)
    loudnorm_args = ["-af", "loudnorm=I=-14:LRA=11:TP=-1.5,aresample=48000"] if ENABLE_LOUDNORM else []

    # קרופ חכם: מזיז את חלון הקרופ האנכי/מרובע לכיוון עיקר התזוזה בסרטון, במקום
    # קרופ מרכזי קבוע שעלול לחתוך פעולה שקורית בצדדים
    # 30.10.2026: הגודל לפי output_resolution (4K = 3840x2160 כמו קודם, "source" = הצלע הקצרה של המקור). הלוגו מצויר ל-4K -
    # ברזולוציה אחרת הוא והמרווח מהתחתית מוקטנים באותו יחס. בלי לוגו (ריק) אין קלט שני בכלל
    long_side, short = shorts_naming.frame_sides(OUTPUT_RESOLUTION, info["width"], info["height"])
    ratio = short / 2160
    tt_crop = f"crop={short}:{long_side}"
    sq_crop = f"crop={short}:{short}"
    if ENABLE_SMART_CROP and not DRY_RUN:
        try:
            from utils.media.smart_crop import compute_horizontal_crop_offset, offset_to_crop_x_expr
            offset = compute_horizontal_crop_offset(video)
            if abs(offset) > 0.05:
                tt_crop = f"crop={short}:{long_side}:{offset_to_crop_x_expr(offset, short)}:(in_h-{long_side})/2"
                sq_crop = f"crop={short}:{short}:{offset_to_crop_x_expr(offset, short)}:(in_h-{short})/2"
                print(f"  🎯 קרופ חכם: היסט {offset:+.2f} (כיוון עיקר התזוזה בסרטון)")
        except Exception as e:
            print(f"  ⚠️ קרופ חכם נכשל, משתמש בקרופ מרכזי רגיל: {e}")

    def _graph(background, margin):
        if not WATERMARK:
            return f"[0:v]{background}[outv]"
        wm_scale = "" if ratio == 1 else f"scale=iw*{ratio:.4f}:-2,"
        return (f"[1:v]{wm_scale}format=rgba,colorchannelmixer=aa={OPACITY:.2f}[wm];[0:v]{background}[bg];"
                f"[bg][wm]overlay=(W-w)/2:H-h-{round(margin * ratio)}[outv]")

    yt_filter = _graph(f"scale={long_side}:{short}:force_original_aspect_ratio=decrease,pad={long_side}:{short}:(ow-iw)/2:(oh-ih)/2", 120)
    tt_filter = _graph(f"scale={short}:{long_side}:force_original_aspect_ratio=increase,{tt_crop}", 120)
    sq_filter = _graph(f"scale={short}:{short}:force_original_aspect_ratio=increase,{sq_crop}", 80)
    inputs = ["-i", video] + (["-i", WATERMARK] if WATERMARK else [])
    size = "4K" if short == 2160 else f"{short}p"

    yt_output = os.path.join(YT_DIR, f"{title_name}.mp4")
    tt_output = os.path.join(TT_DIR, f"{title_name}.mp4")

    jobs = [
        {
            "label": f"  -> YouTube ({size} {info['fps']}FPS)",
            "output": yt_output,
            "cmd": [
                FFMPEG_EXE, "-y", *inputs,
                "-filter_complex", yt_filter,
                "-map", "[outv]", "-map", "0:a?", "-c:v", ENCODER, "-pix_fmt", "yuv420p",
                "-preset", FFMPEG_PRESET,
            ] + _quality_args(QUALITY_CQ) + ["-c:a", "aac", "-b:a", "320k"] + loudnorm_args + ["-movflags", "+faststart", yt_output]
        },
        {
            "label": f"  -> TikTok ({size} {info['fps']}FPS)",
            "output": tt_output,
            "cmd": [
                FFMPEG_EXE, "-y", *inputs,
                "-filter_complex", tt_filter,
                "-map", "[outv]", "-map", "0:a?", "-c:v", ENCODER, "-pix_fmt", "yuv420p",
                "-preset", FFMPEG_PRESET,
            ] + _quality_args(QUALITY_CQ + 2) + ["-c:a", "aac", "-b:a", "320k"] + loudnorm_args + ["-movflags", "+faststart", tt_output]
        },
    ]

    if ENABLE_SQUARE:
        sq_output = os.path.join(SQ_DIR, f"{title_name}.mp4")
        jobs.append({
            "label": f"  -> Square 1:1 ({size} {info['fps']}FPS)",
            "output": sq_output,
            "cmd": [
                FFMPEG_EXE, "-y", *inputs,
                "-filter_complex", sq_filter,
                "-map", "[outv]", "-map", "0:a?", "-c:v", ENCODER, "-pix_fmt", "yuv420p",
                "-preset", FFMPEG_PRESET,
            ] + _quality_args(QUALITY_CQ + 2) + ["-c:a", "aac", "-b:a", "320k"] + loudnorm_args + ["-movflags", "+faststart", sq_output]
        })

    return jobs

def run_jobs(jobs, total_frames):
    """מריץ את כל יעדי הרינדור לסרטון אחד, במקביל עד MAX_CONCURRENT_RENDERS בו-זמנית."""
    if DRY_RUN:
        for job in jobs:
            print(f"[DRY-RUN] היה מריץ: {job['label']} -> {job['output']}")
            print(f"[DRY-RUN] פקודה: {subprocess.list2cmdline(job['cmd'])}")
        return {job["output"]: True for job in jobs}

    results = {}
    if MAX_CONCURRENT_RENDERS <= 1:
        for i, job in enumerate(jobs):
            results[job["output"]] = run_ffmpeg_with_progress(job["cmd"], total_frames, job["label"], position=i)
        return results

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_RENDERS) as pool:
        futures = {
            pool.submit(run_ffmpeg_with_progress, job["cmd"], total_frames, job["label"], i): job
            for i, job in enumerate(jobs)
        }
        for future in futures:
            job = futures[future]
            results[job["output"]] = future.result()
    print()  # מפנה שורה אחרי שפסי ההתקדמות המקבילים נסגרים
    return results

def maybe_generate_thumbnail(video_output_path):
    if not ENABLE_THUMBNAILS or DRY_RUN:
        return
    try:
        from utils.media.thumbnail_generator import generate_thumbnail
        thumb_path = os.path.splitext(video_output_path)[0] + "_thumb.jpg"
        generate_thumbnail(video_output_path, thumb_path, ffmpeg_exe=FFMPEG_EXE, ffprobe_exe=FFPROBE_EXE)
        print(f"  🖼️  תמונה ממוזערת נוצרה: {os.path.basename(thumb_path)}")
    except Exception as e:
        print(f"  ⚠️ יצירת תמונה ממוזערת נכשלה (לא עוצר את הפייפליין): {e}")

def maybe_burn_captions(video_output_path):
    if not ENABLE_CAPTIONS or DRY_RUN:
        return video_output_path
    try:
        from utils.media.captions import burn_captions
        return burn_captions(video_output_path, ffmpeg_exe=FFMPEG_EXE, translate_to_english=ENABLE_CAPTIONS_TRANSLATE)
    except Exception as e:
        print(f"  ⚠️ הוספת כתוביות נכשלה (משתמש בגרסה בלי כתוביות): {e}")
        return video_output_path

def maybe_export_instagram(tiktok_output_path, title_name):
    """מעתיק את הפלט המוכן של TikTok (9:16, אחרי כתוביות אם מופעלות) לתיקיית
    Instagram Reels - אותו מפרט וידאו בדיוק, בלי רינדור GPU נוסף."""
    if not ENABLE_INSTAGRAM:
        return
    if DRY_RUN:
        print(f"[DRY-RUN] היה יוצר עותק Instagram Reels של {title_name}.")
        return
    try:
        ig_output = os.path.join(IG_DIR, f"{title_name}.mp4")
        shutil.copy2(tiktok_output_path, ig_output)
        print(f"  📸 עותק ל-Instagram Reels נוצר: {os.path.basename(ig_output)}")
    except Exception as e:
        print(f"  ⚠️ יצירת עותק ל-Instagram נכשלה (לא עוצר את הפייפליין): {e}")

def maybe_write_ai_metadata(video_path, primary_output_path):
    """
    כותב קובץ מטא-דאטה עם כותרת/תיאור/האשטגים שנוצרו ב-AI, לשימוש כתוכן ההעלאה
    בפועל. שם הקובץ המקומי (<title_prefix> #N) לא משתנה - מערכת המונה נשארת יציבה.
    המשחק: game_name מההגדרות, ואם הוא ריק - לפי שם הקליפ (כמו seo_generator).
    """
    if not ENABLE_AI_TITLES or DRY_RUN:
        return
    try:
        from utils.bot.title_generator import generate_metadata
        from utils.bot.seo_generator import detect_game_title
        game_name = GAME_NAME or detect_game_title(video_path)
        meta = generate_metadata(video_path, game_name if game_name != "Gameplay" else "gaming")
        meta_path = os.path.splitext(primary_output_path)[0] + "_ai_metadata.txt"
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write(f"Title: {meta['title']}\n")
            f.write(f"Description: {meta['description']}\n")
            f.write(f"Hashtags: {' '.join(meta['hashtags'])}\n")
        print(f"  🤖 מטא-דאטה AI נוצרה: {meta['title']}")
    except Exception as e:
        print(f"  ⚠️ מחולל הכותרות AI נכשל (לא עוצר את הפייפליין): {e}")

# סריקת קבצים
video_extensions = ("*.mp4", "*.mkv", "*.mov", "*.avi")
video_files = []
for ext in video_extensions:
    video_files.extend(glob.glob(os.path.join(VIDEO_DIR, ext)))

video_files = [v for v in video_files if os.path.basename(v) != os.path.basename(WATERMARK) and not os.path.basename(v).startswith("YT_") and not os.path.basename(v).startswith("TT_")]

if not video_files:
    print(f"❌ לא נמצאו סרטונים חדשים לעיבוד בתיקייה שנבחרה: {VIDEO_DIR}")
    sys.stdout.flush()
    sys.exit(0)

# לוגו שנבחר אבל הקובץ שלו חסר - כל רינדור היה נכשל ב-ffmpeg, קליפ אחרי קליפ. בלי לוגו (ריק) מרנדרים בלעדיו
if not DRY_RUN and WATERMARK and not os.path.isfile(WATERMARK):
    print(f"❌ קובץ הלוגו לא נמצא: {WATERMARK} - בחר תמונת לוגו אחרת בהגדרות Rocket Shorts, או נקה את השדה לרינדור בלי לוגו.")
    sys.stdout.flush()
    sys.exit(1)

current_num = get_next_number()

print(f"🎬 מתחיל עיבוד קבוצתי{' (DRY-RUN - סימולציה בלבד)' if DRY_RUN else ''}. מספר התחלתי: {current_num}")
print(f"נתיב מנוע FFmpeg: {FFMPEG_EXE}")
print(f"תיקיית קליפים (Import): {VIDEO_DIR}")
print(f"תיקיית ייצוא (Export): {OUTPUT_BASE_DIR}")
print(f"מקודד פעיל: {ENCODER} | שקיפות לוגו: {int(OPACITY * 100)}% | רינדורים מקביליים: {MAX_CONCURRENT_RENDERS}")
print(f"פורמט מרובע: {'פעיל' if ENABLE_SQUARE else 'כבוי'} | נרמול שמע: {'פעיל' if ENABLE_LOUDNORM else 'כבוי'} | Instagram Reels: {'פעיל' if ENABLE_INSTAGRAM else 'כבוי'}")
print("--------------------------------------------------")
sys.stdout.flush()

def _log_waiting_for_render_lock(_seconds_waited):
    print("⏳ ממתין לסיום רינדור אחר שרץ כרגע (GUI/דפדפן/בוט)...")
    sys.stdout.flush()

# render_lock_if_needed - מגן על עצמו גם כשמופעל ישירות (טרמינל), לא רק
# דרך worker.py/remote_execution.py (שכבר תופסים את אותו מנעול ומעבירים
# RENDER_LOCK_HELD_BY_CALLER כדי שהתפיסה כאן תדלג ולא תינעל על עצמה).
with render_lock_if_needed(on_wait=_log_waiting_for_render_lock):
    for video in video_files:
        info = get_video_info(video)
        title_name = f"{TITLE_PREFIX} #{current_num}"

        print(f"\n[מעבד] {os.path.basename(video)} -> {title_name}")
        print(f"  └─ נתוני מקור: {info['width']}x{info['height']} @ {info['fps']}FPS")
        sys.stdout.flush()

        estimated_total_frames = info["total_frames"] if info["total_frames"] > 100 else 1800

        jobs = build_render_jobs(video, title_name, info)

        # מספר יעדי רינדור (YouTube/TikTok/מרובע אופציונלי) + עותק Instagram אפשרי
        # (ראו maybe_export_instagram - העתק קובץ אמיתי, לא hardlink, אז דורש שטח
        # בעצמו) - כל יעד יכול לתפוס בערך את גודל המקור (4K re-encode).
        num_outputs = len(jobs) + (1 if ENABLE_INSTAGRAM else 0)
        required_bytes = estimate_required_bytes(video, safety_factor=1.0) * num_outputs
        if not has_enough_disk_space(OUTPUT_BASE_DIR, required_bytes):
            print(f"⏭️  שטח פנוי לא מספיק ב-{OUTPUT_BASE_DIR} עבור {os.path.basename(video)} - מדלג (במקום להיכשל באמצע רינדור).")
            sys.stdout.flush()
            continue
        results = run_jobs(jobs, estimated_total_frames)
        all_ok = all(results.values())

        if not all_ok:
            print(f"⏭️  מדלג על {os.path.basename(video)} - הרינדור נכשל, לא מקדם מונה ולא מעלה.")
            sys.stdout.flush()
            continue

        for job in jobs:
            maybe_generate_thumbnail(job["output"])

        yt_job = next((j for j in jobs if j["output"].startswith(YT_DIR)), None)
        if yt_job:
            maybe_write_ai_metadata(video, yt_job["output"])

        tt_job = next((j for j in jobs if j["output"].startswith(TT_DIR)), None)
        if tt_job:
            maybe_burn_captions(tt_job["output"])
            maybe_export_instagram(tt_job["output"], title_name)

        current_num += 1
        if not DRY_RUN:
            save_current_number(current_num)

        cookies_path = os.path.join(BASE_DIR, "tiktok_cookies.txt")
        if os.path.exists(cookies_path) and not DRY_RUN:
            tt_output = next((j["output"] for j in jobs if j["output"].startswith(TT_DIR)), None)
            print(f"מעלה את {title_name} ל-TikTok...")
            sys.stdout.flush()
            def _run_tiktok_upload(tt_output=tt_output, title_name=title_name, cookies_path=cookies_path):   # קשירה מפורשת לאיטרציה (B023)
                result = subprocess.run(["tiktok-uploader", "-v", tt_output, "-t", title_name, "-c", cookies_path], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, creationflags=NO_WINDOW_FLAGS)
                if result.returncode != 0:
                    # subprocess.run לא זורק על קוד יציאה שונה מ-0 - מעלים חריגה
                    # במפורש כדי ש-call_with_retry (שתופס Exception) יזהה כישלון בכלל.
                    raise RuntimeError(f"קוד יציאה {result.returncode}: {result.stderr[-500:] if result.stderr else ''}")
                return result

            def _log_tiktok_retry(attempt, delay, exc):
                print(f"⚠️ העלאה לטיקטוק נכשלה ({exc}) - ניסיון חוזר {attempt + 2}/3 בעוד {delay:.0f} שניות...")
                sys.stdout.flush()

            try:
                call_with_retry(_run_tiktok_upload, max_attempts=3, base_delay=5.0, on_retry=_log_tiktok_retry)
                print("✅ העלאה לטיקטוק הושלמה!")
            except Exception as e:
                print(f"❌ העלאה לטיקטוק נכשלה אחרי 3 ניסיונות: {e}")
            sys.stdout.flush()
        elif DRY_RUN and os.path.exists(cookies_path):
            print(f"[DRY-RUN] היה מעלה את {title_name} לטיקטוק.")

print("\n==================================================")
print(f"🎉 {'סימולציית DRY-RUN הסתיימה' if DRY_RUN else 'הסתיים בהצלחה'}! המונה הבא שיישמר: {current_num}")
print("==================================================")
sys.stdout.flush()
