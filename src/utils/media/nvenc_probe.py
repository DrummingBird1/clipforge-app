# utils/media/nvenc_probe.py
#
# item: מודעות למגבלת סשנים אמיתית של NVENC - MAX_CONCURRENT_RENDERS
# (my_scripts/video/rocket_shorts_publisher.py, --hwaccel ב-video_editor.py)
# עד היום היה מספר שהמשתמש מקליד בעצמו, בלי שום דרך לדעת אם הכרטיס בפועל
# תומך בכך. NVIDIA לא חושפת API פשוט ל"כמה סשני NVENC מקבילים מותרים" - זה
# תלוי דגם כרטיס+גרסת דרייבר, ומשתנה עם הזמן (הרבה דרייברים מודרניים כבר לא
# מגבילים כרטיסי GeForce צרכניים כמו שהיה נהוג פעם). טבלת-חיפוש לפי דגם הייתה
# מתיישנת מיד; הדרך האמינה היחידה היא לבדוק בפועל - להריץ כמה קידודי NVENC
# זעירים בו-זמנית ולספור כמה הצליחו יחד.

import subprocess
from concurrent.futures import ThreadPoolExecutor

DEFAULT_MAX_TO_TRY = 8
_PROBE_DURATION_SECONDS = 1
_PROBE_TIMEOUT_SECONDS = 30
# 25.10.2026: היה 64x64 - מתחת למינימום של NVENC (h264_nvenc ו-hevc_nvenc דוחים 128x128 ומטה ב-"Frame Dimension
# less than the minimum supported value" על RTX 4070 SUPER, דרייבר 621), אז הבדיקה החזירה תמיד 0 גם על כרטיס תקין.
# 256x144 - כמו הבדיקה של dataviz.render.nvenc_available (256x256), מעל המינימום בכל הכרטיסים.
_PROBE_SIZE = "256x144"


def _run_single_probe_encode(ffmpeg_exe, codec, creationflags):
    """קידוד NVENC זעיר אחד (256x144, שנייה אחת, בלי אודיו) - הכי קטן/מהיר
    שעדיין באמת פותח סשן NVENC אמיתי. False על כל כישלון (כולל timeout) -
    לא מבדיל בין "אין GPU"/"מגבלת סשנים הושגה"/כל שגיאה אחרת, כי כל אלה
    אומרים אותו דבר לקורא: הסשן הזה לא זמין במקביל לשאר."""
    cmd = [
        ffmpeg_exe, "-y", "-f", "lavfi",
        "-i", f"color=black:size={_PROBE_SIZE}:duration={_PROBE_DURATION_SECONDS}:rate=5",
        "-c:v", codec, "-f", "null", "-",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=_PROBE_TIMEOUT_SECONDS, creationflags=creationflags)
        return result.returncode == 0
    except Exception:
        return False


def probe_max_concurrent_nvenc_sessions(ffmpeg_exe, codec="hevc_nvenc", max_to_try=DEFAULT_MAX_TO_TRY, creationflags=0):
    """מריץ עד max_to_try קידודי NVENC זעירים בו-זמנית אמיתיים (לא סימולציה)
    ומחזיר כמה הצליחו יחד - זו המגבלה האמיתית של הכרטיס/דרייבר הזה עכשיו,
    לא ניחוש/טבלת-חיפוש. 0 אם אף אחד לא הצליח (NVENC לא זמין/לא נתמך בכלל -
    למשל אין GPU של NVIDIA, או ffmpeg נבנה בלי nvenc)."""
    if max_to_try <= 0:
        return 0
    with ThreadPoolExecutor(max_workers=max_to_try) as pool:
        futures = [pool.submit(_run_single_probe_encode, ffmpeg_exe, codec, creationflags) for _ in range(max_to_try)]
        results = [f.result() for f in futures]
    return sum(1 for ok in results if ok)
