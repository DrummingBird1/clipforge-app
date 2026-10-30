# utils/media/ffprobe_cache.py
#
# מטמון תוצאות ffprobe (item 20) - כל סקריפט (video_editor.py, highlight_reel_maker.py
# וכו') קרא בעבר ל-ffprobe בנפרד לכל פרט (משך, רזולוציה, האם יש אודיו), ולפעמים
# יותר מפעם אחת על אותו קובץ בדיוק בתוך אותה ריצה. probe_video() כאן מבצעת קריאת
# ffprobe אחת בלבד לכל קובץ (JSON יחיד עם duration+width+height+has_audio יחד),
# עם מטמון דו-שכבתי:
#   1. זיכרון-תהליך (_memory_cache) - מהיר, לכל קריאה חוזרת באותה ריצת סקריפט.
#   2. קובץ על הדיסק (data/ffprobe_cache.json) - כדי שריצה הבאה של סקריפט אחר
#      על אותו קובץ (למשל פייפליין שרשור, item 15) גם תיהנה מהמטמון, לא רק
#      אותה ריצה בודדת. מפתח המטמון כולל mtime+size של הקובץ - שינוי בקובץ
#      (רינדור מחדש) פשוט לא פוגע במטמון (key חדש), לא דורש invalidation ידני.
import json
import os
import subprocess
import threading
from typing import Any, Dict

from utils.video import media_pool
from utils.shared.atomic_write import atomic_write_json
from utils.shared.ffmpeg_locator import get_ffprobe_exe
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
from utils.shared import data_paths

CACHE_PATH = data_paths.path(data_paths.FFPROBE_CACHE)

# תקרה על מספר הרשומות - בלי זה קובץ המטמון היה גדל ללא הגבלה על פני חודשים/שנים
# של שימוש (כל סרטון שאי-פעם עבר עיבוד נשאר לנצח). dict שומר סדר הכנסה (Python
# 3.7+), אז "הישנים ביותר" הם פשוט המפתחות הראשונים - LRU מקורב, לא מדויק
# (לא מתעדכן ב-access, רק ב-insert), אבל מספיק טוב למטרה (מנוע ביצועים, לא
# קורקטיות) בלי לדרוש מבנה נתונים נוסף.
MAX_CACHE_ENTRIES = 2000

_memory_cache: Dict[str, Any] = {}
_disk_cache_loaded = False
# item: בדיקת באגים מקיפה - probe_video נקראת בו-זמנית מכל worker-thread של
# video_editor.py's --parallel, אבל _memory_cache (וקובץ המטמון על הדיסק)
# לא היו מוגנים בכלל - שני threads שמעדכנים/מפנים-מקום בו-זמנית יכולים
# להפיל RuntimeError ("dictionary changed size during iteration") ולהפיל
# batch שלם, או לשבש את קובץ המטמון על הדיסק. RLock (לא Lock רגיל) כי
# _persist_cache נקראת גם ישירות וגם מתוך probe_video שכבר מחזיקה את
# המנעול - צריך שאותו thread יוכל לתפוס אותו שוב בלי deadlock.
_cache_lock = threading.RLock()

FFPROBE_EXE = get_ffprobe_exe()


def _cache_key(path):
    stat = os.stat(path)
    return f"{os.path.abspath(path)}|{stat.st_mtime_ns}|{stat.st_size}"


def _ensure_disk_cache_loaded():
    global _disk_cache_loaded
    with _cache_lock:
        if _disk_cache_loaded:
            return
        _disk_cache_loaded = True
        if os.path.exists(CACHE_PATH):
            try:
                with open(CACHE_PATH, "r", encoding="utf-8") as f:
                    _memory_cache.update(json.load(f))
            except Exception:
                pass  # קובץ מטמון פגום - פשוט מתחילים ממטמון ריק, לא קריטי


def _persist_cache():
    with _cache_lock:
        while len(_memory_cache) > MAX_CACHE_ENTRIES:
            _memory_cache.pop(next(iter(_memory_cache)))
        try:
            # אטומי (קובץ זמני + os.replace), לא open("w") ישיר: open("w") מרוקן את
            # הקובץ לפני הכתיבה, וקורא בו-זמני - thread אחר, או תהליך אחר לגמרי
            # (שרת הווב קורא/כותב את אותו data/ffprobe_cache.json במקביל לסקריפט
            # הרינדור) - היה יכול לקרוא קובץ ריק/חצי-כתוב. נמצא כשטסט ה-thread-safety
            # נכשל ב-CI (JSONDecodeError על קובץ ריק).
            atomic_write_json(CACHE_PATH, _memory_cache)
        except Exception as e:
            print(f"[ffprobe_cache] שגיאה בשמירת מטמון ffprobe: {e}")


def _is_usable_frame_rate(value):
    """True אם value (מחרוזת ffprobe בסגנון "30000/1001" או "0/0") מייצג קצב
    פריימים חיובי אמיתי - ffprobe מחזיר "0/0" לזרמים בלי קצב ידוע (למשל תמונה
    בודדת/סטרים לא-שגרתי), ואי אפשר לחלק באפס."""
    if not value:
        return False
    num_str, _, den_str = value.partition("/")
    den_str = den_str or "1"
    try:
        return float(num_str) > 0 and float(den_str) > 0
    except ValueError:
        return False


def _pick_frame_rate(r_frame_rate, avg_frame_rate):
    """r_frame_rate (הקצב הנומינלי שהקונטיינר עצמו מצהיר עליו) קודם ל-
    avg_frame_rate (ממוצע נגזר ממספר-פריימים/משך - יכול לצאת לא-מדויק לקבצים
    קצרים/מוזרים) - נופלים לאחרון רק אם הראשון חסר/לא-שמיש (item: שימור FPS
    מקורי). מחזיר את המחרוזת כמות שהיא (למשל "30000/1001") - לא ממיר למספר
    כאן, כדי לא לאבד דיוק על קצבים לא-שלמים כמו NTSC 29.97/59.94."""
    if _is_usable_frame_rate(r_frame_rate):
        return r_frame_rate
    if _is_usable_frame_rate(avg_frame_rate):
        return avg_frame_rate
    return None


def _run_ffprobe(path):
    cmd = [
        FFPROBE_EXE, "-v", "error",
        "-show_entries",
        "format=duration:stream=codec_type,width,height,r_frame_rate,avg_frame_rate,"
        "color_transfer,color_primaries,color_space,pix_fmt",
        "-of", "json", path,
    ]
    result = {
        "duration": None, "width": None, "height": None, "has_audio": False,
        "fps": None, "color_transfer": None, "color_primaries": None,
        "color_space": None, "pix_fmt": None,
    }
    try:
        # גל 24: probe לתור של מאות קבצים - בתוך תקרת נתיב ה-thumbs (utils/video/media_pool.py)
        proc = media_pool.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=15, creationflags=NO_WINDOW_FLAGS)
        data = json.loads(proc.stdout)
    except Exception:
        return result

    fmt = data.get("format", {})
    try:
        result["duration"] = float(fmt["duration"])
    except (KeyError, ValueError, TypeError):
        pass

    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and result["width"] is None:
            result["width"] = stream.get("width")
            result["height"] = stream.get("height")
            result["fps"] = _pick_frame_rate(stream.get("r_frame_rate"), stream.get("avg_frame_rate"))
            result["color_transfer"] = stream.get("color_transfer")
            result["color_primaries"] = stream.get("color_primaries")
            result["color_space"] = stream.get("color_space")
            result["pix_fmt"] = stream.get("pix_fmt")
        elif stream.get("codec_type") == "audio":
            result["has_audio"] = True

    return result


def probe_video(path):
    """מחזיר {"duration": float|None, "width": int|None, "height": int|None,
    "has_audio": bool, "fps": str|None, "color_transfer": str|None,
    "color_primaries": str|None, "color_space": str|None, "pix_fmt": str|None}
    עבור path - קריאת ffprobe יחידה (לא כמה קריאות נפרדות לכל פרט), עם מטמון
    (זיכרון-תהליך + דיסק, ראו תיעוד המודול). fps מוחזר כמחרוזת ffprobe גולמית
    (למשל "30000/1001") - ראו utils/video/video_editor.py's parse_fps_value לפירוש
    למספר. color_transfer/primaries/space הם השדות הרלוונטיים לזיהוי HDR
    (ראו utils/video/video_editor.py's is_hdr_source) - None על תוכן SDR רגיל
    (ffprobe פשוט לא מדווח את השדות האלה כשאין להם ערך רלוונטי).

    "fps" not in cached: מגן מפני מטמון-דיסק שנכתב *לפני* שהשדה הזה נוסף -
    רשומה ישנה כזו לא הייתה "שקרית" בכוונה, פשוט מגרסה קודמת של הפונקציה
    הזו; מתייחסים אליה כ-cache miss ומריצים ffprobe מחדש פעם אחת, במקום
    להחזיר בשקט dict חסר-שדות שיפיל שגיאה אצל כל קורא חדש שמצפה להם."""
    _ensure_disk_cache_loaded()
    key = _cache_key(path)
    with _cache_lock:
        cached = _memory_cache.get(key)
    if cached is not None and "fps" in cached:
        return cached

    result = _run_ffprobe(path)  # לא תחת המנעול בכוונה - subprocess יקר, לא מגן על משהו משותף
    with _cache_lock:
        _memory_cache[key] = result
        _persist_cache()
    return result
