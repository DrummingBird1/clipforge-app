# utils/bot/youtube_analytics.py
#
# מושך צפיות/לייקים/תגובות מצטברים-לנצח אחורה מ-YouTube (item: YouTube
# Analytics feedback loop) - עד כה utils/bot/youtube_uploader.py רק *העלה*
# סרטונים, חד-כיווני, בלי שום דרך לדעת איך הם בפועל ביצעו לאחר מכן.
#
# בכוונה *לא* דרך ה-YouTube Analytics API הנפרד (youtubeAnalytics v2, עם
# startDate/endDate/dimensions) - videos().list(part="statistics") של YouTube
# Data API v3 הרגיל כבר חושף בדיוק את שלוש המדדים המבוקשים (views/likes/
# comments, מצטבר-לנצח, לא טווח-תאריכים) בלי לצרוך quota/מורכבות של API נפרד.
# דורש scope חדש (youtube.readonly - ראו utils/bot/youtube_uploader.py.READONLY_SCOPE)
# מעבר ל-youtube.upload הקיים; טוקן ישן יעבור הסכמה מחודשת אוטומטית
# (ראו youtube_uploader._get_credentials).

from utils.bot.youtube_uploader import _get_credentials


def get_video_stats(video_id):
    """מחזיר {"views": int, "likes": int, "comments": int} עבור video_id בודד,
    או None אם הסרטון לא נמצא (נמחק וכו'). זורק את חריגת ה-API המקורית לכל
    כשל אחר (הרשאה חסרה, בעיית רשת וכו') - הקריאה האחראית מטפלת בהצגה למשתמש."""
    from googleapiclient.discovery import build

    creds = _get_credentials()
    youtube = build("youtube", "v3", credentials=creds)
    response = youtube.videos().list(part="statistics", id=video_id).execute()

    items = response.get("items", [])
    if not items:
        return None

    stats = items[0].get("statistics", {})
    return {
        "views": int(stats.get("viewCount", 0)),
        "likes": int(stats.get("likeCount", 0)),
        "comments": int(stats.get("commentCount", 0)),
    }


def set_video_thumbnail(video_id, image_path):
    """מגדיר את image_path כתמונה הממוזערת של video_id (item: A/B thumbnail
    testing - thumbnails().set דורש רק youtube.upload, אותו scope שכבר קיים
    מהעלאה - אין scope נוסף לזה, בניגוד ל-get_video_stats למעלה). זורק את
    חריגת ה-API המקורית לכל כשל - הקריאה האחראית מטפלת בהצגה למשתמש."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = _get_credentials()
    youtube = build("youtube", "v3", credentials=creds)
    media = MediaFileUpload(image_path)
    youtube.thumbnails().set(videoId=video_id, media_body=media).execute()


def get_audience_retention(video_id, today=None):
    """27.10.2026: שימור הצופים לאורך הסרטון - YouTube Analytics API (youtubeAnalytics v2), dimension
    elapsedVideoTimeRatio: מאה נקודות (0.01 עד 1) עם audienceWatchRatio (כמה מהצופים עוד צופים) ו-
    relativeRetentionPerformance (מול סרטונים באורך דומה). מחזיר את השורות כמו שהן ([יחס, שימור, יחסי]);
    זורק את חריגת ה-API לכל כשל (הרשאה, סרטון חדש מדי שעוד אין לו נתונים...)."""
    import datetime

    from googleapiclient.discovery import build

    creds = _get_credentials()
    analytics = build("youtubeAnalytics", "v2", credentials=creds)
    end = (today or datetime.date.today()).isoformat()
    response = analytics.reports().query(
        ids="channel==MINE", startDate="2005-01-01", endDate=end, metrics="audienceWatchRatio,relativeRetentionPerformance",
        dimensions="elapsedVideoTimeRatio", filters=f"video=={video_id}").execute()
    return response.get("rows") or []
