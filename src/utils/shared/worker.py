# utils/shared/worker.py
import collections
import contextlib
import json
import os
import queue
import re
import threading
import subprocess
import time

from utils.shared.logging_setup import setup_persistent_logging
from utils.shared.python_locator import get_python_executable
from utils.shared.render_lock import CALLER_HOLDS_LOCK_ENV_VAR, render_lock
from utils.shared.render_lock import touch as _touch_render_lock
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

try:
    import psutil
except ImportError:
    psutil = None

# בין רענוני המנעול (touch()) בזמן השהיה ממושכת - הרבה יותר קצר מ-
# MAX_LOCK_AGE_SECONDS (4 שעות, render_lock.py) כדי שאפילו אם רענון בודד
# נופל (למשל תקלה זמנית בכתיבה לדיסק), הרענון הבא עדיין יגיע בזמן.
_PAUSE_KEEPALIVE_INTERVAL_SECONDS = 60

# תואם לפורמט הפס של tqdm, למשל "...: 45%|####      | 810/1800 [...]"
PROGRESS_PATTERN = re.compile(r"(\d{1,3})%\|")

# tqdm כבר מחשב ומדפיס הערכת-זמן-שנותר בעצמו בתוך אותה שורת פס ("...
# [02:30<03:05, 5.4it/s]" - הקטע שאחרי ה-"<" הוא ה-ETA) - לא מחשבים כאן שום
# דבר, רק שולפים החוצה מספר שכבר קיים בטקסט. תואם גם "M:SS" (פחות משעה) וגם
# "H:MM:SS" (שעה ומעלה), כמו שtqdm מפרמט את שניהם.
ETA_PATTERN = re.compile(r"<(\d+):(\d{2})(?::(\d{2}))?,")


def _parse_tqdm_eta_seconds(line):
    match = ETA_PATTERN.search(line)
    if not match:
        return None
    seconds = 0
    for part in match.groups():
        if part is not None:
            seconds = seconds * 60 + int(part)
    return seconds

# פרוטוקול מפורש חלופי: סקריפט שלא משתמש ב-tqdm (או שרוצה התקדמות פר-שלב ולא
# פר-קובץ) יכול פשוט להדפיס שורה כזו בפני עצמה - עמיד יותר מ-regex שמצפה
# לפורמט הפס המדויק של tqdm, ששביר לכל שינוי בספריית/גרסת ההתקדמות.
EXPLICIT_PROGRESS_PATTERN = re.compile(r"^PROGRESS:\s*(\d{1,3})\s*$")
# וגם "PROGRESS: k/N" - k משימות מתוך N הסתיימו (סבב ייצוב; עורך-העל מדפיס 0/N בהתחלה)
EXPLICIT_COUNT_PATTERN = re.compile(r"^PROGRESS:\s*(\d+)\s*/\s*(\d+)\s*$")

# שורת תוצאה מובנית אופציונלית בסוף הריצה - סקריפט יכול לסיים עם
# "RESULT: {...}" (JSON חד-שורתי) כדי לתת ל-GUI תוצאה מפורשת (למשל מספר
# קבצים/כפילויות/שגיאות) במקום להסתפק בהצלחה/כישלון גולמיים לפי קוד היציאה.
# לא נדרש - סקריפט שלא מדפיס RESULT פשוט ימשיך לעבוד בדיוק כמו קודם.
RESULT_LINE_PREFIX = "RESULT:"
# עורך-העל מדפיס "RUN_MANIFEST: <נתיב>" אחרי ריצה. הממשק מקבל את הנתיב ב-RESULT (manifest_path), אז השורה הטכנית
# נשארת רק בקובץ הלוג ולא בלוג שבמסך (סיור הסטודיו 23.10.2026, ממצא 8)
MANIFEST_LINE_PREFIX = "RUN_MANIFEST:"

# גל 32: שורת אירוע באמצע ריצה - "EVENT: {"type": ...}" (JSON חד-שורתי). מאזין ארוך-טווח
# (OBS/תיקיית לכידה) מודיע כך שקליפ חדש נכנס, ומי שרשם handler לסוג (on_event) מחליט מה
# להריץ אחריו - מיד, לא בסוף הריצה (שלמאזין אין). לא מוצגת בקונסולה; אירוע בלי handler נבלע.
EVENT_LINE_PREFIX = "EVENT:"

# item: log spam - כל שורת פלט מכל תת-תהליך (כולל כל עדכון tqdm שלא מוצג
# בקונסולה החיה, ראו _handle_output_line) נכתבת במלואה לכאן - data/logs/
# script_runs.log(+.jsonl), מתגלגל בדיוק כמו שאר הלוגים בפרויקט (setup_persistent_logging)
# - כדי שההיסטוריה המלאה תישאר זמינה לתיעוד/דיבוג גם אחרי שהיא כבר לא
# מוצגת/רלוונטית שם.
_SCRIPT_RUN_LOGGER = setup_persistent_logging("script_runs", tee_stdio=False)

# סקריפטים "קלים" (# Concurrency: light בכותרת - ראו utils/shared/script_metadata.py)
# רצים במאגר תהליכונים משלהם, נפרד מהתור הכבד/סדרתי - כך שסריקת דיסק או שינוי
# שם קבצים לא צריכים לחכות מאחורי רינדור ffmpeg שלוקח שעה. ברירת המחדל (סקריפט
# בלי התגית) נשארת "heavy"/סדרתי לגמרי כמו קודם - זה שינוי הרשאה (opt-in),
# לא שינוי התנהגות לסקריפטים קיימים.
LIGHT_POOL_SIZE = 2


class RenderQueue:
    """גל 14 - תור הרינדור (מסלול heavy): FIFO עם קדימות ("לראש התור"), שינוי סדר,
    הוצאה והשהיה של התור כולו - בלי לגעת במשימה שכבר רצה. אותו ממשק כמו
    queue.Queue (put/get/task_done/qsize), כך ש-_worker_loop לא משתנה מבחינתו."""

    def __init__(self):
        self._items = collections.deque()
        self._cond = threading.Condition()
        self._paused = False
        self._next_id = 1

    def put(self, item, front=False, meta=None):
        with self._cond:
            entry = {"id": self._next_id, "item": item, **(meta or {})}
            self._next_id += 1
            if front:
                self._items.appendleft(entry)
            else:
                self._items.append(entry)
            self._cond.notify_all()
            return entry["id"]

    def get(self):
        with self._cond:
            while not self._items or (self._paused and self._items[0].get("item") is not None):
                self._cond.wait()
            return self._items.popleft()["item"]

    def task_done(self):
        pass

    def qsize(self):
        with self._cond:
            return sum(1 for entry in self._items if entry.get("item") is not None)

    @property
    def paused(self):
        return self._paused

    def set_paused(self, paused):
        with self._cond:
            self._paused = bool(paused)
            self._cond.notify_all()

    def snapshot(self):
        with self._cond:
            return [{k: v for k, v in entry.items() if k != "item"} for entry in self._items if entry.get("item") is not None]

    def move(self, task_id, direction):
        """direction: up/down/top/bottom. True אם זז."""
        with self._cond:
            items = list(self._items)
            index = next((i for i, e in enumerate(items) if e["id"] == task_id), None)
            if index is None:
                return False
            entry = items.pop(index)
            target = {"up": max(0, index - 1), "down": min(len(items), index + 1), "top": 0, "bottom": len(items)}.get(direction, index)
            items.insert(target, entry)
            self._items = collections.deque(items)
            return target != index

    def remove(self, task_id):
        """מוציא משימה ממתינה מהתור; מחזיר את ה-callback שלה (כדי לסגור אותה) או None."""
        with self._cond:
            for entry in list(self._items):
                if entry["id"] == task_id:
                    self._items.remove(entry)
                    return entry["item"]
            return None


class TaskWorker:
    def __init__(self):
        self.heavy_queue = RenderQueue()
        self.light_queue = queue.Queue()
        self.log_queue = queue.Queue()
        self.progress_queue = queue.Queue()
        self.last_returncode = None
        self._lock = threading.Lock()
        self.active_processes = {}  # id(proc) -> Popen, כל התהליכים הפעילים כרגע (שני המסלולים)
        self.is_running = False
        self._paused = False
        self._pause_stop_event = threading.Event()
        self._pause_keepalive_thread = None
        self._event_handlers = {}

        threading.Thread(target=self._worker_loop, args=(self.heavy_queue,), daemon=True).start()
        for _ in range(LIGHT_POOL_SIZE):
            threading.Thread(target=self._worker_loop, args=(self.light_queue,), daemon=True).start()

    def _worker_loop(self, task_queue):
        while True:
            task = task_queue.get()
            if task is None:
                break
            func, args, callback = task
            try:
                outcome = func(*args)
            except Exception as e:
                self.log_queue.put((f"Worker Error: {e}\n", "red"))
                outcome = {"returncode": -1, "result": None}
            finally:
                with self._lock:
                    self.is_running = bool(self.active_processes)
                if callback:
                    callback(outcome)
                task_queue.task_done()

    def add_script_task(self, script_path, folder_path, on_finish, concurrency="heavy", extra_args=None, on_start=None,
                        label=None, priority="normal", busy_guard=None):
        """דוחף משימת הרצת סקריפט לתור המתאים (heavy/light לפי מטא-דאטת הסקריפט).

        היה מקבל גם encoder_args (דגלי ffmpeg כמו "-c:v hevc_nvenc -preset fast")
        ומוסיף אותם תמיד לשורת הפקודה, בלי קשר לאיזה סקריפט נבחר. שלושה מהסקריפטים
        (story_cutter.py, audio_converter.py, file_renamer.py) משתמשים ב-
        argparse.parse_args() קפדני שלא מכיר דגלים כאלה - כל הרצה שלהם דרך כפתור
        ה-Run הייתה קורסת עם שגיאת "unrecognized arguments". rocket_shorts_publisher.py
        עצמו גם מתעלם מהם בשקט (parse_known_args) ושואב את המקודד שלו מ-
        rocket_settings.json במקום זאת - כך שהדגלים האלה לא היטיבו עם אף סקריפט.

        extra_args שונה מזה: ברירת המחדל None (=[]) ולעולם לא מתווסף אוטומטית -
        הקורא (ui/dashboard.py) אחראי להעביר אותו רק כשהוא בטוח שהסקריפט הנבחר
        אכן מזהה את הדגלים האלה (למשל --ai-provider עבור story_cutter.py בלבד),
        בדיוק כדי לא לחזור על אותה תקלה."""
        python_exe = get_python_executable()
        if not python_exe:
            # קורה רק בגרסה הארוזה (exe) כשאין Python גלובלי מותקן במערכת - בעבר
            # get_python_executable() היה נופל חזרה בשקט ל-sys.executable (ה-exe
            # עצמו), מה שפתח עוד עותק מלא של ה-GUI במקום להריץ את הסקריפט, בלי
            # שום הודעת שגיאה. עדיף להיכשל כאן בבירור.
            self.log_queue.put((
                "❌ לא נמצא פרשן Python להרצת הסקריפט (רלוונטי רק לגרסה הארוזה/exe) - "
                "התקן Python והוסף אותו ל-PATH, או הרץ דרך Launcher.vbs.\n",
                "red",
            ))
            return

        cmd = [python_exe, "-u", script_path, "--input_dir", folder_path, *(extra_args or [])]
        display_name = os.path.basename(script_path)

        def run_proc():
            proc = None
            result = None
            returncode = -1
            if busy_guard and concurrency == "heavy":
                self._wait_until_not_busy(busy_guard, label or display_name)
            if on_start is not None:
                # גל 12 (ממשק הדפדפן): כמה משימות בתור בבת-אחת (יעדים) - הקורא מעדכן
                # "מה רץ עכשיו" ברגע שהמשימה באמת מתחילה, לא כשהיא נכנסה לתור.
                try:
                    on_start()
                except Exception as e:
                    self.log_queue.put((f"on_start נכשל: {e}\n", "red"))

            # מנעול חוצה-תהליכים רק למשימות "heavy" (רינדור GPU כבד) - כדי
            # שרינדור שהופעל מה-GUI לא יתנגש עם רינדור שהבוט מפעיל בו-זמנית
            # (cogs/scheduler_cog.py/remote_execution.py, תהליך נפרד לגמרי) -
            # ראו utils/shared/render_lock.py. משימות "light" לא נוגעות ב-GPU בכלל.
            def _log_waiting(_seconds_waited):
                self.log_queue.put((f"[{display_name}] ⏳ ממתין לסיום רינדור אחר שרץ כרגע (GUI או הבוט)...\n", None))

            # priority=10 - הרצה ידנית של משתמש (GUI/דפדפן) קודמת בתור למול
            # ריצה מתוזמנת ברקע (cogs/scheduler_cog.py, נשארת בברירת המחדל 0) -
            # מישהו שלוחץ "הרץ" עכשיו מחכה בפועל, בניגוד לג'וב מתוזמן.
            lock_ctx = render_lock(on_wait=_log_waiting, priority=10, label=display_name) if concurrency == "heavy" else contextlib.nullcontext()

            # אם אנחנו כבר תופסים את המנעול כאן (heavy), מודיעים לתת-התהליך
            # עם משתנה סביבה - כדי שסקריפט שגם יודע להגן על עצמו בעצמו
            # (utils.shared.render_lock.render_lock_if_needed, ראו video_editor.py)
            # לא ינסה לתפוס את אותו מנעול שוב ויינעל על עצמו.
            proc_env = {**os.environ, CALLER_HOLDS_LOCK_ENV_VAR: "1"} if concurrency == "heavy" else None

            with lock_ctx:
                try:
                    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW_FLAGS, env=proc_env)
                    with self._lock:
                        self.active_processes[id(proc)] = proc
                        self.is_running = True
                    self.progress_queue.put({"pct": 0, "eta_seconds": None})

                    # קריאה תו-אחר-תו ופיצול גם על \r - כלי כמו tqdm מעדכנים שורת התקדמות
                    # עם \r בלבד (בלי \n) עד שהפס נסגר, כך ש-readline() לא היה מחזיר כלום
                    # במשך כל ריצת ה-ffmpeg ומציג את כל ההתקדמות בבת אחת רק בסוף.
                    buffer = ""
                    while True:
                        ch = proc.stdout.read(1)
                        if ch == "":
                            break
                        if ch in ("\r", "\n"):
                            if buffer:
                                parsed_result = self._handle_output_line(buffer, display_name)
                                if parsed_result is not None:
                                    result = parsed_result
                            buffer = ""
                        else:
                            buffer += ch
                    if buffer:
                        parsed_result = self._handle_output_line(buffer, display_name)
                        if parsed_result is not None:
                            result = parsed_result

                    proc.wait()
                    returncode = proc.returncode
                    self.last_returncode = returncode
                    if returncode == 0:
                        self.progress_queue.put({"pct": 100, "eta_seconds": None})
                except Exception as e:
                    returncode = -1
                    self.last_returncode = -1
                    self.log_queue.put((f"Process Exec Error: {e}\n", "red"))
                finally:
                    if proc is not None:
                        with self._lock:
                            self.active_processes.pop(id(proc), None)
                            self.is_running = bool(self.active_processes)
            return {"returncode": returncode, "result": result}

        if concurrency == "light":
            self.light_queue.put((run_proc, [], on_finish))
            return None
        meta = {"label": label or display_name, "folder": folder_path, "priority": priority, "queued_at": time.time()}
        return self.heavy_queue.put((run_proc, [], on_finish), front=(priority == "high"), meta=meta)

    # --- גל 14: המתנה כשהמחשב עסוק (משחק/סטרים) לפני שמתחילים רינדור כבד ---
    BUSY_POLL_SECONDS = 15

    def busy_reason(self, guard):
        """מחרוזת "למה המחשב עסוק" או None. guard: {processes: [שמות exe], gpu_percent: סף}."""
        names = {str(n).lower() for n in (guard or {}).get("processes") or [] if str(n).strip()}
        if names:
            try:
                import psutil
                for proc in psutil.process_iter(["name"]):
                    name = (proc.info.get("name") or "").lower()
                    if name in names:
                        return f"{proc.info.get('name')} פועל"
            except Exception:
                pass
        threshold = (guard or {}).get("gpu_percent")
        if threshold:
            try:
                from utils.shared.hardware import get_gpu_stats
                # (ניצול כללי, VRAM, מנוע NVENC) - עסוק = הגבוה מבין הכללי וה-NVENC (משחק או הקלטת OBS)
                util, _vram, encoder = get_gpu_stats()
                load = max((v for v in (util, encoder) if v is not None), default=None)
                if load is not None and float(load) >= float(threshold):
                    return f"ה-GPU בעומס {float(load):.0f}%"
            except Exception:
                pass
        return None

    def _wait_until_not_busy(self, guard, label):
        announced = 0.0
        while True:
            reason = self.busy_reason(guard)
            if not reason:
                return
            if time.time() - announced > 120:
                self.log_queue.put((f"[{label}] ⏸️ ממתין - המחשב עסוק ({reason}). הרינדור יתחיל כשזה ייגמר.\n", None))
                announced = time.time()
            time.sleep(self.BUSY_POLL_SECONDS)

    def on_event(self, event_type, handler):
        """רושם handler(event) לשורות "EVENT:" מסוג event_type - אחד לכל סוג. נקרא מ-thread
        הקריאה של הריצה ששלחה את האירוע, אז handler צריך רק לתכנן ולהכניס לתור, לא לחכות.
        event כולל גם "script" - שם הסקריפט ששלח אותו."""
        self._event_handlers[event_type] = handler

    def _dispatch_event(self, raw, script):
        try:
            event = json.loads(raw)
        except (ValueError, TypeError):
            return
        if not isinstance(event, dict):
            return
        handler = self._event_handlers.get(event.get("type"))
        if handler is None:
            return
        try:
            handler({**event, "script": script})
        except Exception as e:  # handler שנכשל לא מפיל את קריאת הפלט של המאזין
            self.log_queue.put((f"[{script}] ⚠️ הטיפול באירוע {event.get('type')} נכשל: {e}\n", "red"))

    def _handle_output_line(self, line, prefix=None):
        """מטפל בשורת פלט בודדת מתת-תהליך. מחזיר dict אם זו הייתה שורת RESULT
        מובנית (ראו RESULT_LINE_PREFIX למעלה), אחרת None."""
        display = f"[{prefix}] {line}" if prefix else line
        # תיעוד מלא תמיד (item: log spam) - גם שורות שלא מוצגות בקונסולה
        # החיה למטה (כל עדכון tqdm) נשמרות כאן במלואן, בלי שום דילול.
        _SCRIPT_RUN_LOGGER.info(display)

        if line.startswith(RESULT_LINE_PREFIX):
            try:
                return json.loads(line[len(RESULT_LINE_PREFIX):].strip())
            except (ValueError, TypeError):
                pass
            return None

        if line.startswith(EVENT_LINE_PREFIX):
            self._dispatch_event(line[len(EVENT_LINE_PREFIX):].strip(), prefix)
            return None

        if line.startswith(MANIFEST_LINE_PREFIX):
            return None

        count_match = EXPLICIT_COUNT_PATTERN.match(line)
        if count_match:
            # סבב ייצוב: "PROGRESS: 2/5" - כמה מתוך כמה. done/total נשלחים גם כמספרים, כדי שהדפדפן ישקלל איתם את
            # הפס של הקובץ שבעבודה (בריצה של קובץ אחד הכולל היה 0% עד הסוף, בזמן שהקובץ כבר ב-77%)
            done, total = int(count_match.group(1)), int(count_match.group(2))
            if total > 0:
                self.progress_queue.put({"pct": min(100, done * 100 // total), "eta_seconds": None, "done": min(done, total), "total": total})
            return None

        explicit_match = EXPLICIT_PROGRESS_PATTERN.match(line)
        match = None if explicit_match else PROGRESS_PATTERN.search(line)
        if explicit_match is None and match is None:
            # רק שורות שאינן עדכון-התקדמות "רועש" (tqdm/PROGRESS: - כבר מיוצג
            # במלואו בפס ההתקדמות הייעודי דרך progress_queue למטה) מוצגות
            # בקונסולה החיה - אחרת ריצה ארוכה מציפה אותה באלפי עדכוני-אחוזים
            # כמעט-זהים ומכבידה על ה-GUI/דפדפן (item: log spam). ההיסטוריה
            # המלאה, כולל אלה, עדיין נשמרת למעלה בקובץ ה-log.
            self.log_queue.put((display + "\n", None))

        if explicit_match:
            # אין ל-PROGRESS: הידני שום מידע זמן (זה לא tqdm) - eta_seconds
            # תמיד None כאן, בניגוד לפס tqdm למטה.
            self.progress_queue.put({"pct": min(100, int(explicit_match.group(1))), "eta_seconds": None})
            return None

        if match:
            try:
                pct = min(100, int(match.group(1)))
                # item: התקדמות פר-קובץ (עורך-העל בווב) - התיאור של פס ה-tqdm (הטקסט
                # שלפני "NN%|", בד"כ שם הקובץ שמרונדר) נשלח כ-label, כדי שבריצה
                # מקבילית (--parallel) יוצגו כמה קבצים בו-זמנית, כל אחד עם האחוז שלו.
                label = line[:match.start()].rstrip().rstrip(":").strip() or None
                self.progress_queue.put({"pct": pct, "eta_seconds": _parse_tqdm_eta_seconds(line), "label": label})
            except ValueError:
                pass
        return None

    def pending_count(self):
        """מספר המשימות שממתינות בתור (לא כולל אלה שרצות כרגע), בשני המסלולים יחד."""
        return self.heavy_queue.qsize() + self.light_queue.qsize()

    def pending_counts_by_lane(self):
        """כמו pending_count(), אבל מפורק לפי מסלול - כדי שה-GUI יוכל להסביר
        *למה* סקריפט ממתין (heavy עמוס? light עמוס?) במקום מספר גולמי אחד."""
        return {"heavy": self.heavy_queue.qsize(), "light": self.light_queue.qsize()}

    def terminate_current(self):
        """עוצר את כל התהליכים הפעילים כרגע (בשני המסלולים) - לכפתור "עצור"
        היחיד ב-GUI אין דרך לבחור איזה תהליך ספציפי לעצור, אז הפעולה הבטוחה
        היחידה היא לעצור הכל. כמו pause_current/_suspend_tree - ffmpeg הוא
        ילד של תת-תהליך הסקריפט, לא מספיק לעצור רק אותו עצמו (item: בדיקת
        באגים מקיפה - נמצא ש-terminate_current, בניגוד ל-pause_current, לא
        היה עושה את זה: proc.terminate() היה עוצר רק את python.exe, ומשאיר
        את ffmpeg.exe רץ כתהליך-יתום שממשיך לכתוב פלט ולהחזיק ב-GPU)."""
        self._stop_pause_keepalive()
        self._paused = False
        with self._lock:
            processes = list(self.active_processes.values())
        for proc in processes:
            if psutil is not None:
                self._terminate_tree(proc.pid)
                continue
            try:
                proc.terminate()
            except Exception as e:
                self.log_queue.put((f"Terminate Error: {e}\n", "red"))

    def is_paused(self):
        return self._paused

    def pause_current(self):
        """משהה (מוקפא, לא נעצר) את כל התהליכים הפעילים כרגע *וכל תת-
        התהליכים שלהם* - ffmpeg הוא ילד של תת-תהליך הסקריפט, לא מספיק להשהות
        רק אותו עצמו. משתמש ב-psutil.Process.suspend() (NtSuspendProcess
        ב-Windows) - קיפוא CPU/GPU מיידי בלי לאבד שום התקדמות, resume_current()
        ממשיך מדויק מאיפה שנעצר (בניגוד ל-terminate_current, זו לא עצירה).
        לא משחרר את render_lock (התהליך עדיין "רץ" מבחינת שאר המערכת, רק קפוא
        בפועל - משהו אחר שיתפוס אותו היה מתחרה על אותו GPU) - במקום זאת שומר
        thread שמרענן אותו (touch) כדי שלא יחשב "תקוע" בהשהיה ממושכת."""
        if psutil is None:
            self.log_queue.put(("⚠️ psutil לא מותקן - לא ניתן להשהות תהליכים.\n", "red"))
            return
        with self._lock:
            processes = list(self.active_processes.values())
        if not processes:
            return
        for proc in processes:
            self._suspend_tree(proc.pid)
        self._paused = True
        self._start_pause_keepalive()

    def resume_current(self):
        if psutil is None:
            return
        with self._lock:
            processes = list(self.active_processes.values())
        self._stop_pause_keepalive()
        self._paused = False
        for proc in processes:
            self._resume_tree(proc.pid)

    def _terminate_tree(self, pid):
        try:
            parent = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return
        for child in parent.children(recursive=True):
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        try:
            parent.terminate()
        except psutil.NoSuchProcess:
            pass

    def _suspend_tree(self, pid):
        try:
            parent = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return
        # קודם ההורה (כדי שלא יוליד תת-תהליכים חדשים באמצע ההשהיה), ואז כל העץ עד נקודת שבת: תהליך שנולד בין
        # הסריקה להשהיה (למשל מפרש ה-venv שמוליד את ה-python האמיתי, או ffmpeg חדש) היה נשאר רץ - באג אמיתי
        # שהתבטא ככשל לסירוגין בטסט ההשהיה
        try:
            parent.suspend()
        except psutil.NoSuchProcess:
            pass
        suspended = set()
        for _ in range(5):
            try:
                fresh = [c for c in parent.children(recursive=True) if c.pid not in suspended]
            except psutil.NoSuchProcess:
                break
            if not fresh:
                break
            for child in fresh:
                suspended.add(child.pid)
                try:
                    child.suspend()
                except psutil.NoSuchProcess:
                    pass

    def _resume_tree(self, pid):
        try:
            parent = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return
        try:
            parent.resume()
        except psutil.NoSuchProcess:
            pass
        for child in parent.children(recursive=True):
            try:
                child.resume()
            except psutil.NoSuchProcess:
                pass

    def _start_pause_keepalive(self):
        if self._pause_keepalive_thread is not None and self._pause_keepalive_thread.is_alive():
            return
        self._pause_stop_event.clear()
        self._pause_keepalive_thread = threading.Thread(target=self._pause_keepalive_loop, daemon=True)
        self._pause_keepalive_thread.start()

    def _stop_pause_keepalive(self):
        self._pause_stop_event.set()

    def _pause_keepalive_loop(self):
        while not self._pause_stop_event.wait(_PAUSE_KEEPALIVE_INTERVAL_SECONDS):
            _touch_render_lock()


worker = TaskWorker()
