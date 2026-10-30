# utils/shared/notifications.py
import threading

try:
    import requests
except ImportError:
    requests = None

try:
    from winotify import Notification
except ImportError:
    Notification = None


def send_webhook_notification(webhook_url, message):
    """שולח הודעת טקסט ל-Discord Webhook ברקע, כדי לא לתקוע את ה-UI על קריאת רשת."""
    if not webhook_url or not requests:
        return

    def _send():
        try:
            requests.post(webhook_url, json={"content": message}, timeout=10)
        except Exception as e:
            print(f"[notifications] שגיאה בשליחת Webhook: {e}")

    threading.Thread(target=_send, daemon=True).start()


def send_toast_notification(title, message):
    """התראת Windows מקורית - שימושי כשה-GUI ממוזער/במגש המערכת ולא רואים את הלוג."""
    if not Notification:
        return
    try:
        toast = Notification(app_id="ClipForge", title=title, msg=message)
        toast.show()
    except Exception as e:
        print(f"[notifications] שגיאה בשליחת התראת Windows: {e}")
