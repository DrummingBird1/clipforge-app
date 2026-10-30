# utils/shared/disk_space.py
#
# בדיקת שטח פנוי מראש לפני רינדור ארוך - בלי זה, דיסק שמתמלא באמצע רינדור 4K
# (קבצים של עשרות GB לא נדירים בפייפליין הזה) גורם ל-ffmpeg להיכשל בצורה לא
# ברורה אחרי שכבר הושקעו דקות/שעה של זמן GPU, במקום להיכשל מיד עם הודעה ברורה.

import os
import shutil

# רצפת ביטחון קבועה מעבר להערכה - גם אם ההערכה מדויקת להפליא, לא רוצים
# שהדיסק יגיע ל-0 בייטים פנויים בדיוק (מערכת ההפעלה עצמה זקוקה לשטח לעבוד).
DEFAULT_MIN_FREE_BYTES = 2 * 1024 ** 3  # 2GB


def estimate_required_bytes(input_path: str, safety_factor: float = 1.5) -> int:
    """הערכה גסה של שטח הפלט הנדרש - לא ניתן לדעת בוודאות (תלוי בקידוד/
    איכות/משכי זמן שונים בין ffmpeg runs), אז מניחים שהפלט לא יעלה על גודל
    הקלט כפול מקדם ביטחון. מחזיר 0 אם קובץ הקלט לא נגיש (לא חוסמים על בסיס
    כשל בבדיקה עצמה - ראו has_enough_disk_space)."""
    try:
        return int(os.path.getsize(input_path) * safety_factor)
    except OSError:
        return 0


def estimate_required_bytes_for_duration(output_seconds: float, num_outputs: int = 1, bitrate_mbps: float = 8) -> int:
    """הערכה חלופית ל-estimate_required_bytes, לסקריפטים שהפלט שלהם הוא אורך
    קבוע ידוע מראש (timelapse_maker.py: תמיד TARGET_SECONDS, בלי קשר לאורך
    הקלט) - שם "גודל קלט * מקדם" הוא הערכה שגויה לגמרי (מקור של שעות שנדחס
    ל-60 שניות מפיק פלט קטן בהרבה מהקלט, לא גדול ממנו)."""
    return int(output_seconds * bitrate_mbps * 1_000_000 / 8 * num_outputs)


def has_enough_disk_space(output_dir: str, required_bytes: int, min_free_bytes: int = DEFAULT_MIN_FREE_BYTES) -> bool:
    """בודק אם יש מספיק שטח פנוי בכונן של output_dir - required_bytes (הערכה,
    ראו estimate_required_bytes) בתוספת רצפת בטיחות קבועה. אם output_dir עדיין
    לא קיים (ייווצר ע"י os.makedirs לפני הרינדור בפועל), בודקים את תיקיית האב
    הקיימת הקרובה ביותר - shutil.disk_usage דורש נתיב קיים."""
    check_path = output_dir
    while check_path and not os.path.exists(check_path):
        parent = os.path.dirname(check_path)
        if parent == check_path:
            break
        check_path = parent
    if not check_path or not os.path.exists(check_path):
        return True  # לא ניתן לבדוק - לא חוסמים על בסיס כשל בבדיקה עצמה

    try:
        _total, _used, free = shutil.disk_usage(check_path)
    except OSError:
        return True
    return free >= (required_bytes + min_free_bytes)
