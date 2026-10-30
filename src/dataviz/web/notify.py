# dataviz/web/notify.py
#
# 20.10.2026: התראה כשרינדור של עורך הגרפים מסתיים או נכשל - ל-Discord webhook אופציונלי שהמשתמש מכניס (נשמר כמו שאר
# הסודות: Windows Credential Manager דרך utils.shared.secrets_vault, ולא נשלח חזרה לדפדפן), בנוסף להתראות שבאפליקציה.
# dataviz_maker.py שולח בסוף הריצה הודעה עם הפרקים, המצב, מה נוצר ומה נכשל. מתוך pytest לא נשלח כלום לכתובת אמיתית
# (PYTEST_CURRENT_TEST) - בטסטים רק מקבל מזויף שמועבר ב-post=.
import os
import re
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

SECRET_KEY = "DATAVIZ_DISCORD_WEBHOOK"
URL_RE = re.compile(r"^https://(?:(?:canary|ptb)\.)?discord(?:app)?\.com/api/webhooks/\d{5,30}/[\w\-]{20,120}$")
MAX_TEXT = 1800   # Discord: עד 2000 תווים להודעה


def valid_url(url: Any) -> bool:
    return bool(URL_RE.match(str(url or "").strip()))


def get_url() -> str:
    from utils.shared.secrets_vault import get_secret
    url = str(get_secret(SECRET_KEY) or "").strip()
    return url if valid_url(url) else ""


def set_url(url: Any) -> Dict[str, Any]:
    """שומר (או מוחק כשריק) את הכתובת. כתובת שאינה webhook של Discord נדחית."""
    from dataviz.web.episodes import EpisodeError
    from utils.shared.secrets_vault import delete_secret, set_secret
    url = str(url or "").strip()
    if not url:
        delete_secret(SECRET_KEY)
        return status()
    if not valid_url(url):
        raise EpisodeError("זו לא כתובת webhook של Discord (https://discord.com/api/webhooks/...).")
    try:
        set_secret(SECRET_KEY, url)
    except RuntimeError as e:
        raise EpisodeError(str(e), status=500) from e
    return status()


def status() -> Dict[str, Any]:
    """אם מוגדר, ורק סוף הכתובת - הכתובת עצמה לא חוזרת לדפדפן."""
    url = get_url()
    return {"configured": bool(url), "hint": ("…" + url[-6:]) if url else ""}


def message(results: Mapping[str, Any], names: Sequence[str], mode: str, seconds: float, variant: str = "") -> str:
    ok = not results.get("errors")
    icon = "✅" if ok else "❌"
    what = ", ".join(names[:8]) + (f" ועוד {len(names) - 8}" if len(names) > 8 else "")
    duration = f"{seconds:.0f} שניות" if seconds < 60 else f"{seconds / 60:.1f} דקות"
    lines = [f"{icon} **עורך הגרפים**: {what}" + (f" · {variant}" if variant else "") + f" ({mode}) {'הסתיים' if ok else 'נכשל'} - {duration}",
             f"קבצים: {results.get('files_created', 0)} · שגיאות: {results.get('errors', 0)}"
             + (f" · דולגו: {results['skipped']}" if results.get("skipped") else "")]
    return "\n".join(lines)[:MAX_TEXT]


def send(url: str, text: str, post: Optional[Callable[..., Any]] = None) -> bool:
    """שולח מיד (בסוף ריצה, לא ב-thread שהתהליך עלול לסגור). post = מקבל מזויף בטסטים. כשל רשת לא מפיל כלום."""
    if not valid_url(url):
        return False
    if post is None:
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return False   # אף פעם לא Discord אמיתי מטסט
        import requests
        post = requests.post
    try:
        response = post(url, json={"content": text[:MAX_TEXT]}, timeout=10)
        return 200 <= int(getattr(response, "status_code", 0)) < 300
    except Exception:
        return False
