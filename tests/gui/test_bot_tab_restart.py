# tests/gui/test_bot_tab_restart.py
#
# לולאת ההפעלה מחדש של הבוט בטאב הבוט (GUI שולחני, ui/bot_tab.py): קריסה (1) מפעילה מחדש, שגיאת הגדרה
# של main.py (2 - אין טוקן / נדחה / חסר Intent) עוצרת. בלי Tk אמיתי ובלי להריץ את הבוט: הרכיב נבנה עם
# __new__, ו-subprocess.Popen מוחלף בתהליך מדומה שיוצא מיד עם הקוד שנבחר.
import ast
from tests import PROJECT_ROOT
import os


import ui.bot_tab as bot_tab_module
from ui.bot_tab import BotTabComponent

MAIN_PY = os.path.join(PROJECT_ROOT, "src", "entrypoints", "main.py")


class _FakeProc:
    def __init__(self, returncode):
        self.returncode = returncode
        self.stdout = self

    def readline(self):
        return ""

    def wait(self):
        return self.returncode

    def terminate(self):
        pass


class _RecordingDispatcher:
    def __init__(self):
        self.calls = []

    def call_soon(self, fn, *args):
        self.calls.append((fn.__name__, args))


def _make_tab():
    tab = BotTabComponent.__new__(BotTabComponent)
    tab.bot_process = None
    tab.is_running = True
    tab.crash_timestamps = []
    tab._dispatcher = _RecordingDispatcher()
    return tab


def _run_with_exit_codes(monkeypatch, tab, codes):
    """Popen מחזיר תהליכים עם הקודים לפי הסדר; קריאה נוספת אחרי הרשימה עוצרת את הלולאה (כמו לחיצה על 'כבה בוט')."""
    started = []

    def _fake_popen(*args, **kwargs):
        if len(started) >= len(codes):
            tab.is_running = False
            started.append("extra")
            return _FakeProc(0)
        started.append(codes[len(started)])
        return _FakeProc(started[-1])

    monkeypatch.setattr(bot_tab_module.subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(bot_tab_module.time, "sleep", lambda _s: None)
    tab.run_bot_process()
    return started


def test_gui_config_error_code_matches_main_py():
    with open(MAIN_PY, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    values = [ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
              and any(getattr(t, "id", None) == "CONFIG_ERROR_EXIT_CODE" for t in n.targets)]
    assert values == [bot_tab_module.BOT_CONFIG_ERROR_EXIT_CODE]


def test_crash_restarts_but_a_config_error_stops_without_restarting(monkeypatch):
    tab = _make_tab()

    started = _run_with_exit_codes(monkeypatch, tab, [1, 2])

    assert started == [1, 2]
    assert tab.is_running is False
    assert ("_on_bot_config_error", ()) in tab._dispatcher.calls
    logged = "".join(str(args[0]) for name, args in tab._dispatcher.calls if name == "_do_write_to_log")
    # t() הופך את סדר המילים בעברית לתצוגה של Tk - בודקים את המילים, לא את הסדר
    assert "שגיאת" in logged and "הגדרה" in logged
