# utils/bot/youtube_uploader.py
#
# העלאה אמיתית ל-YouTube דרך YouTube Data API v3, במקום פתיחת דפדפן להעלאה ידנית.
#
# דורש הגדרה חד-פעמית מהצד שלך לפני שזה יעבוד (לא ניתן לבצע את זה מהקוד -
# זו פעולה בחשבון Google Cloud שלך):
#   1. היכנס ל-https://console.cloud.google.com/ וצור פרויקט חדש (או השתמש בקיים).
#   2. הפעל את "YouTube Data API v3" תחת Library.
#   3. במסך "OAuth consent screen" צור מסך הסכמה מסוג External (מספיק במצב Testing),
#      והוסף את חשבון ה-Google שלך כ-Test User.
#   4. תחת "Credentials" צור OAuth client ID מסוג "Desktop app".
#   5. הורד את קובץ ה-JSON ושמור אותו בשורש הפרויקט בשם client_secret.json.
# בפעם הראשונה שמעלים סרטון ייפתח דפדפן לאישור הרשאה; לאחר מכן הטוקן נשמר
# ל-youtube_token.json ולא תצטרך לאשר שוב.
#
# אם youtube_token.json כבר קיים מלפני הוספת אנליטיקס (item: YouTube Analytics
# feedback loop) - בפעם הראשונה שמרעננים סטטיסטיקות (לא מעלים) ייפתח דפדפן
# להסכמה נוספת אוטומטית (ראו _get_credentials), כי הטוקן הישן לא כולל את
# ה-scope הנדרש לקריאת נתונים. זה קורה פעם אחת בלבד, אותו עיקרון בדיוק
# כמו ההסכמה הראשונית.

import os

from utils.shared.retry import call_with_retry

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CLIENT_SECRETS_FILE = os.path.join(BASE_DIR, "client_secret.json")
TOKEN_FILE = os.path.join(BASE_DIR, "youtube_token.json")

UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
# item: YouTube Analytics feedback loop - views/likes/comments דרך videos().list
# (YouTube Data API v3, לא ה-API הנפרד "YouTube Analytics") דורש את ה-scope
# הזה; youtube.upload לבדו *לא* מספיק לקריאה (רק להעלאה/ניהול). ראו utils/bot/youtube_analytics.py.
READONLY_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
# 27.10.2026: שימור צופים לאורך הסרטון (audienceWatchRatio) - רק ב-YouTube Analytics API, שדורש scope משלו.
# טוקן ישן יעבור הסכמה מחודשת אוטומטית, כמו כשנוסף READONLY_SCOPE
ANALYTICS_SCOPE = "https://www.googleapis.com/auth/yt-analytics.readonly"
SCOPES = [UPLOAD_SCOPE, READONLY_SCOPE, ANALYTICS_SCOPE]

# קודי HTTP שכדאי לנסות שוב עליהם (עומס/תקלה זמנית בצד השרת) - זהה לרשימה
# המומלצת בדוגמת ההעלאה הרזומבלית הרשמית של Google.
_RETRYABLE_HTTP_STATUSES = (500, 502, 503, 504)


def _is_retryable_upload_error(exc):
    """True אם סביר שניסיון חוזר יעזור - שגיאת HTTP 5xx זמנית, או בעיית רשת/socket.
    שגיאות אחרות (401 הרשאה, 400 בקשה פגומה וכו') לא ייפתרו בניסיון חוזר."""
    status = getattr(getattr(exc, "resp", None), "status", None)
    if status in _RETRYABLE_HTTP_STATUSES:
        return True
    return isinstance(exc, (ConnectionError, TimeoutError, OSError))


def is_configured():
    """True אם קובץ ההרשאות של Google Cloud קיים - כלומר בוצעה ההגדרה החד-פעמית."""
    return os.path.exists(CLIENT_SECRETS_FILE)


def _get_credentials():
    """מבקש תמיד את איחוד ה-scopes המלא (SCOPES, upload+readonly) - כך שהעלאה
    ואנליטיקס חולקים טוקן יחיד, בלי שתי הסכמות נפרדות. טוקן ישן (מלפני
    שנוסף READONLY_SCOPE) לא כולל את ה-scope הזה - google.oauth2.credentials
    שומר את ה-scopes שבאמת אושרו בפועל בתוך הקובץ עצמו (creds.scopes), לא רק
    את מה שהועבר ל-from_authorized_user_file - אז השוואה מפורשת נדרשת כדי
    לזהות "טוקן תקף אבל עם הרשאות חסרות" ולהפעיל הסכמה מחדש (במקום לתת
    לקריאת ה-API עצמה להיכשל בהמשך עם שגיאת 403 לא-ברורה)."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    has_all_scopes = bool(creds) and set(SCOPES) <= set(creds.scopes or [])

    if not creds or not creds.valid or not has_all_scopes:
        if creds and creds.expired and creds.refresh_token and has_all_scopes:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return creds


def upload_video(file_path, title, description="", tags=None, privacy_status="private", progress_callback=None, publish_at=None):
    """
    מעלה סרטון ל-YouTube ומחזיר את ה-video_id.
    progress_callback(percent:int) נקרא תוך כדי ההעלאה, אם סופק.
    זורק חריגה אם ההעלאה נכשלת - הקריאה האחראית צריכה לתפוס אותה.
    """
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = _get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
        },
        "status": {
            "privacyStatus": privacy_status,
        },
    }
    if publish_at:
        # פרסום מתוזמן: YouTube מפרסם בעצמו בזמן הזה (privacyStatus חייב להיות private עד אז)
        body["status"]["publishAt"] = publish_at
        body["status"]["privacyStatus"] = "private"

    media = MediaFileUpload(file_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    def _log_retry(attempt, delay, exc):
        print(f"[youtube_uploader] שגיאה זמנית בהעלאה ({exc}) - ניסיון חוזר {attempt + 2} בעוד {delay:.0f} שניות...")

    response = None
    while response is None:
        status, response = call_with_retry(
            request.next_chunk, max_attempts=5, is_retryable=_is_retryable_upload_error, base_delay=2.0, on_retry=_log_retry
        )
        if status and progress_callback:
            progress_callback(int(status.progress() * 100))

    return response.get("id")


def set_thumbnail(video_id, image_path):
    """גל 55: התמונה הממוזערת שנבחרה לסרטון שכבר הועלה (מסך הנתונים מעלה אותה יחד עם הסרטון). אותה קריאה כמו
    ב-A/B של התמונות (utils/youtube_analytics.set_video_thumbnail); זורקת על כל כשל - הקריאה האחראית רושמת."""
    from utils.bot.youtube_analytics import set_video_thumbnail
    set_video_thumbnail(video_id, image_path)
