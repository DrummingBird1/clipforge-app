# tests/web/test_web_app_wave31_tasks_browser.py
#
# גל 31: מדידה - חמש משימות ליבה (חיתוך, לוגו, צבע, ייצוא אנכי, הרצה) בלחיצות אמיתיות בדפדפן, עם ספירת
# פעולות וזמן לכל משימה ותקציב שלא עוברים. כך סידור העורך נמדד, ולא רק "מרגיש" טוב יותר.
#
# לפני הסידור (גלים 27-31), לפי המסלולים בממשק של גל 26: חיתוך 2 (לפתוח ✂️, להקליד), לוגו 3 (לפתוח 🧩,
# ➕ לוגו, נתיב), צבע 4 (לפתוח 🎨, שלושה סליידרים), אנכי 2 (לפתוח 📐, לבחור 9:16), הרצה 1 - סה"כ 12.
# אחרי: 2, 3, 2, 2, 2 = 11 (הרצה עולה ב-1 - הגיליון שמראה מה ירונדר), ובמצב "פשוט": צבע 1, אנכי 1, הרצה 2.
import json
import time


import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

MAX_TASK_SECONDS = 4.0


class _Session:
    """פעולות משתמש אמיתיות (לחיצה/הקלדה) שנספרות, וזמן לכל משימה."""

    def __init__(self, page):
        self.page = page
        self.report = {}
        self._actions = 0

    def click(self, selector):
        self._actions += 1
        self.page.click(selector)

    def fill(self, selector, value):
        self._actions += 1
        self.page.fill(selector, value)

    def task(self, name, steps, done):
        self._actions = 0
        start = time.perf_counter()
        steps()
        self.page.wait_for_function(done, timeout=5000)
        self.report[name] = {"actions": self._actions, "seconds": round(time.perf_counter() - start, 2)}


def _ready(page, tmp_path, mode):
    for name in ("a.mp4", "b.mp4"):
        (tmp_path / name).write_bytes(b"x")
    page.evaluate("(m) => { setVeMode(m); setVeLayout('tabs'); window.__runs = 0; runScript = () => { window.__runs++; }; }", mode)
    page.evaluate("(f) => { document.getElementById('folderInput').value = f; onFolderTyped(); }", str(tmp_path))
    page.wait_for_function("() => (_veQueueState || []).length === 2 && !document.getElementById('veStickyRunBtn').disabled", timeout=15000)
    page.wait_for_function("() => !!_veSchema && document.querySelector('#veTargetChips button[data-target=shorts]')")


def _save(report, tmp_path, name):
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(name, json.dumps(report, ensure_ascii=False))


def test_five_core_tasks_in_the_studio_stay_within_their_click_budget(editor_page, tmp_path):
    page = editor_page
    _ready(page, tmp_path, "advanced")
    s = _Session(page)
    logo = str(tmp_path / "logo.png")
    s.task("trim", lambda: (s.click("#veCatTabs button[data-cat=time]"), s.fill("#veTrimStart", "2")),
           "() => _collectRunOptions().trim_start === 2")
    s.task("logo", lambda: (s.click("#veCatTabs button[data-cat=layers]"), s.click(".ve-layer-add-bar button:has-text('לוגו')"),
                            s.fill("#veWatermarkPath", logo)),
           f"() => _collectRunOptions().watermark_path === {json.dumps(logo)}")
    s.task("color", lambda: (s.click("#veCatTabs button[data-cat=look]"), s.click("#veLookCards [data-look=cinematic]")),
           "() => _collectRunOptions().eq_contrast === 1.15")
    s.task("vertical", lambda: (s.click("#veCatTabs button[data-cat=output]"), s.click("#veTargetChips button[data-target=shorts]")),
           "() => JSON.stringify(_collectRunOptions().targets) === '[\"shorts\"]'")
    s.task("run", lambda: (s.click("#veStickyRunBtn"), s.click("#veRunSheetGo")), "() => window.__runs === 1")
    _save(s.report, tmp_path, "studio_tasks")
    budget = {"trim": 2, "logo": 3, "color": 2, "vertical": 2, "run": 2}
    for name, limit in budget.items():
        assert s.report[name]["actions"] <= limit, (name, s.report[name])
        assert s.report[name]["seconds"] < MAX_TASK_SECONDS, (name, s.report[name])
    assert sum(r["actions"] for r in s.report.values()) <= 11  # לפני הסידור: 12


def test_simple_mode_does_look_vertical_and_run_in_four_clicks(editor_page, tmp_path):
    page = editor_page
    _ready(page, tmp_path, "simple")
    s = _Session(page)
    s.task("color", lambda: s.click("#veStepLookCards [data-look=vivid]"), "() => _collectRunOptions().eq_saturation === 1.45")
    s.task("vertical", lambda: s.click("#veStepTargets button[data-target=shorts]"), "() => JSON.stringify(_collectRunOptions().targets) === '[\"shorts\"]'")
    s.task("run", lambda: (s.click("#veStepRunBtn"), s.click("#veRunSheetGo")), "() => window.__runs === 1")
    _save(s.report, tmp_path, "simple_tasks")
    assert [s.report[k]["actions"] for k in ("color", "vertical", "run")] == [1, 1, 2]
    assert all(r["seconds"] < MAX_TASK_SECONDS for r in s.report.values()), s.report
