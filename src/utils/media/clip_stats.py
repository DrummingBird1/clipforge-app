# utils/media/clip_stats.py
#
# "קליפים שנלכדו לאורך זמן" (item: personal stats dashboard) - נגזר ישירות
# מ-mtime של קבצים קיימים ב-workspace/clips, בלי טבלת DB חדשה: אין צורך, ה-
# מידע כבר קיים על הדיסק (בניגוד ל-utils/media/game_playtime.py's "שעות משחק", ששם
# באמת אין שום נתון היסטורי קיים לפני שמתחילים לצבור).
#
# בכוונה בלי פירוק "לפי משחק" - צינור הלכידה/עריכה כרגע ממוקד Rocket League
# בלבד (ראו my_scripts/video/rocket_shorts_publisher.py), וגם game_detector.py
# לא משייך משחק לקובץ קליפ בודד; פירוק כזה הוא בדיוק ה"הרחבה למספר משחקים"
# שהמשתמש ביקש לדלג עליה בינתיים.

import glob
import os
from datetime import date, timedelta


def get_clips_captured_by_day(clips_dir, days=30):
    """{iso_date: count} עם days ימים אחרונים (כולל היום), מהישן לחדש, כולל
    ימים בלי אף קליפ (0 מפורש) - כדי שגרף יוכל לצייר ציר-זמן רציף בלי לחשב
    בעצמו אילו תאריכים חסרים."""
    today = date.today()
    counts = {(today - timedelta(days=i)).isoformat(): 0 for i in range(days - 1, -1, -1)}
    cutoff = today - timedelta(days=days - 1)
    for path in glob.glob(os.path.join(clips_dir, "*.mp4")):
        try:
            clip_day = date.fromtimestamp(os.path.getmtime(path))
        except OSError:
            continue
        if clip_day >= cutoff:
            key = clip_day.isoformat()
            if key in counts:
                counts[key] += 1
    return counts
