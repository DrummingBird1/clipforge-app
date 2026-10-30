# utils/shared/ffmpeg_locator.py
#
# מקור אמת יחיד לאיתור ffmpeg/ffprobe - קודם הגרסה המצורפת בפרויקט (ffmpeg/bin/),
# ואם היא לא קיימת נופל חזרה לפקודה הגלובלית (מותקנת ב-PATH). לפני זה הלוגיקה
# הזו הייתה משוכפלת (עם נתיב מוחלט קשיח לדיסק E: של המפתח כניסיון ראשון) בארבעה
# קבצים שונים בפרויקט; story_cutter.py בכלל לא השתמש בה וקרא ל-"ffmpeg"/"ffprobe"
# הגלובליים בלבד, מה שהפך אותו לחריג היחיד שנשבר בלי ffmpeg מותקן ב-PATH.

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_BIN_DIR = os.path.join(BASE_DIR, "ffmpeg", "bin")


def get_ffmpeg_exe():
    bundled = os.path.join(_BIN_DIR, "ffmpeg.exe")
    return bundled if os.path.exists(bundled) else "ffmpeg"


def get_ffprobe_exe():
    bundled = os.path.join(_BIN_DIR, "ffprobe.exe")
    return bundled if os.path.exists(bundled) else "ffprobe"
