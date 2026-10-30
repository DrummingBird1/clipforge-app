# utils/shared/gui_thread.py
#
# self.after(0, func) שנקרא מ-thread שאינו הראשי אינו בטוח: הוא צריך לרשום
# פקודת Tcl חדשה (self.tk.createcommand), פעולה שדורשת גישה למתורגם ה-Tcl
# שבבעלות ה-thread הראשי. אומת בפועל בטסטים אוטומטיים של הפרויקט (utils/shared/worker.py)
# שזה יכול להיכשל עם RuntimeError("main thread is not in main loop") - וגם אם
# בדרך כלל "עובד", זה תלוי-תזמון ולא מובטח. הדפוס הבטוח: thread הרקע רק
# "מפקיד" callback בתור רגיל (thread-safe מטבעו, בלי Tcl בכלל), ולולאת after
# קיימת שכבר רצה על ה-thread הראשי שואבת ומריצה אותו.
import queue


class MainThreadDispatcher:
    def __init__(self):
        self._queue = queue.Queue()

    def call_soon(self, func, *args, **kwargs):
        """קריאה מכל thread - מתזמן func(*args, **kwargs) להרצה על ה-thread הראשי
        בפעם הבאה ש-drain() נקרא."""
        self._queue.put((func, args, kwargs))

    def drain(self):
        """קריאה רק מה-thread הראשי (מתוך לולאת after קיימת) - מריץ כל מה שממתין בתור."""
        try:
            while True:
                func, args, kwargs = self._queue.get_nowait()
                try:
                    func(*args, **kwargs)
                except Exception as e:
                    # תפוס בכוונה (לא לתת ל-callback אחד שנכשל לעצור/לקרוס את
                    # לולאת ה-after כולה - עדכוני UI אחרים בתור עדיין צריכים
                    # לרוץ) - אבל מודפס, לא נבלע בשקט מוחלט (item: בדיקת באגים
                    # מקיפה - נמצא שזה היה בלתי-ניתן-לאבחון מדיווחי משתמשים).
                    print(f"[gui_thread] callback נכשל: {e}")
        except queue.Empty:
            pass
