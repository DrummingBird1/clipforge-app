# utils/shared/crash_supervisor.py
#
# לוגיקה טהורה לזיהוי "לולאת קריסה" - כמה קריסות בלתי-צפויות בחלון זמן נתון
# נחשבות יותר מדי כדי להמשיך לנסות להפעיל מחדש אוטומטית. מופרד מ-ui/bot_tab.py
# (שם נעשה שימוש בפועל, ליד הפעלת/הפסקת תהליך הבוט) כדי שאפשר לבדוק את חוקי
# הספירה/החלון בלי תלות ב-subprocess/Tkinter אמיתיים.


def record_crash_and_check_giveup(crash_timestamps, now, window_seconds, max_restarts):
    """מוסיף קריסה חדשה בזמן `now` לרשימה (אחרי סינון קריסות ישנות מחוץ לחלון),
    ומחזיר (updated_timestamps, should_give_up). should_give_up=True כשמספר
    הקריסות שנותרו בתוך החלון חורג מ-max_restarts - כלומר יותר מדי קריסות
    תכופות מדי, כנראה תקלה קבועה שהפעלה חוזרת לא תפתור."""
    updated = [ts for ts in crash_timestamps if now - ts < window_seconds]
    updated.append(now)
    return updated, len(updated) > max_restarts
