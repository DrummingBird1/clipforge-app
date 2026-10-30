# utils/shared/retry.py
#
# לוגיקה טהורה וניתנת-לבדיקה ל-retry עם exponential backoff, לשימוש בכל קריאת
# רשת חיצונית שעלולה להיכשל זמנית (YouTube upload, Gemini API, TikTok
# uploader) - עד כה כשל רשת חד-פעמי היה כשל מוחלט של כל הריצה, בלי שום ניסיון
# חוזר (מלבד story_cutter.py, שכבר היה לו retry מצומצם משלו ל-Gemini בלבד).
#
# call_with_retry_async (item: אימוץ retry/backoff גם ב-Steam/RSS) - אותה
# לוגיקת backoff בדיוק (compute_backoff_delay משותף), אבל cogs/steam_monitor.py
# ו-cogs/rss_monitor.py הם קוד אסינכרוני (discord.py/aiohttp) - time.sleep
# החוסם של call_with_retry הרגיל היה קופא את כל ה-event loop של הבוט (כל
# הפקודות האחרות) במקום רק את המשימה הזו, אז צריך תאום asyncio.sleep+await
# נפרד, לא רק לעטוף את הגרסה הסינכרונית.

import asyncio
import time
from typing import Any, Awaitable, Callable, Optional, TypeVar

T = TypeVar("T")


def compute_backoff_delay(attempt: int, base_delay: float = 1.0, factor: float = 2.0, max_delay: float = 30.0) -> float:
    """זמן ההמתנה (בשניות) לפני ניסיון מספר attempt+1 (attempt מתחיל מ-0) -
    גדל מעריכית (base_delay * factor**attempt), מוגבל ל-max_delay כדי שכשל
    ממושך לא יגרום להמתנה של דקות ארוכות בין ניסיון לניסיון."""
    return min(base_delay * (factor ** attempt), max_delay)


def call_with_retry(
    func: Callable[[], T],
    max_attempts: int = 4,
    is_retryable: Callable[[Exception], bool] = lambda e: True,
    base_delay: float = 1.0,
    factor: float = 2.0,
    max_delay: float = 30.0,
    sleep_func: Optional[Callable[[float], Any]] = None,
    on_retry: Optional[Callable[[int, float, Exception], Any]] = None,
) -> T:
    """קורא ל-func() (בלי ארגומנטים - הקורא סוגר עליהם מראש עם lambda/functools.partial
    אם צריך). על חריגה: אם is_retryable(e) מחזיר False, או שזה הניסיון האחרון,
    זורקים מיד; אחרת ממתינים לפי compute_backoff_delay וקוראים שוב.
    on_retry(attempt, delay, exc), אם סופק, נקרא לפני כל המתנה - לשימוש בלוג."""
    sleep_func = sleep_func or time.sleep
    for attempt in range(max_attempts):
        try:
            return func()
        except Exception as e:
            if attempt == max_attempts - 1 or not is_retryable(e):
                raise
            delay = compute_backoff_delay(attempt, base_delay, factor, max_delay)
            if on_retry:
                on_retry(attempt, delay, e)
            sleep_func(delay)
    raise RuntimeError("call_with_retry: max_attempts must be at least 1")


async def call_with_retry_async(
    func: Callable[[], Awaitable[T]],
    max_attempts: int = 4,
    is_retryable: Callable[[Exception], bool] = lambda e: True,
    base_delay: float = 1.0,
    factor: float = 2.0,
    max_delay: float = 30.0,
    sleep_func: Optional[Callable[[float], Awaitable[Any]]] = None,
    on_retry: Optional[Callable[[int, float, Exception], Any]] = None,
) -> T:
    """זהה ל-call_with_retry (אותו compute_backoff_delay), לקוד אסינכרוני -
    func() מחזירה awaitable (לדוגמה: lambda: session.get(url)), וההמתנה בין
    ניסיונות היא asyncio.sleep (לא חוסמת את ה-event loop, בניגוד ל-time.sleep
    שהגרסה הסינכרונית משתמשת בה)."""
    sleep_func = sleep_func or asyncio.sleep
    for attempt in range(max_attempts):
        try:
            return await func()
        except Exception as e:
            if attempt == max_attempts - 1 or not is_retryable(e):
                raise
            delay = compute_backoff_delay(attempt, base_delay, factor, max_delay)
            if on_retry:
                on_retry(attempt, delay, e)
            await sleep_func(delay)
    raise RuntimeError("call_with_retry_async: max_attempts must be at least 1")
