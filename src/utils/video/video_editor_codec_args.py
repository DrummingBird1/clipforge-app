# utils.video.video_editor_codec_args - split out of the original module (no behavior change); the original module re-exports every name.

from typing import List, Optional

from utils.video.video_editor_effort import CODEC_ARGS


def get_codec_args(codec: str, preset: Optional[str] = None, cq: Optional[int] = None) -> List[str]:
    """מחזיר את דגלי ffmpeg (-c:v ...) עבור קידוד נתון. ValueError על קידוד לא מוכר -
    עדיף כישלון מיידי וברור מאשר ffmpeg שנכשל מאוחר יותר עם שגיאה עמומה.

    preset/cq (my_scripts/video/video_editor.py's --nvenc-preset/--nvenc-cq):
    דורסים את ברירת המחדל שב-CODEC_ARGS. שימושי בעיקר יחד עם --hwaccel - בלי
    hwaccel המקודד לרוב מחכה לפריימים מסוננים ב-CPU (לא ה-bottleneck בפועל,
    ראו build_edit_filter_complex), אז שינוי preset כמעט לא משפיע על זמן
    הריצה הכולל; עם hwaccel המקודד עצמו יכול להיות ה-bottleneg, ואז p1 (מהיר)
    מול p7 (איכות מרבית) הוא טרייד-אוף אמיתי. cq מיושם על "-cq" (NVENC) או
    "-crf" (h264) - מה שקיים בפועל ב-CODEC_ARGS של הקודק הזה."""
    try:
        args = list(CODEC_ARGS[codec])
    except KeyError:
        raise ValueError(f"קידוד לא מוכר: {codec!r} (אפשרויות: {', '.join(CODEC_ARGS)})")
    if preset is not None and "-preset" in args:
        args[args.index("-preset") + 1] = preset
    if cq is not None:
        cq_flag = "-cq" if "-cq" in args else ("-crf" if "-crf" in args else None)
        if cq_flag:
            args[args.index(cq_flag) + 1] = str(cq)
    return args


def compute_target_bitrate_kbps(target_size_mb: float, duration_seconds: float, audio_kbps: int = 0) -> int:
    """
    מחשב ביטרייט וידאו (kbps) שיפיק בקירוב את גודל הקובץ המבוקש (target_size_mb)
    לאורך duration_seconds - "יעד גודל" קלאסי לקידוד two-pass VBR (item: two-pass
    VBR quality mode - שימושי למשל כדי להתאים קליפ למגבלת גודל של דיסקורד/טוויטר).
    מפחית את הביטרייט של האודיו (אם יש) מסך הביטרייט הכולל כדי לא לחרוג מהיעד.
    לא יורד מתחת ל-100 kbps (רצפת בטיחות) גם אם היעד קטן מדי לאורך הסרטון -
    מוטב פלט נמוך-איכות אבל תקין מאשר ביטרייט אפסי/שלילי.
    """
    if target_size_mb <= 0 or duration_seconds <= 0:
        raise ValueError("target_size_mb ו-duration_seconds חייבים להיות חיוביים")
    total_kbps = (target_size_mb * 8192) / duration_seconds  # מגה-בייט -> קילו-ביט: *8*1024
    return max(100, int(total_kbps - audio_kbps))


def get_two_pass_codec_args(codec: str, bitrate_kbps: int, pass_num: int, passlog_path: str, preset: Optional[str] = None) -> List[str]:
    """
    ארגומנטי ffmpeg לקידוד VBR עם יעד ביטרייט קונקרטי (bitrate_kbps) - חלופה
    ל-get_codec_args() הרגיל (CQ/CRF, יעד איכות בלי גודל קובץ צפוי) כשיש יעד
    *גודל קובץ* קונקרטי (item: two-pass VBR quality mode).

    h264 (libx264, CPU) - two-pass קלאסי: pass_num=1 כותב סטטיסטיקה בלבד
    ל-passlog_path (הקורא אחראי לכוון את הפלט ל-null/-f null באותה קריאה),
    pass_num=2 קורא אותה ומפיק את הקידוד האמיתי. hevc/av1 (NVENC) - "-multipass
    fullres", מקבילת NVENC המודרנית (אימות ידני מול GPU אמיתי בבנייה הזו של
    ffmpeg - יש לה גם, מוזר ככל שיישמע, "-b:v"+"-rc vbr" כמו h264 אבל ב-קריאה
    בודדת אחת בלבד, NVENC לא תומך בקבצי pass-log כמו libx264) - pass_num
    מתעלם עבור הקודקים האלה (אין פה שתי קריאות ffmpeg נפרדות בכלל).
    """
    if codec not in CODEC_ARGS:
        raise ValueError(f"קידוד לא מוכר: {codec!r} (אפשרויות: {', '.join(CODEC_ARGS)})")
    if pass_num not in (1, 2):
        raise ValueError("pass_num חייב להיות 1 או 2")
    bitrate_arg = f"{bitrate_kbps}k"
    maxrate_arg = f"{int(bitrate_kbps * 1.5)}k"
    if codec == "h264":
        args = ["-c:v", "libx264", "-preset", "medium", "-b:v", bitrate_arg, "-pass", str(pass_num), "-passlogfile", passlog_path]
    else:
        nvenc_codec = "hevc_nvenc" if codec == "hevc" else "av1_nvenc"
        args = ["-c:v", nvenc_codec, "-preset", "p5", "-rc", "vbr", "-b:v", bitrate_arg, "-maxrate", maxrate_arg, "-multipass", "fullres"]
    if preset is not None:
        args[args.index("-preset") + 1] = preset
    return args
