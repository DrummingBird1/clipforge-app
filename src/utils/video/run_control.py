# utils/video/run_control.py
#
# גל 8 של 102-ההצעות (items 95-96): שליטה בריצה *תוך כדי* - השהיה/המשך/ביטול של
# קובץ בודד בריצה מקבילית, ושינוי סדר הקבצים שעוד לא התחילו. ערוץ פשוט וחסין:
# הווב כותב קובץ JSON קטן ({"pause": [...], "cancel": [...], "priority": [...]},
# שמות-קבצים בלבד), והסקריפט קורא אותו ב-polling (מטמון לפי mtime). אין socket/IPC -
# אם הקובץ חסר/חצי-כתוב, נשארים עם המצב התקין האחרון.

import json
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

ACTIONS = ("pause", "resume", "cancel", "prioritize", "unprioritize")
EMPTY_STATE: Dict[str, List[str]] = {"pause": [], "cancel": [], "priority": []}
MAX_NAMES = 2000


def normalize_state(raw: Any) -> Dict[str, List[str]]:
    state: Dict[str, List[str]] = {key: [] for key in EMPTY_STATE}
    if not isinstance(raw, dict):
        return state
    for key in state:
        values = raw.get(key)
        if isinstance(values, list):
            seen = []
            for value in values[:MAX_NAMES]:
                name = os.path.basename(str(value))
                if name and name not in seen:
                    seen.append(name)
            state[key] = seen
    return state


def apply_action(state: Dict[str, List[str]], action: str, name: str) -> Dict[str, List[str]]:
    """מצב חדש אחרי פעולה על קובץ (טהור). resume מסיר מ-pause; cancel גובר על pause;
    prioritize מעביר לראש רשימת העדיפות (לחיצה נוספת על קובץ אחר = הוא הבא בתור)."""
    if action not in ACTIONS:
        raise ValueError(f"פעולה לא מוכרת: {action!r}")
    name = os.path.basename(str(name))
    new = normalize_state(state)
    if not name:
        return new
    if action == "pause" and name not in new["pause"]:
        new["pause"].append(name)
    elif action == "resume":
        new["pause"] = [n for n in new["pause"] if n != name]
    elif action == "cancel":
        if name not in new["cancel"]:
            new["cancel"].append(name)
        new["pause"] = [n for n in new["pause"] if n != name]
    elif action == "prioritize":
        new["priority"] = [name] + [n for n in new["priority"] if n != name]
    elif action == "unprioritize":
        new["priority"] = [n for n in new["priority"] if n != name]
    return new


def write_state(path: str, state: Dict[str, List[str]]) -> None:
    from utils.shared.atomic_write import atomic_write_json
    atomic_write_json(path, normalize_state(state))


def next_task_index(pending_names: Sequence[str], priority: Sequence[str]) -> int:
    """איזה קובץ מהממתינים לקחת עכשיו: הראשון ברשימת העדיפות שעוד ממתין, אחרת הסדר המקורי."""
    for wanted in priority:
        for index, name in enumerate(pending_names):
            if name == wanted:
                return index
    return 0


class RunControl:
    """צד הסקריפט: קורא את קובץ הבקרה (מטמון לפי mtime, חסין לכתיבה חלקית)."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._mtime: Optional[float] = None
        self._state: Dict[str, List[str]] = normalize_state(None)

    def state(self) -> Dict[str, List[str]]:
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            return self._state
        with self._lock:
            if mtime != self._mtime:
                try:
                    with open(self.path, encoding="utf-8") as f:
                        self._state = normalize_state(json.load(f))
                    self._mtime = mtime
                except (OSError, ValueError):
                    pass  # כתיבה באמצע - נשארים עם המצב האחרון
            return self._state

    def action_for(self, name: str) -> str:
        """"cancel" / "pause" / "run" לקובץ (לפי שם-קובץ, בלי תיקייה)."""
        state = self.state()
        name = os.path.basename(name)
        if name in state["cancel"]:
            return "cancel"
        if name in state["pause"]:
            return "pause"
        return "run"

    def priority(self) -> List[str]:
        return list(self.state()["priority"])

    def wait_while_paused(self, name: str, poll_seconds: float = 0.5, on_pause: Optional[Callable[[], None]] = None) -> str:
        """לפני שקובץ מתחיל: ממתין כל עוד הוא מושהה. מחזיר "cancel" או "run"."""
        announced = False
        while True:
            action = self.action_for(name)
            if action != "pause":
                return action
            if not announced and on_pause:
                on_pause()
                announced = True
            time.sleep(poll_seconds)


def run_tasks(
    tasks: Sequence[Tuple[Any, ...]],
    run_one: Callable[..., None],
    parallel: int,
    pick: Optional[Callable[[List[Tuple[Any, ...]]], int]] = None,
) -> None:
    """מריץ את המשימות עם עד parallel במקביל, כשכל worker בוחר את *הבאה* רק כשהוא
    מתפנה (pick) - כך שינוי סדר תוך ריצה משפיע על מה שעוד לא התחיל. חריגה ב-worker
    עוצרת לקיחת משימות חדשות ומועלית לקורא (כמו future.result() קודם)."""
    pending = list(tasks)
    lock = threading.Lock()
    errors: List[BaseException] = []

    def _take() -> Optional[Tuple[Any, ...]]:
        with lock:
            if not pending or errors:
                return None
            index = pick(pending) if pick else 0
            if not 0 <= index < len(pending):
                index = 0
            return pending.pop(index)

    if parallel <= 1:
        while True:
            task = _take()
            if task is None:
                return
            run_one(*task)

    def _worker() -> None:
        while True:
            task = _take()
            if task is None:
                return
            try:
                run_one(*task)
            except BaseException as e:  # noqa: BLE001 - מועבר לקורא למטה
                with lock:
                    errors.append(e)
                return

    threads = [threading.Thread(target=_worker, daemon=True) for _ in range(parallel)]
    for thread in threads:
        thread.start()
    for thread in threads:
        while thread.is_alive():
            thread.join(timeout=0.5)  # join עם timeout - Ctrl+C נשאר זמין ב-thread הראשי
    if errors:
        raise errors[0]
