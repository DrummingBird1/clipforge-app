# utils.video.video_editor_effort - split out of the original module (no behavior change); the original module re-exports every name.

from typing import Any, Dict, List, Optional, Tuple


# item: דרגות מאמץ קידוד (--effort, my_scripts/video/video_editor.py) - חוגה
# ידידותית יחידה למשאבי-מחשב במקום דגלים נפרדים - "high" (ברירת מחדל) זהה
# בדיוק להתנהגות הקודמת (בלי הגבלת threads, בלי דריסת NVENC preset). "auto"
# (item: זיהוי עומס-מחשב אוטומטי) הוא ערך גולמי בלבד שהקורא (video_editor.py)
# חייב לפענח פר-קובץ ל-low/medium/high בפועל דרך resolve_auto_effort() לפני
# שמעביר אותו ל-resolve_effort_thread_count/EFFORT_NVENC_PRESET למטה - שתיהן
# לא מכירות "auto" בעצמן.
EFFORT_LEVELS: Tuple[str, ...] = ("low", "medium", "high", "auto")


# ל-NVENC (hevc/av1) בלבד, ורק כש---nvenc-preset לא ניתן במפורש - "low"/
# "medium" מורידים לפריסט מהיר/קל-יותר-על-ה-GPU מברירת המחדל של הקודק
# (p5, ב-CODEC_ARGS למעלה). "high" (None) = לא דורס כלום.
EFFORT_NVENC_PRESET: Dict[str, Optional[str]] = {"low": "p2", "medium": "p4", "high": None}


def resolve_auto_effort(cpu_percent: Optional[float], gpu_percent: Optional[float]) -> str:
    """--effort auto (item: זיהוי עומס-מחשב אוטומטי) - ממיר קריאת עומס בפועל
    (utils.shared.hardware.get_system_stats/get_gpu_stats, my_scripts/video/video_editor.py)
    לרמת מאמץ קונקרטית (low/medium/high). None (item: אין GPU NVIDIA/psutil
    לא מותקן) מטופל כ"לא ידוע" בציר הזה בלבד - לא כ"0% עומס" - כדי שמידע
    חלקי (למשל אין GPU) לא יטה בטעות תמיד ל-"high". שני הצירים לא ידועים
    (None,None) חוזר ל-"high" (זהה לברירת המחדל הקודמת, בלי מידע-בכלל להחליט
    לפיו). העומס הגבוה מבין השניים (CPU/GPU) קובע - מגבלת המשאב הצר יותר."""
    known = [v for v in (cpu_percent, gpu_percent) if v is not None]
    if not known:
        return "high"
    load = max(known)
    if load >= 70:
        return "low"
    if load >= 40:
        return "medium"
    return "high"


# hevc_nvenc/av1_nvenc תואמים בכוונה לפרופילי האיכות הקיימים כבר ב-
# ui/rocket_settings_tab.py (PRESETS) - עקביות קידוד לאורך כל הפרויקט, ומנצלים
# את ה-GPU (NVIDIA NVENC) שכבר בשימוש שם, לא CPU איטי, לקידוד HEVC/AV1.
CODEC_ARGS: Dict[str, List[str]] = {
    "h264": ["-c:v", "libx264", "-preset", "medium", "-crf", "20"],
    "hevc": ["-c:v", "hevc_nvenc", "-preset", "p5", "-cq", "19"],
    "av1": ["-c:v", "av1_nvenc", "-preset", "p5", "-cq", "24"],
}


# שילובי הגדרות מוכנים לפעולות עריכה חוזרות - זהה בעיקרון ל-PRESETS ב-
# ui/rocket_settings_tab.py. לא כולל watermark_path (ספציפי-למשתמש, לא חלק
# מ"סוג עריכה" כללי) - רק vertical/target_seconds/keep_audio/loudnorm/codec.
# מקור אמת יחיד: גם ה-GUI השולחני (ui/settings_tab.py) וגם ה-web app
# (web_app.py, דרך /api/video_editor_presets) קוראים מכאן, לא משכפלים.
VIDEO_EDITOR_PRESETS: Dict[str, Dict[str, Any]] = {
    "📱 טיקטוק/שורטס מהיר": {"vertical": True, "target_seconds": 60, "keep_audio": True, "loudnorm": True, "codec": "hevc"},
    "⏩ טיימלאפס שקט": {"vertical": False, "target_seconds": 60, "keep_audio": False, "loudnorm": False, "codec": "h264"},
    "🎬 יוטיוב איכות מלאה": {"vertical": False, "target_seconds": 0, "keep_audio": True, "loudnorm": True, "codec": "hevc"},
    "💻 תאימות מקסימלית (CPU)": {"vertical": False, "target_seconds": 0, "keep_audio": True, "loudnorm": False, "codec": "h264"},
}
