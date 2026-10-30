# tests/dataviz/test_web_app_dataviz_fix_ui_browser.py
#
# 23.10.2026, סריקת הבאגים - מנה 4 (הזרימות בממשק). המספרים לפי הדוח (dataviz-bug-hunt-2026-10-23.md):
# ג1 "הרץ" רינדר בלי הטיוטה; ג2 מעבר פרק זרק את הטיוטה בלי לשאול; ג15 טעינה עצלה שנכשלה - בלי הודעה; ב30 במצב פשוט
# "טבלת הנתונים" פתחה חלון מוסתר; ב31 לחיצה כפולה בקטלוג; ב33 Ctrl+Z בלשוניות שמשנות אובייקט; ב34 שמירה מחקה את מה
# שהוקלד בזמן הבקשה, ולחיצה כפולה שמרה פעמיים; ב35 "שינויים להרצה הזו" עברו לפרק אחר; ב36 שגיאת שרת כרשימה ריקה;
# ב39 גרירת קובץ לא נתמך פתחה אותו במקום האפליקציה; נ9 טופס "מקבצים" שמר את הערכים של הפרק הקודם.
# xdist-group: workspace
import json

import pytest

from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    for name in ("alpha", "beta"):
        write_episode(data / "dataviz_episodes", overrides={"title": name}, name=name)
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    return data


def _open(page, mode="regular"):
    page.evaluate(f"() => {{ localStorage.setItem('dvzMode', '{mode}'); closeVeEditor(); switchTab('dataviz'); }}")
    page.wait_for_selector("#dvzEpisodes .dvz-card")
    page.wait_for_function("() => dvzState.selected === 'alpha'")


# בקשות שיוצאות דרך ה-service worker לא עוברות ב-page.route (והיו מגיעות לשרת האמיתי - רינדור, הורדה מהרשת). התשובה
# המזויפת ניתנת בתוך הדף, וכתובת שלא ברשימה ממשיכה לשרת הבדיקה כרגיל
def _stub_fetch(page, replies):
    page.evaluate("""(replies) => {
        const real = window.fetch;
        window.__stubbed = [];
        window.fetch = (url, options) => {
            const hit = Object.keys(replies).find(part => String(url).includes(part));
            if (!hit) return real(url, options);
            window.__stubbed.push(hit);
            return Promise.resolve(new Response(JSON.stringify(replies[hit]), {status: 200, headers: {"Content-Type": "application/json"}}));
        };
    }""", replies)


def _editor(page):
    page.evaluate("() => { document.getElementById('dvzEditor').open = true; }")
    page.wait_for_function("() => dvzEd.data && dvzEd.data.episode === dvzState.selected")


# ---------- ג1 ----------
def test_run_with_a_draft_asks_and_saves_it_first(editor_page, screen):
    page = editor_page
    _open(page)
    _editor(page)
    _stub_fetch(page, {"/api/dataviz/run": {"ok": True}})
    page.evaluate("() => _dvzStage('subtitle', 'מהטיוטה')")
    page.evaluate("() => { window._run = dvzRun(); }")
    page.click("#veConfirmCancelBtn", timeout=5000)                             # קודם: אין שאלה - רץ בלי הטיוטה
    page.evaluate("() => window._run")                                         # מחכה לסוף ההרצה
    assert page.evaluate("() => window.__stubbed") == [] and page.evaluate("() => Object.keys(dvzEd.draft)") == ["subtitle"]
    page.evaluate("() => { window._run = dvzRun(); }")
    page.click("#veConfirmOkBtn")
    page.evaluate("() => window._run")                                         # מחכה לסוף ההרצה
    assert page.evaluate("() => window.__stubbed") == ["/api/dataviz/run"] and page.evaluate("() => Object.keys(dvzEd.draft).length") == 0
    saved = json.loads((screen / "dataviz_overrides" / "alpha.json").read_text(encoding="utf-8"))
    assert saved["subtitle"] == "מהטיוטה"                                       # נשמר לפני ההרצה


# ---------- ג2 ----------
def test_switching_episode_with_a_draft_asks_first(editor_page, screen):
    page = editor_page
    _open(page)
    _editor(page)
    page.evaluate("() => _dvzStage('title', 'כותרת שלא נשמרה')")
    page.evaluate("() => document.querySelector('#dvzEpisodes .dvz-card[data-episode=\"beta\"]').click()")
    page.click("#veConfirmCancelBtn", timeout=5000)                             # קודם: הטיוטה נזרקה בלי לשאול
    assert page.evaluate("() => [dvzState.selected, Object.keys(dvzEd.draft)]") == ["alpha", ["title"]]
    page.evaluate("() => document.querySelector('#dvzEpisodes .dvz-card[data-episode=\"beta\"]').click()")
    page.click("#veConfirmOkBtn")
    page.wait_for_function("() => dvzState.selected === 'beta'")


# ---------- ב33 / ב34 ----------
def test_undo_restores_the_previous_value_of_an_object_setting(editor_page, screen):
    page = editor_page
    _open(page)
    _editor(page)
    label = page.evaluate("""() => {
        const events = [{date: "2020-02-01", label: "ראשון"}];
        _dvzStage("events", events);
        dvzUndo.lastAt = 0;                       // כמו הפסקה של יותר מ-1.2 שניות בין העריכות
        events[0].label = "שני";                  // הלשונית ממשיכה לשנות את האובייקט שלה
        _dvzStage("events", events);
        dvzUndoDraft();
        return dvzEd.draft.events && dvzEd.draft.events[0].label;
    }""")
    assert label == "ראשון"                                                     # קודם: "שני" (Ctrl+Z לא החזיר כלום)


def test_saving_keeps_what_was_typed_during_the_request_and_saves_once(editor_page, screen):
    page = editor_page
    _open(page)
    _editor(page)
    posts = []
    page.on("request", lambda r: posts.append(1) if r.url.endswith("/api/dataviz/episodes/override") and r.method == "POST" else None)
    left = page.evaluate("""async () => {
        _dvzStage("title", "נשמר");
        const first = dvzSaveDraft(), second = dvzSaveDraft();   // לחיצה כפולה / Ctrl+S
        _dvzStage("subtitle", "הוקלד בזמן השמירה");
        await Promise.all([first, second]);
        return Object.keys(dvzEd.draft);
    }""")
    assert left == ["subtitle"] and len(posts) == 1                             # קודם: [] ושתי בקשות


# ---------- ב35 ----------
def test_run_options_do_not_carry_over_to_another_episode(editor_page, screen):
    page = editor_page
    _open(page)
    page.evaluate("() => { document.getElementById('dvzChart').value = 'pie_race'; }")
    page.evaluate("() => document.querySelector('#dvzEpisodes .dvz-card[data-episode=\"beta\"]').click()")
    page.wait_for_function("() => dvzState.selected === 'beta'")
    assert page.evaluate("() => document.getElementById('dvzChart').value") == ""   # קודם: עוגה גם בפרק השני


# ---------- ב30 ----------
def test_simple_mode_shows_the_data_window_when_a_tool_opens_it(editor_page, screen):
    page = editor_page
    page.evaluate("() => localStorage.removeItem('dvzMode')")
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector("#dvzEpisodes .dvz-card")
    page.wait_for_function("() => dvzState.selected && document.getElementById('dvzToolsBtn')")
    page.click("#dvzToolsBtn")
    page.click("#dvzToolGrid")
    page.wait_for_function("() => document.getElementById('dvzData').open")
    assert page.evaluate("() => getComputedStyle(document.getElementById('dvzData')).display") != "none"   # קודם: none


# ---------- ב31 ----------
def test_catalog_buttons_are_locked_while_downloading(editor_page, screen):
    page = editor_page
    _open(page)
    _stub_fetch(page, {"/api/dataviz/catalog/fetch": {"ok": True, "rows": 3, "range": ["2000", "2002"]}})   # בלי הורדה אמיתית
    states = page.evaluate("""async () => {
        _dvzCatalog.picked = {id: "wb_population", title: "אוכלוסייה"};
        const running = dvzCatalogFetch("source");
        const during = document.getElementById("dvzCatalogSourceBtn").disabled;
        await running;
        return [during, document.getElementById("dvzCatalogSourceBtn").disabled];
    }""")
    assert states == [True, False] and page.evaluate("() => window.__stubbed") == ["/api/dataviz/catalog/fetch"]   # קודם: לא ננעל


# ---------- ב36 ----------
def test_a_server_error_on_the_list_is_shown_as_an_error(editor_page, screen, monkeypatch):
    page = editor_page
    from dataviz.web import episodes as de

    def boom(*args, **kwargs):
        raise RuntimeError("שרת שבור")
    monkeypatch.setattr(de, "list_episodes", boom)                             # 500 אמיתי מהשרת (page.route לא רואה את ה-service worker)
    page.evaluate("() => { localStorage.setItem('dvzMode', 'regular'); closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector("#dvzEpisodes .empty-msg.bad")                       # קודם: "אין פרקים" והכפתור הגדול


# ---------- ב39 ----------
def test_dropping_an_unsupported_file_stays_in_the_app(editor_page, screen):
    page = editor_page
    _open(page)
    prevented = page.evaluate("""() => {
        const panel = document.querySelector('[data-dvz-drop]');
        const dt = new DataTransfer(); dt.items.add(new File(['x'], 'photo.png', {type: 'image/png'}));
        const ev = new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true});
        panel.dispatchEvent(ev); return ev.defaultPrevented;
    }""")
    assert prevented                                                            # קודם: false - הדפדפן פותח את הקובץ
    page.wait_for_selector("#toastHost .toast")


# ---------- נ9 ----------
def test_the_from_files_form_is_cleared_after_creating(editor_page, screen):
    page = editor_page
    _open(page)
    page.evaluate("() => dvzOpenNew('files')")
    page.evaluate("""() => dvzTableFile(new File(['date,city,n\\n2020-01-01,A,1\\n2020-01-02,B,2\\n'], 'cities.csv', {type: 'text/csv'}))""")
    page.wait_for_function("() => document.getElementById('dvzNewName').value === 'cities'")
    page.evaluate("() => { document.getElementById('dvzNewGroup').value = 'city'; }")
    page.evaluate("() => dvzCreateEpisode()")
    page.wait_for_function("() => dvzState.episodes.some(e => e.name === 'cities')")
    assert page.evaluate("() => [document.getElementById('dvzNewName').value, document.getElementById('dvzNewTitle').value, _dvzCsvText]") == ["", "", ""]


# ---------- ג15 ----------
def test_a_failed_lazy_load_of_the_screen_shows_a_message(editor_page, screen):
    page = editor_page
    page.reload()
    page.wait_for_function("() => typeof switchTab === 'function' && typeof _uiLoadScript === 'function'")
    page.evaluate("() => { _uiLoadScript = () => Promise.reject(new Error('bundle 404')); closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector("#toastHost .toast")                                 # קודם: שום הודעה (ה-.catch היה בתוך הערה)
