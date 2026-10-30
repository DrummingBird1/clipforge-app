# utils/bot/weekly_digest.py
#
# תקציר שבועי ל-Discord Webhook (אם מוגדר) - נבדק פעם ביום מאותה לולאה
# שבודקת משימות מתוזמנות (gui_manager.pyw), לא רץ עצמאית. שולח את הראשון
# מיד אם 7+ ימים עברו מאז last_digest_sent_at (כולל אם הוא ריק - התקנה
# ראשונה) - זו הרחבה טבעית של job_history/result_json שכבר קיימים, לא
# מנגנון תזמון נפרד.
import datetime

from utils.shared import job_history
from utils.shared.notifications import send_webhook_notification
from utils.shared.state import state


def _parse_iso(value):
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value)
    except ValueError:
        return None


def build_digest_message(now=None):
    now = now or datetime.datetime.now()
    since = (now - datetime.timedelta(days=7)).isoformat(timespec="seconds")
    jobs = job_history.get_jobs_since(since)

    if not jobs:
        return "📊 תקציר שבועי: לא בוצעו ריצות בשבוע האחרון."

    success_count = sum(1 for j in jobs if j[1] == "success")
    failed_count = len(jobs) - success_count
    lines = [f"📊 **תקציר שבועי** - {len(jobs)} ריצות ({success_count} הצליחו, {failed_count} נכשלו):"]
    for script_name, status, _started_at, _duration, result_json in jobs:
        icon = "✅" if status == "success" else "❌"
        summary = job_history.format_result_summary(result_json)
        line = f"{icon} {script_name}"
        if summary:
            line += f" - {summary}"
        lines.append(line)

    return "\n".join(lines)


def maybe_send_weekly_digest(now=None):
    """שולח תקציר שבועי אם יש webhook מוגדר ועברו 7+ ימים מהתקציר הקודם
    (או שאף פעם לא נשלח תקציר). מחזיר True אם נשלח."""
    now = now or datetime.datetime.now()
    if not state.discord_webhook_url:
        return False

    last_sent = _parse_iso(state.last_digest_sent_at)
    if last_sent and (now - last_sent) < datetime.timedelta(days=7):
        return False

    send_webhook_notification(state.discord_webhook_url, build_digest_message(now))
    state.last_digest_sent_at = now.isoformat(timespec="seconds")
    state.save_config()
    return True
