# utils/bot/youtube_publish_log.py
#
# רושם כל סרטון שהועלה בפועל ל-YouTube (item: YouTube Analytics feedback loop) -
# עד כה video_id שהעלאה מחזירה (utils/youtube_uploader.upload_video) לא נשמר
# באף מקום קבוע (רק מוצג רגעית בתווית סטטוס/state בזיכרון) - אין שום דרך
# לדעת מאוחר יותר "אילו סרטונים שלי בכלל קיימים ב-YouTube" כדי לשלוף את
# הסטטיסטיקות שלהם (utils/bot/youtube_analytics.py). נכתב מכל מקום שמעלה בהצלחה
# (web_app.py/ui/stats_tab.py) - שני הצדדים כותבים לאותו DB משותף (data_paths.BOT_DB).
#
# מגבלה ידועה, לא באג: רק העלאות *מרגע שהתכונה הזו נוספה* יופיעו כאן -
# סרטונים שהועלו לפני כן (בלי רישום) לא ניתנים לשחזור רטרואקטיבית.

from datetime import datetime

from utils.shared import db
from utils.shared import data_paths

DB_PATH = data_paths.path(data_paths.BOT_DB)


def _ensure_table():
    with db.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS youtube_published_videos (
                video_id TEXT PRIMARY KEY,
                clip_filename TEXT,
                title TEXT,
                uploaded_at TEXT,
                views INTEGER,
                likes INTEGER,
                comments INTEGER,
                stats_updated_at TEXT
            )
        """)


def record_upload(video_id, clip_filename, title):
    """נקרא מיד אחרי העלאה מוצלחת. views/likes/comments מתחילים כ-NULL (עוד
    לא נשלפו בפועל) - לא 0, כדי שה-UI יבדיל בין "עוד לא רוענן" ל"0 צפיות
    אמיתי בפועל"."""
    _ensure_table()
    with db.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO youtube_published_videos (video_id, clip_filename, title, uploaded_at) VALUES (?, ?, ?, ?)",
            (video_id, clip_filename, title, datetime.now().isoformat(timespec="seconds")),
        )


def get_published_videos(limit=50):
    """[(video_id, clip_filename, title, uploaded_at, views, likes, comments, stats_updated_at), ...]
    מהחדש לישן."""
    _ensure_table()
    with db.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT video_id, clip_filename, title, uploaded_at, views, likes, comments, stats_updated_at "
            "FROM youtube_published_videos ORDER BY uploaded_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return rows


def update_cached_stats(video_id, views, likes, comments):
    _ensure_table()
    with db.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE youtube_published_videos SET views = ?, likes = ?, comments = ?, stats_updated_at = ? WHERE video_id = ?",
            (views, likes, comments, datetime.now().isoformat(timespec="seconds"), video_id),
        )
