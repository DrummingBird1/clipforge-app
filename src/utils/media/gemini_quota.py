# utils/media/gemini_quota.py
#
# מעקב אחרי מכסת Gemini בריצה אחת של story_cutter.py: עד עכשיו כשהמכסה היומית נגמרה והקליפים
# אושרו אוטומטית בלי שיפוט (אין Ollama, או שהוא נכשל) - זה קרה בשקט, ושורת ההפעלה היחידה
# ("[WARNING] Ollama לא נמצא") נבלעה בהתחלה של ריצה של שעות. כאן: זיהוי שגיאת מכסה, אזהרה
# ברורה אחת כשזה קורה (ואזהרה מוקדמת כשמתקרבים לתקרה שהמשתמש הגדיר), וסיכום בסוף - כמה קליפים
# אושרו בלי שיפוט אמיתי. לוגיקה טהורה (מחזירה הודעות), ההדפסה אצל הקורא.

import time
from typing import Callable, List, Optional

QUOTA_MARKERS = ("429", "resource_exhausted", "quota", "rate limit", "rate_limit")
UNJUDGED_MARKER = "מאשר כברירת מחדל"      # הנוסח ש-local_vision_judge מחזיר כשאין שיפוט אמיתי
WARN_FRACTION = 0.8
# מפסק: אחרי כך וכך כשלי מכסה רצופים מפסיקים לדפוק ב-API (וגם לא מבזבזים 6 שניות backoff על כל קליפ) ועוברים ישר
# לשיפוט המקומי; אחרי תקופת צינון מנסים שוב פעם אחת (כי 429 של "בקשות לדקה" חולף, בניגוד למכסה יומית)
MAX_CONSECUTIVE_QUOTA_FAILURES = 3
COOLDOWN_SECONDS = 300


def is_quota_error(error: object) -> bool:
    text = str(error).lower()
    return any(marker in text for marker in QUOTA_MARKERS)


def is_unjudged_reason(reason: object) -> bool:
    return UNJUDGED_MARKER in str(reason)


class QuotaWatch:
    """daily_limit = תקרת קריאות Gemini ליום שהמשתמש מכיר (0 = לא ידוע, בלי אזהרה מוקדמת)."""

    def __init__(self, daily_limit: int = 0, local_judge_available: bool = False,
                 max_consecutive: int = MAX_CONSECUTIVE_QUOTA_FAILURES, cooldown: float = COOLDOWN_SECONDS,
                 clock: Callable[[], float] = time.monotonic):
        self.daily_limit = max(int(daily_limit or 0), 0)
        self.max_consecutive = max_consecutive
        self.cooldown = cooldown
        self._clock = clock
        self.consecutive_quota_failures = 0
        self._tripped_at: Optional[float] = None
        self.skipped_calls = 0
        self.local_judge_available = local_judge_available
        self.calls = 0
        self.quota_errors = 0
        self.unjudged_approved = 0
        self._warned_near = False
        self._warned_exhausted = False

    def gemini_called(self) -> Optional[str]:
        """לפני כל קריאה אמיתית. מחזיר אזהרה מוקדמת (פעם אחת) כשמגיעים ל-80% מהתקרה."""
        self.calls += 1
        if self.daily_limit and not self._warned_near and self.calls >= self.daily_limit * WARN_FRACTION:
            self._warned_near = True
            return (f"[WARNING] נשלחו {self.calls} בקשות ל-Gemini בריצה הזו - {int(WARN_FRACTION * 100)}% מהתקרה היומית "
                    f"שהגדרת ({self.daily_limit}). {self._what_happens_next()}")
        return None

    def gemini_failed(self, error: object) -> Optional[str]:
        """אחרי כשל של קריאה. מחזיר אזהרת 'המכסה נגמרה' (פעם אחת) אם זו שגיאת מכסה."""
        if not is_quota_error(error):
            return None
        self.quota_errors += 1
        self.consecutive_quota_failures += 1
        if self.consecutive_quota_failures >= self.max_consecutive and self._tripped_at is None:
            self._tripped_at = self._clock()
        if self._warned_exhausted:
            return None
        self._warned_exhausted = True
        return (f"[WARNING] מכסת Gemini כנראה נגמרה (אחרי {self.calls} בקשות, שגיאה: {str(error)[:120]}). "
                f"{self._what_happens_next()}")

    def gemini_succeeded(self) -> None:
        """תשובה תקינה: מאפסים את מונה הכשלים הרצופים ומסגרים את המפסק."""
        self.consecutive_quota_failures = 0
        self._tripped_at = None

    def should_skip_gemini(self) -> bool:
        """True כשהמפסק פתוח (כשלי מכסה רצופים) ועוד לא עברה תקופת הצינון - לא קוראים ל-Gemini בכלל.
        אחרי הצינון מחזירים False פעם אחת (קריאת ניסיון); כשל נוסף פותח את המפסק מחדש."""
        if self._tripped_at is None:
            return False
        if self._clock() - self._tripped_at >= self.cooldown:
            self._tripped_at = None
            self.consecutive_quota_failures = self.max_consecutive - 1    # כשל אחד נוסף וסוגרים שוב
            return False
        self.skipped_calls += 1
        return True

    @property
    def tripped(self) -> bool:
        return self._tripped_at is not None

    def verdict(self, reason: object) -> Optional[str]:
        """אחרי כל החלטה על קליפ. סופר קליפים שאושרו בלי שיפוט אמיתי ומתריע עליהם בקול."""
        if not is_unjudged_reason(reason):
            return None
        self.unjudged_approved += 1
        return f"[WARNING] קליפ אושר בלי שיפוט AI אמיתי (סה\"כ {self.unjudged_approved}) - כדאי לעבור עליו ידנית."

    def summary(self) -> Optional[str]:
        if not (self.unjudged_approved or self.quota_errors):
            return None
        return (f"[WARNING] סיכום מכסה: {self.calls} בקשות Gemini, {self.quota_errors} שגיאות מכסה, "
                f"{self.unjudged_approved} קליפים אושרו בלי שיפוט AI אמיתי - בדוק אותם לפני פרסום.")

    def _what_happens_next(self) -> str:
        if self.local_judge_available:
            return "קליפים יישפטו מכאן דרך Ollama המקומי."
        return ("Ollama לא זמין, ולכן מכאן קליפים יאושרו אוטומטית בלי שיפוט! עצור והמשך מחר, "
                "הפעל Ollama, או שדרג את מכסת Gemini.")


def messages(*items: Optional[str]) -> List[str]:
    return [m for m in items if m]