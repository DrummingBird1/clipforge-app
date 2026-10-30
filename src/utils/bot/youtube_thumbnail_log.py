# utils/bot/youtube_thumbnail_log.py
#
# רושם תמונות ממוזערות מועמדות שנוצרו לכל סרטון + היסטוריית החלפות בפועל
# (item: A/B thumbnail testing) - אותו DB משותף, בדיוק כמו
# utils/bot/youtube_publish_log.py הסמוך.
#
# views_at_switch (לא רק "מתי הוחלף") הוא מה שהופך את זה משורת-לוג גרידא
# ל"בדיקת A/B" שימושית בפועל: תמונה ממוזערת קיימת + views_at_switch, מול
# הצפיות המצטברות הנוכחיות (utils/bot/youtube_publish_log.py, מרוענן דרך
# utils/bot/youtube_analytics.py) - ההפרש הוא "כמה צפיות נצברו מאז ההחלפה הזו".
# בכוונה *לא* בדיקת A/B בו-זמנית - YouTube Data API לא חושף את "Test & Compare"
# הפנימי של YouTube Studio; זו השוואה רציפה (לפני/אחרי), לא פיצול-תנועה אמיתי.

from datetime import datetime

from utils.shared import db
from utils.shared import data_paths

DB_PATH = data_paths.path(data_paths.BOT_DB)


def _ensure_tables():
    with db.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS youtube_thumbnail_candidates (
                video_id TEXT NOT NULL,
                candidate_index INTEGER NOT NULL,
                image_path TEXT NOT NULL,
                PRIMARY KEY (video_id, candidate_index)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS youtube_thumbnail_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                candidate_index INTEGER,
                set_at TEXT,
                views_at_switch INTEGER
            )
        """)


def record_candidates(video_id, candidate_paths):
    """שומר את נתיבי התמונות המועמדות שנוצרו לסרטון (index 0-based, לפי סדר
    candidate_paths) - מוחק קודם כל שורה קיימת לאותו video_id, לא רק
    INSERT OR REPLACE לפי index: קריאה חוזרת עם *פחות* מועמדים מבעבר הייתה
    אחרת משאירה שאריות מה-set הקודם (index שלא נדרס). לא קורא ל-YouTube -
    רק רישום מקומי."""
    _ensure_tables()
    with db.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM youtube_thumbnail_candidates WHERE video_id = ?", (video_id,))
        for index, path in enumerate(candidate_paths):
            conn.execute(
                "INSERT INTO youtube_thumbnail_candidates (video_id, candidate_index, image_path) VALUES (?, ?, ?)",
                (video_id, index, path),
            )


def get_candidates(video_id):
    """[(candidate_index, image_path), ...] ממוין לפי index."""
    _ensure_tables()
    with db.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT candidate_index, image_path FROM youtube_thumbnail_candidates WHERE video_id = ? ORDER BY candidate_index",
            (video_id,),
        ).fetchall()
    return rows


def record_switch(video_id, candidate_index, views_at_switch):
    """נקרא מיד אחרי set_video_thumbnail מוצלח בפועל (utils/bot/youtube_analytics.py) -
    views_at_switch הוא ה-views המצטבר-לנצח הידוע כרגע (מהמטמון ב-
    utils/bot/youtube_publish_log.py, לא קריאת API נוספת)."""
    _ensure_tables()
    with db.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO youtube_thumbnail_history (video_id, candidate_index, set_at, views_at_switch) VALUES (?, ?, ?, ?)",
            (video_id, candidate_index, datetime.now().isoformat(timespec="seconds"), views_at_switch),
        )


def get_latest_switch(video_id):
    """(candidate_index, set_at, views_at_switch) של ההחלפה האחרונה, או None
    אם מעולם לא הוחלפה תמונה ממוזערת לסרטון הזה."""
    _ensure_tables()
    with db.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT candidate_index, set_at, views_at_switch FROM youtube_thumbnail_history "
            "WHERE video_id = ? ORDER BY id DESC LIMIT 1",
            (video_id,),
        ).fetchone()
    return row
