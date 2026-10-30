# utils/shared/health_status.py
#
# לוגיקה טהורה וניתנת-לבדיקה לתצוגת "בריאות מערכת" - משמשת גם את פקודת
# /status בדיסקורד (cogs/status_cog.py) וגם את web_dashboard.py, כדי ששתי
# התצוגות יציגו את אותה עיצוב זמן בדיוק.


def format_duration(total_seconds):
    """ממיר משך זמן בשניות למחרוזת קריאה בעברית (ימים/שעות/דקות) - למשל
    "2י 3ש 14ד". פחות מדקה מוצג בשניות ("45שנ׳") - "0ד" נראה כמו "נגמר" (סבב ייצוב: "נותרו כ-0ד" בדקה האחרונה)."""
    total_seconds = max(0, int(total_seconds))
    if total_seconds < 60:
        return f"{total_seconds}שנ׳"
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)

    parts = []
    if days:
        parts.append(f"{days}י")
    if hours:
        parts.append(f"{hours}ש")
    if minutes:
        parts.append(f"{minutes}ד")
    return " ".join(parts)
