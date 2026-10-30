# utils/media/compilation.py
#
# לוגיקה טהורה וניתנת-לבדיקה עבור my_scripts/video/weekly_compilation.py (item:
# ריקאפ תקופתי + פרקים אוטומטיים) - הקוד שבאמת מריץ ffmpeg/ffprobe נשאר
# בסקריפט עצמו, בדיוק כמו utils/media/timelapse.py ל-timelapse_maker.py.

PERIOD_TO_DAYS = {"week": 7, "month": 30, "year": 365}
PERIOD_LABELS = {"week": "Weekly", "month": "Monthly", "year": "Yearly"}


def resolve_period_days(period, explicit_days=None):
    """days מפורש (--days) תמיד גובר על period - נשאר לשליטה עדינה בהתנהגות
    הישנה; period הוא נוחות בלבד (week/month/year -> ברירת מחדל סבירה).
    period לא-מוכר (או None) נופל ל"week" (7, זהה להתנהגות המקורית)."""
    if explicit_days is not None:
        return explicit_days
    return PERIOD_TO_DAYS.get(period, PERIOD_TO_DAYS["week"])


def recap_label_for_period(period):
    """שם קובץ הפלט (Weekly_Recap_.../Monthly_Recap_.../Yearly_Recap_...) -
    period לא-מוכר נופל ל"Weekly", זהה ל-resolve_period_days."""
    return PERIOD_LABELS.get(period, PERIOD_LABELS["week"])


def format_chapter_timestamp(seconds):
    """MM:SS אם פחות משעה, אחרת H:MM:SS - הפורמט שיוטיוב מזהה כפרקים (chapters)
    כשהם מופיעים בתיאור הסרטון בשורות נפרדות, כל עוד הראשון מתחיל מ-00:00."""
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def build_chapters_text(clip_entries):
    """clip_entries: [(display_name, duration_seconds), ...] בסדר שהם מוצבים
    בקובץ המאוחד. מחזיר טקסט מוכן-להדבקה בתיאור יוטיוב - שורה אחת לכל קטע,
    "<timestamp> <שם>", מתחיל מ-00:00. יוטיוב דורש לפחות 3 פרקים ושכל פרק
    יהיה לפחות 10 שניות כדי להפעיל בפועל את תצוגת הפרקים - לא נאכף כאן
    (פחות מזה פשוט לא יופעל כפרקים אצל יוטיוב, לא שגיאה מבחינתנו - הטקסט
    עדיין מיוצר ותקין להדבקה ידנית).
    clip_entries ריק מחזיר מחרוזת ריקה."""
    lines = []
    cumulative = 0.0
    for name, duration in clip_entries:
        lines.append(f"{format_chapter_timestamp(cumulative)} {name}")
        cumulative += duration
    return "\n".join(lines)


def should_run_recap_today(period, recap_weekday, today):
    """קובע אם *היום הזה* (today: datetime.date) הוא היום הנכון להריץ ריקאפ
    אוטומטי, לפי period. month/year רצים בתאריך קבוע (1 לחודש / 1 בינואר) -
    לא נעזרים ב-recap_weekday (שרלוונטי רק ל-period="week", יום-בשבוע נבחר,
    0=שני..6=ראשון, זהה ל-date.weekday()). period לא-מוכר נופל ל"week"."""
    if period == "month":
        return today.day == 1
    if period == "year":
        return today.month == 1 and today.day == 1
    return today.weekday() == recap_weekday
