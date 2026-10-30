# entrypoints/web/bot_process.py
#
# 24.10.2026 (פיצול web_app.py, קבוצה 2): תהליך הבוט (Discord) - הלולאה שמריצה את main.py ומפעילה אותו מחדש אחרי קריסה,
# הכתיבה ללוג של הבוט וההתראה כשהוא מפסיק לעלות. עבר מ-web_app.py בלי שינוי התנהגות. web_app מייבא את השמות האלה בחזרה
# (web_app.<שם> נשאר), וה-routes ממשיכים לקרוא W.<שם>. המצב (_bot_state, _bot_state_lock, תור הלוג וקבועי BOT_*) נשאר
# מוגדר ב-web_app ונקרא ונכתב דרך W. - טסטים מחליפים את web_app.<שם> (_bot_write_to_log, MAIN_PY_PATH...), והקוד כאן צריך
# לראות את ההחלפה (tests/web/test_web_app_split.py בודק את זה).
import subprocess
import time

from entrypoints import web_app as W


def _bot_write_to_log(line):
    W._bot_log_buffer.append(line)
    W._bot_log_queue.put(line)


def _notify_bot(title, body):
    """מרכז ההתראות: הבוט הפסיק לעלות (שגיאת הגדרה או קריסות חוזרות) - רואים את זה גם בלי להיכנס למסך הבוט."""
    try:
        W.notification_log.add("bot", title, body=body, level="bad", target="bot")
    except Exception:
        pass   # הלוג של הבוט כבר מספר את זה


def _run_bot_process_loop():
    """זהה בעיקרון ל-ui/bot_tab.py's run_bot_process - לולאה (לא ריצה חד-
    פעמית): אם main.py יוצא בלי שהמשתמש ביקש (קריסה), מפעילים אותו מחדש
    אוטומטית עד BOT_MAX_AUTO_RESTARTS קריסות בתוך BOT_AUTO_RESTART_WINDOW_SECONDS."""
    while W._bot_state["is_running"]:
        returncode = None
        try:
            # errors="replace": פלט שאינו UTF-8 (main.py כתב פעם cp1255) הפיל את הקורא בזמן שהבוט עוד רץ
            proc = subprocess.Popen(
                [W.get_python_executable(), W.MAIN_PY_PATH], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1, creationflags=W.NO_WINDOW_FLAGS,
            )
        except Exception as e:
            W._bot_write_to_log(f"\n[שגיאה בהרצה]: {e}\n")
        else:
            with W._bot_state_lock:
                W._bot_state["process"] = proc
            try:
                for line in iter(proc.stdout.readline, ""):
                    W._bot_write_to_log(line)
            except Exception as e:
                # הקורא נפל אבל הבוט אולי עוד רץ: לא מפעילים עותק נוסף (שני בוטים על אותו טוקן) - מרוקנים את
                # הפלט בלי לפרסר (שהבוט לא ייתקע על צינור מלא) ומחכים שהתהליך הזה באמת ייצא
                W._bot_write_to_log(f"\n[שגיאה בקריאת הלוג של הבוט]: {e}\n")
                try:
                    while proc.stdout.buffer.read(65536):
                        pass
                except Exception:
                    pass
            returncode = proc.wait()
        with W._bot_state_lock:
            W._bot_state["process"] = None

        if not W._bot_state["is_running"]:
            return  # כיבוי יזום - לא קריסה

        if W.BOT_CONFIG_ERROR_EXIT_CODE is not None and returncode == W.BOT_CONFIG_ERROR_EXIT_CODE:
            # שגיאת הגדרה (טוקן חסר/נדחה, Intent חסר - ההודעה של main.py כבר בלוג): הפעלה מחדש לא תעזור
            with W._bot_state_lock:
                W._bot_state["is_running"] = False
                W._bot_state["config_error"] = True
            W._bot_write_to_log("\n[שגיאת הגדרה] הבוט לא הופעל מחדש - בדוק את הטוקן וההגדרה שמופיעה למעלה, ואז הפעל שוב.\n")
            W._notify_bot("🤖 הבוט לא עלה: שגיאת הגדרה", "בדוק את הטוקן וההגדרה בלוג של הבוט, ואז הפעל אותו שוב.")
            return

        with W._bot_state_lock:
            W._bot_state["crash_timestamps"], give_up = W.record_crash_and_check_giveup(
                W._bot_state["crash_timestamps"], time.time(), W.BOT_AUTO_RESTART_WINDOW_SECONDS, W.BOT_MAX_AUTO_RESTARTS
            )
        if give_up:
            with W._bot_state_lock:
                W._bot_state["is_running"] = False
                W._bot_state["gave_up"] = True
            W._bot_write_to_log(
                f"\n[קריסה חוזרת] הבוט קרס {len(W._bot_state['crash_timestamps'])} פעמים ב-5 הדקות האחרונות - "
                "עצירת ניסיונות הפעלה מחדש אוטומטיים. תקן את הבעיה ולחץ שוב על 'הפעל בוט' ידנית.\n"
            )
            W._notify_bot("🤖 הבוט נעצר אחרי קריסות חוזרות", "הפעלה מחדש אוטומטית הופסקה. הפרטים בלוג של הבוט.")
            return

        W._bot_write_to_log(
            f"\n[קריסה] הבוט נסגר בלי שביקשת - מפעיל מחדש אוטומטית "
            f"({len(W._bot_state['crash_timestamps'])}/{W.BOT_MAX_AUTO_RESTARTS})...\n"
        )
        time.sleep(3)
